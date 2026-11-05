#!/usr/bin/env python3
"""Loopback-only laboratory UI/chemistry sandbox. No bot imports or databases."""
import argparse
import base64
import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hmac
import math
import os
import re
import time
from pathlib import Path
import secrets
import tempfile
import threading
from urllib.parse import urlsplit, unquote
import zlib

MAX_BUNDLE = 8_000_000
MAX_CONTENT = 12_000_000
CONFIG_LOCK=threading.Lock()
SESSION_COOKIE='ege_lab_session'


def unpack(encoded):
    packed = base64.b64decode(encoded, validate=True)
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    data = decoder.decompress(packed, MAX_CONTENT + 1)
    if len(data) > MAX_CONTENT or not decoder.eof or decoder.unused_data:
        raise ValueError('invalid or excessive compressed content')
    return data


def load_bundle(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BUNDLE:
        raise ValueError('bundle too large')
    bundle = json.loads(raw)
    if bundle.get('format') != 'ege-lab-sandbox-v1':
        raise ValueError('unknown bundle')
    html = unpack(bundle['html_gzip_base64'])
    payload_bytes = unpack(bundle['payload_gzip_base64'])
    if hashlib.sha256(html).hexdigest() != bundle['html_sha256'] or hashlib.sha256(payload_bytes).hexdigest() != bundle['payload_sha256']:
        raise ValueError('content digest mismatch')
    payload = json.loads(payload_bytes)
    if payload.get('ok') is not True or not payload['data'].get('preview'):
        raise ValueError('sandbox payload required')
    health = {'ok': True, 'sandbox': True, 'build': bundle['build'],
              'bundle_sha256': hashlib.sha256(raw).hexdigest(),
              'html_sha256': bundle['html_sha256'], 'payload_sha256': bundle['payload_sha256'],
              'coverage': payload['data']['coverage']}
    return html, payload, health


def access_password(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32).hex()


def access_allowed(header, access_file):
    """Reload on each request: expiry and revocation take effect immediately."""
    try:
        if not header.startswith('Basic ') or len(header) > 2048:
            return False
        credentials = base64.b64decode(header[6:], validate=True).decode('utf-8')
        username, password = credentials.split(':', 1)
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}', username) or not 1 <= len(password) <= 256:
            return False
        raw = Path(access_file).read_bytes()
        if len(raw) > 65536:
            return False
        config = json.loads(raw)
        if not isinstance(config, dict) or config.get('version') != 1 or not isinstance(config.get('users'), dict):
            return False
        user = config['users'].get(username)
        if not isinstance(user, dict) or user.get('revoked') is not False:
            return False
        expires = float(user.get('expires', 0))
        if not math.isfinite(expires) or expires <= time.time():
            return False
        salt, digest = user.get('salt', ''), user.get('digest', '')
        if not re.fullmatch(r'[0-9a-f]{32}', salt) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            return False
        return hmac.compare_digest(access_password(password, salt), digest)
    except (OSError, ValueError, TypeError, UnicodeError):
        return False


def read_access_config(access_file):
    raw=Path(access_file).read_bytes()
    if len(raw)>65536: raise ValueError('access file too large')
    config=json.loads(raw)
    if not isinstance(config,dict) or config.get('version')!=1 or not isinstance(config.get('users'),dict):
        raise ValueError('invalid access file')
    config.setdefault('invites',{})
    return config


def valid_user(config, username, password):
    if not isinstance(username,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{3,48}',username): return False
    if not isinstance(password,str) or not 1<=len(password)<=256: return False
    user=config.get('users',{}).get(username)
    if not isinstance(user,dict) or user.get('revoked') is not False: return False
    expires=float(user.get('expires',0))
    salt,digest=user.get('salt',''),user.get('digest','')
    return (math.isfinite(expires) and expires>time.time() and re.fullmatch(r'[0-9a-f]{32}',salt)
            and re.fullmatch(r'[0-9a-f]{64}',digest) and hmac.compare_digest(access_password(password,salt),digest))


def make_session(username, user):
    expires=min(int(user.get('expires',0)),int(time.time()+7*86400))
    payload=f'{username}|{expires}|{secrets.token_urlsafe(12)}'
    key=bytes.fromhex(user['digest'])
    sig=hmac.new(key,payload.encode(),hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f'{payload}|{sig}'.encode()).decode().rstrip('='),expires


def session_user(cookie, access_file):
    try:
        if not cookie or len(cookie)>1024: return None
        raw=base64.urlsafe_b64decode(cookie+'='*((4-len(cookie)%4)%4)).decode()
        username,expiry,nonce,sig=raw.split('|',3)
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}',username) or not re.fullmatch(r'[0-9a-f]{64}',sig): return None
        expires=int(expiry)
        if expires<=time.time(): return None
        config=read_access_config(access_file);user=config['users'].get(username)
        if not isinstance(user,dict) or user.get('revoked') is not False or float(user.get('expires',0))<=time.time(): return None
        payload=f'{username}|{expiry}|{nonce}';expected=hmac.new(bytes.fromhex(user['digest']),payload.encode(),hashlib.sha256).hexdigest()
        return username if hmac.compare_digest(expected,sig) else None
    except (OSError,ValueError,TypeError,UnicodeError,KeyError): return None


def consume_invite(access_file, token, username, password, days=14):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{3,48}',username) or not isinstance(password,str) or not 12<=len(password)<=256:
        raise ValueError('invalid_credentials')
    digest_token=hashlib.sha256(token.encode()).hexdigest()
    with CONFIG_LOCK:
        config=read_access_config(access_file);invite=config.get('invites',{}).get(digest_token)
        if not isinstance(invite,dict) or invite.get('used') is not False or float(invite.get('expires',0))<=time.time():
            raise ValueError('invite_invalid_or_expired')
        if username in config['users']: raise ValueError('username_taken')
        salt=secrets.token_hex(16)
        config['users'][username]={'salt':salt,'digest':access_password(password,salt),'expires':time.time()+days*86400,'revoked':False}
        invite['used']=True
        _write_access_config(access_file,config)
        return config['users'][username]


def _write_access_config(access_file, config):
    path=Path(access_file);fd,name=tempfile.mkstemp(prefix='.pilot-users-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream: json.dump(config,stream);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,0o644);os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)


def login_page(message=''):
    msg=f'<p class="msg">{html.escape(message)}</p>' if message else ''
    return ('''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Вход · ЕГЭ БЛИЗКО</title>
<style>body{margin:0;background:#fff8fc;color:#26212a;font:16px system-ui;display:grid;min-height:100vh;place-items:center}.box{box-sizing:border-box;width:min(92vw,420px);padding:32px;background:white;border:1px solid #efd9e5;border-radius:24px;box-shadow:0 12px 40px #53243a12}h1{font-size:25px;margin:0 0 8px}p{color:#786d78}.msg{color:#b00062}label{display:block;margin:18px 0 6px}input{box-sizing:border-box;width:100%;padding:13px;border:1px solid #d9cbd5;border-radius:12px;font:inherit}button{margin-top:22px;width:100%;padding:14px;border:0;border-radius:14px;background:#f00087;color:white;font:600 16px system-ui;cursor:pointer}a{color:#b00062}</style>
<main class="box"><h1>ЕГЭ БЛИЗКО · Лаборатория</h1><p>Войди в аккаунт преподавателя</p>'''+msg+'''
<form method="post" action="/lab-app/auth/login"><label>Логин</label><input name="username" autocomplete="username" required minlength="3" maxlength="48" pattern="[A-Za-z0-9_-]+"><label>Пароль</label><input name="password" type="password" autocomplete="current-password" required maxlength="256"><button>Войти</button></form></main></html>''').encode()


def invite_page(token, message=''):
    msg=f'<p class="msg">{html.escape(message)}</p>' if message else ''
    return ('''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>Приглашение · ЕГЭ БЛИЗКО</title>
<style>body{margin:0;background:#fff8fc;color:#26212a;font:16px system-ui;display:grid;min-height:100vh;place-items:center}.box{box-sizing:border-box;width:min(92vw,420px);padding:32px;background:white;border:1px solid #efd9e5;border-radius:24px;box-shadow:0 12px 40px #53243a12}h1{font-size:25px;margin:0 0 8px}p{color:#786d78}.msg{color:#b00062}label{display:block;margin:18px 0 6px}input{box-sizing:border-box;width:100%;padding:13px;border:1px solid #d9cbd5;border-radius:12px;font:inherit}button{margin-top:22px;width:100%;padding:14px;border:0;border-radius:14px;background:#f00087;color:white;font:600 16px system-ui;cursor:pointer}</style>
<main class="box"><h1>Приглашение в лабораторию</h1><p>Создай логин и пароль. Ссылка действует один раз.</p>'''+msg+f'''
<form method="post" action="/lab-app/auth/register"><input type="hidden" name="token" value="{html.escape(token,quote=True)}"><label>Придумай логин</label><input name="username" autocomplete="username" required minlength="3" maxlength="48" pattern="[A-Za-z0-9_-]+"><label>Придумай пароль (не менее 12 символов)</label><input name="password" type="password" autocomplete="new-password" required minlength="12" maxlength="256"><button>Создать аккаунт</button></form></main></html>''').encode()


def handler_for(html, payload, health, access_file=None):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *args):
            pass  # No uploaded documents, credentials or request bodies in logs.

        def send(self, code, body, content_type='application/json; charset=utf-8'):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.end_headers()
            self.wfile.write(body)

        def json(self, code, data):
            self.send(code, json.dumps(data, ensure_ascii=False).encode())

        def set_session(self, username):
            config=read_access_config(access_file);user=config['users'][username]
            token,expires=make_session(username,user)
            self.send_header('Set-Cookie',f'{SESSION_COOKIE}={token}; Path=/; Max-Age={max(0,expires-int(time.time()))}; Secure; HttpOnly; SameSite=Lax')

        def authorized(self):
            if access_file is None:
                self.pilot_user='';return True
            cookie=''
            for part in self.headers.get('Cookie','').split(';'):
                key,sep,value=part.strip().partition('=')
                if sep and key==SESSION_COOKIE: cookie=value
            username=session_user(cookie,access_file)
            if username:
                self.pilot_user=username;return True
            header=self.headers.get('Authorization','')
            if access_allowed(header,access_file):
                self.pilot_user=base64.b64decode(header[6:],validate=True).decode('utf-8').split(':',1)[0]
                return True
            return False

        def do_GET(self):
            path = urlsplit(self.path).path
            if path=='/healthz': return self.json(200,health)
            if path.startswith('/invite/') and access_file is not None:
                token=unquote(path[len('/invite/'):])
                if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',token): return self.send(404,invite_page('', 'Ссылка приглашения недействительна.'),'text/html; charset=utf-8')
                try:
                    config=read_access_config(access_file);digest=hashlib.sha256(token.encode()).hexdigest();invite=config.get('invites',{}).get(digest)
                    if not isinstance(invite,dict) or invite.get('used') is not False or float(invite.get('expires',0))<=time.time():
                        return self.send(410,invite_page('', 'Ссылка уже использована или срок её действия истёк.'),'text/html; charset=utf-8')
                except (OSError,ValueError,TypeError): return self.send(503,invite_page('', 'Не удалось проверить приглашение.'),'text/html; charset=utf-8')
                return self.send(200,invite_page(token),'text/html; charset=utf-8')
            if path == '/lab-app':
                if access_file is not None and not self.authorized(): return self.send(200,login_page(),'text/html; charset=utf-8')
                return self.send(200, html, 'text/html; charset=utf-8')
            return self.json(404, {'ok': False, 'error': 'not_found'})

        def do_POST(self):
            path=urlsplit(self.path).path
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if access_file is not None and path=='/lab-app/auth/logout' and size==0:
                    request={}
                else:
                    if not 0 < size <= 50_000:
                        raise ValueError('length')
                    body=self.rfile.read(size)
                    if path in ('/lab-app/auth/login','/lab-app/auth/register'):
                        request=dict(__import__('urllib.parse',fromlist=['parse_qsl']).parse_qsl(body.decode('utf-8'),keep_blank_values=True))
                    else: request=json.loads(body)
                if not isinstance(request,dict): raise ValueError('request object required')
            except (ValueError,UnicodeError):
                return self.json(400, {'ok': False, 'error': 'invalid_request'})
            if access_file is not None and path=='/lab-app/auth/login':
                username=request.get('username','');password=request.get('password','')
                try:
                    config=read_access_config(access_file)
                    if not valid_user(config,username,password): return self.send(401,login_page('Логин или пароль не подошёл.'),'text/html; charset=utf-8')
                    self.send_response(303);self.set_session(username);self.send_header('Location','/lab-app');self.send_header('Cache-Control','no-store');self.send_header('Content-Length','0');self.end_headers();return
                except (OSError,ValueError,TypeError): return self.send(503,login_page('Вход временно недоступен.'),'text/html; charset=utf-8')
            if access_file is not None and path=='/lab-app/auth/register':
                try:
                    username=request.get('username','');password=request.get('password','');token=request.get('token','')
                    consume_invite(access_file,token,username,password)
                    self.send_response(303);self.set_session(username);self.send_header('Location','/lab-app');self.send_header('Cache-Control','no-store');self.send_header('Content-Length','0');self.end_headers();return
                except ValueError as error:
                    reason=str(error);message=('Логин уже занят. Выбери другой.' if reason=='username_taken' else 'Проверь логин и пароль: пароль должен быть не короче 12 символов.' if reason=='invalid_credentials' else 'Приглашение недействительно или уже использовано.')
                    token=request.get('token','')
                    return self.send(400,invite_page(token,message),'text/html; charset=utf-8')
                except (OSError,TypeError): return self.json(503,{'ok':False,'error':'registration_unavailable'})
            if access_file is not None and path=='/lab-app/auth/logout':
                if not self.authorized(): return self.json(401,{'ok':False,'error':'unauthorized'})
                self.send_response(303);self.send_header('Set-Cookie',f'{SESSION_COOKIE}=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax');self.send_header('Location','/lab-app');self.send_header('Cache-Control','no-store');self.send_header('Content-Length','0');self.end_headers();return
            if not self.authorized(): return self.json(401,{'ok':False,'error':'unauthorized'})
            if path != '/lab-app/api': return self.json(404, {'ok': False, 'error': 'not_found'})
            action = request.get('action')
            if action == 'load':
                if access_file is not None:
                    return self.json(200, {**payload, 'data': {**payload['data'], 'pilot_user': self.pilot_user}})
                return self.json(200, payload)
            if action == 'event':
                return self.json(200, {'ok': True, 'stats': payload['data']['stats'], 'preview': True})
            return self.json(200, {'ok': False, 'error': 'not_available_in_isolated_sandbox'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--access-file', type=Path, default=os.environ.get('EGE_LAB_ACCESS_FILE') or None, help='Optional pilot user file; configured but unreadable means deny all access')
    args = parser.parse_args()
    html, payload, health = load_bundle(args.bundle)
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(html, payload, health, args.access_file)) as server:
        server.daemon_threads = True
        print(json.dumps(health), flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
