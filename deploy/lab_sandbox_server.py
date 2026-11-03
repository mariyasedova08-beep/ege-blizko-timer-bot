#!/usr/bin/env python3
"""Loopback-only laboratory UI/chemistry sandbox. No bot imports or databases."""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hmac
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
import zlib

MAX_BUNDLE = 8_000_000
MAX_CONTENT = 12_000_000


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
        if config.get('version') != 1 or not isinstance(config.get('users'), dict):
            return False
        user = config['users'].get(username)
        if not isinstance(user, dict) or user.get('revoked') is not False or float(user.get('expires', 0)) <= time.time():
            return False
        salt, digest = user.get('salt', ''), user.get('digest', '')
        if not re.fullmatch(r'[0-9a-f]{32}', salt) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            return False
        return hmac.compare_digest(access_password(password, salt), digest)
    except (OSError, ValueError, TypeError, UnicodeError):
        return False


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
            self.end_headers()
            self.wfile.write(body)

        def json(self, code, data):
            self.send(code, json.dumps(data, ensure_ascii=False).encode())

        def authorized(self):
            if access_file is None:
                return True
            if access_allowed(self.headers.get('Authorization', ''), access_file):
                self.pilot_user = base64.b64decode(self.headers['Authorization'][6:]).decode('utf-8').split(':', 1)[0]
                return True
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="EGE BLIZKO pilot", charset="UTF-8"')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', '0')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            return False

        def do_GET(self):
            path = urlsplit(self.path).path
            if path != '/healthz' and not self.authorized():
                return
            if path == '/lab-app':
                return self.send(200, html, 'text/html; charset=utf-8')
            if path == '/healthz':
                return self.json(200, health)
            return self.json(404, {'ok': False, 'error': 'not_found'})

        def do_POST(self):
            if not self.authorized():
                return
            if urlsplit(self.path).path != '/lab-app/api':
                return self.json(404, {'ok': False, 'error': 'not_found'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 50_000:
                    raise ValueError('length')
                request = json.loads(self.rfile.read(size))
                if not isinstance(request, dict):
                    raise ValueError('request object required')
            except (ValueError, UnicodeError):
                return self.json(400, {'ok': False, 'error': 'invalid_request'})
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
