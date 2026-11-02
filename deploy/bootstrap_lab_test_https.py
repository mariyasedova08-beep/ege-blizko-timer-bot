#!/usr/bin/env python3
"""Add ONLY the separate laboratory HTTPS virtual host, with checked rollback."""
import argparse
import configparser
from datetime import datetime, timezone
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.request

DOMAIN = 'lab-test.77-233-212-200.sslip.io'
IP = '77.233.212.200'
NAME = 'ege-lab-sandbox-test'
BASE = Path('/var/lib/ege-lab-test-https')
CONF = Path('/etc/nginx/conf.d/ege-lab-sandbox-test.conf')
HOOK = Path('/usr/local/libexec/ege-lab-test-tls-reload')
LINEAGE = Path('/etc/letsencrypt/live') / NAME
RENEWAL = Path('/etc/letsencrypt/renewal') / (NAME + '.conf')
EXISTING = ('77-233-212-200.sslip.io', 'lms-77-233-212-200.sslip.io', 'prepodmin.77-233-212-200.sslip.io')
EXPECTED_BUNDLE = '8dd56a65fd1f1530c91ce93cf19cc048c056011d4ee44407064330abd54360ee'
EXPECTED_HTML = '82990efffb6dcf224b0de5e85271d860a0001050153ef09412846f08658f6fac'
MARKER = '# EGE_LAB_TEST_HTTPS_MANAGED_V1'
HTTP2 = False
TLS_BIND = "443"
HOOK_TEXT = '''#!/bin/sh
set -eu
[ "${RENEWED_LINEAGE:-}" = /etc/letsencrypt/live/ege-lab-sandbox-test ] || exit 0
/usr/sbin/nginx -t
/usr/bin/systemctl reload nginx
'''


def configuration(tls, http2=None, bind=None):
    listen = (TLS_BIND if bind is None else bind) + " ssl" + (" http2" if (HTTP2 if http2 is None else http2) else "")
    challenge = f'''    location ^~ /.well-known/acme-challenge/ {{
        root {BASE}/acme;
        default_type text/plain;
        try_files $uri =404;
    }}'''
    http_default = f'    location / {{ return 308 https://{DOMAIN}$request_uri; }}' if tls else '    location / { return 503 "Test HTTPS setup in progress\\n"; }'
    result = f'''{MARKER}
server {{
    listen 80;
    server_name {DOMAIN};
{challenge}
{http_default}
}}
'''
    if tls:
        result += f'''server {{
    listen {listen};
    server_name {DOMAIN};
    ssl_certificate {LINEAGE}/fullchain.pem;
    ssl_certificate_key {LINEAGE}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:LAB_TEST_TLS:1m;
    ssl_session_tickets off;
    server_tokens off;
    add_header X-Robots-Tag "noindex, noarchive" always;
    client_max_body_size 64k;
    location = / {{ return 302 /lab-app; }}
    location / {{
        proxy_pass http://127.0.0.1:8768;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
    }}
}}
'''
    return result


def managed_configs():
    return {configuration(False)} | {configuration(True,http2,bind) for http2 in (False,True) for bind in ("443",IP+":443")}


def existing_tls_bind(dump):
    explicit=r'^\s*listen\s+'+re.escape(IP)+r':443(?:\s|;)'
    return IP+':443' if re.search(explicit,dump,re.M) else '443'


def existing_http2(dump,bind='443'):
    address=r'(?:0\.0\.0\.0:)?443' if bind=='443' else re.escape(bind)
    flags=re.findall(r'^\s*listen\s+'+address+r'(?:\s+([^;]+))?;',dump,re.M)
    if any('proxy_protocol' in (line or '').split() for line in flags):
        raise RuntimeError('existing IPv4 TLS listener requires PROXY protocol; automatic setup refused')
    return any('http2' in (line or '').split() for line in flags)


def run(*args, timeout=40):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Do not dump nginx -T or certificate/account data into public reports.
        if args[0]=='certbot':
            message=(result.stdout+result.stderr).lower()
            if 'rate' in message and ('limit' in message or 'too many' in message):
                raise RuntimeError('CERTBOT_RATE_LIMITED: test virtual host will be rolled back')
            if 'unauthorized' in message or 'challenge failed' in message:
                raise RuntimeError('CERTBOT_CHALLENGE_FAILED: check inbound HTTP for the test hostname')
        raise RuntimeError('command failed: ' + args[0] + ' (exit ' + str(result.returncode) + ')')
    return result.stdout


def check_dir(path):
    if path.is_symlink():
        raise ValueError('symlink directory refused: ' + str(path))
    if path.exists() and (not path.is_dir() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022):
        raise ValueError('untrusted directory: ' + str(path))


def atomic(path, data, mode=0o644):
    check_dir(path.parent)
    if path.is_symlink():
        raise ValueError('symlink file refused: ' + str(path))
    fd, temp = tempfile.mkstemp(prefix='.lab-https-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def config_hashes(dump):
    result = {}
    for name in re.findall(r'^# configuration file (.+):$', dump, re.M):
        path = Path(name)
        if path != CONF:
            result[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def verify_unchanged(before):
    for name, expected in before.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('an existing nginx config changed; refusing further action')


def tls_request(host, path='/', method='GET', body=None):
    context = ssl.create_default_context()
    with socket.create_connection((IP,443),timeout=5) as raw:
        with context.wrap_socket(raw,server_hostname=host) as sock:
            fingerprint = hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()
            content = body or b''
            request = f'{method} {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\nContent-Length: {len(content)}\r\nContent-Type: application/json\r\n\r\n'.encode() + content
            sock.sendall(request)
            response = http.client.HTTPResponse(sock);response.begin()
            data = response.read(4_000_001)
            if len(data)>4_000_000:raise ValueError('response too large')
            return response.status, fingerprint, data


def production_status():
    result = {}
    for host in EXISTING:
        try:
            status,fingerprint,_=tls_request(host)
            result[host]={'status':status,'certificate_sha256':fingerprint}
        except Exception as error:
            result[host]={'unavailable':type(error).__name__}
    return result


def assert_production_same(before):
    if production_status()!=before:
        raise RuntimeError('existing HTTPS status or certificate changed')


def account_id():
    root=Path('/etc/letsencrypt/accounts/acme-v02.api.letsencrypt.org/directory')
    accounts=[p.name for p in root.glob('*') if p.is_dir() and not p.is_symlink() and re.fullmatch('[a-f0-9]{32}',p.name)]
    if len(accounts)!=1:
        raise RuntimeError('expected one existing Let\'s Encrypt account; no account registration or terms acceptance performed')
    return accounts[0]


def certbot_command(account):
    return ['certbot','certonly','--config',str(BASE/'certbot.ini'),
            '--non-interactive','--webroot','--webroot-path',str(BASE/'acme'),
            '--preferred-challenges','http','--cert-name',NAME,'-d',DOMAIN,
            '--account',account,'--server','https://acme-v02.api.letsencrypt.org/directory',
            '--keep-until-expiring','--no-directory-hooks',
            '--work-dir',str(BASE/'work'),'--logs-dir',str(BASE/'logs'),
            '--deploy-hook',str(HOOK)]


def reload_checked(hashes):
    verify_unchanged(hashes)
    run('nginx','-t')
    run('systemctl','reload','nginx')


def restore(folder):
    if folder.parent!=BASE/'backups' or folder.is_symlink():raise ValueError('invalid backup')
    receipt=json.loads((folder/'receipt.json').read_bytes())
    for name,path,mode in (('config',CONF,0o644),('hook',HOOK,0o755)):
        if path.is_symlink():raise ValueError('unexpected symlink during rollback')
        if receipt['had_'+name]:
            atomic(path,(folder/name).read_bytes(),mode)
        elif path.exists():
            expected=HOOK_TEXT if name=='hook' else None
            text=path.read_text()
            if (name=='hook' and text!=expected) or (name=='config' and text not in managed_configs()):
                raise RuntimeError('unknown file during rollback')
            path.unlink()
    # Disable auto-renewal only for the newly created test certificate.
    # Certificate/key files themselves are retained, never deleted or revoked.
    if not receipt['had_renewal'] and RENEWAL.exists():
        if RENEWAL.is_symlink():raise ValueError('unexpected renewal symlink')
        os.replace(RENEWAL,folder/'new-test-renewal.disabled')
    reload_checked(receipt['config_hashes'])
    assert_production_same(receipt['production'])
    print('TEST_HTTPS_ROLLBACK_COMPLETE')


def verify_sandbox():
    code,_,body=tls_request(DOMAIN,'/healthz')
    health=json.loads(body)
    if code!=200 or health.get('sandbox') is not True or health.get('bundle_sha256')!=EXPECTED_BUNDLE:
        raise RuntimeError('wrong sandbox health over HTTPS')
    code,_,body=tls_request(DOMAIN,'/lab-app')
    if code!=200 or hashlib.sha256(body).hexdigest()!=EXPECTED_HTML:
        raise RuntimeError('wrong HTML over HTTPS')
    code,_,body=tls_request(DOMAIN,'/lab-app/api','POST',b'{"action":"load"}')
    api=json.loads(body)
    if code!=200 or not api.get('ok') or api['data']['coverage']!={'substances':219,'reactions':1424,'medium_reactions':96}:
        raise RuntimeError('wrong chemistry API over HTTPS')
    return health


def certificate_usable():
    cert=LINEAGE/'fullchain.pem'
    if not cert.is_file() or not (LINEAGE/'privkey.pem').is_file():
        return False
    # Check the certificate on disk before changing the TLS virtual host.
    hostname=run('openssl','x509','-in',str(cert),'-noout','-checkhost',DOMAIN).strip()
    # OpenSSL x509 can exit zero even when its checkhost result is negative.
    if hostname!='Hostname '+DOMAIN+' does match certificate':
        raise RuntimeError('saved test certificate hostname does not match')
    check=subprocess.run(['openssl','x509','-in',str(cert),'-noout','-checkend',str(30*86400)],capture_output=True,text=True,timeout=10)
    return check.returncode==0


def validate_saved_renewal(content):
    parser=configparser.ConfigParser(interpolation=None)
    parser.read_string('[lineage]\n'+content)
    for key in ('cert','privkey','chain','fullchain'):
        if parser.get('lineage',key,fallback='')!=str(LINEAGE/(key+'.pem')):
            raise ValueError('saved renewal belongs to another certificate')
    if parser.get('lineage','archive_dir',fallback='')!=str(Path('/etc/letsencrypt/archive')/NAME):
        raise ValueError('saved renewal archive differs')
    if parser.get('renewalparams','authenticator',fallback='')!='webroot':
        raise ValueError('saved renewal does not use webroot')
    for key in ('pre_hook','post_hook'):
        if parser.get('renewalparams',key,fallback='').strip():
            raise ValueError('unexpected saved certificate hook')
    hook=parser.get('renewalparams','deploy_hook',fallback='').strip()
    if hook and hook!=str(HOOK):raise ValueError('unexpected deploy hook')


def restore_test_renewal():
    if RENEWAL.exists():return
    backups=sorted((BASE/'backups').glob('*/new-test-renewal.disabled'))
    if not backups:
        if LINEAGE.exists():raise RuntimeError('test certificate exists but its saved renewal configuration was not found')
        return
    source=backups[-1]
    if source.is_symlink() or source.stat().st_uid!=os.geteuid():
        raise ValueError('untrusted saved test renewal')
    content=source.read_text()
    validate_saved_renewal(content)
    atomic(RENEWAL,content.encode(),0o600)
    print('SAVED_TEST_RENEWAL_RESTORED',flush=True)


def ensure_test_certificate(account):
    restore_test_renewal()
    if certificate_usable():
        print('REUSING_VALID_TEST_CERTIFICATE',flush=True)
        return
    run(*certbot_command(account),timeout=240)
    if not certificate_usable():raise RuntimeError('issued test certificate is not usable')


def wait_for_sandbox(attempts=20,delay=1):
    # systemctl reload returns before nginx has necessarily replaced workers.
    # Every attempt still checks the CA chain, hostname, HTML and API.
    last=None
    for attempt in range(attempts):
        try:return verify_sandbox()
        except (OSError,ValueError,RuntimeError,http.client.HTTPException) as error:
            last=error
            if attempt+1<attempts:time.sleep(delay)
    raise RuntimeError('new HTTPS virtual host did not become ready; rolling back') from last


def main():
    global HTTP2, TLS_BIND
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rollback',action='store_true')
    args=parser.parse_args()
    if os.geteuid()!=0:raise SystemExit('ROOT_CONSOLE_REQUIRED')
    for command in ('nginx','certbot','systemctl','openssl'):
        if not shutil.which(command):raise SystemExit('MISSING_PROGRAM: '+command)
    lock_fd=os.open('/run/lock/ege-lab-test-https.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(lock_fd,'a+') as lock:
        if os.fstat(lock.fileno()).st_uid!=0:raise SystemExit('UNTRUSTED_INSTALL_LOCK')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        check_dir(BASE)
        if args.rollback:
            backups=sorted((BASE/'backups').glob('*/receipt.json'))
            if not backups:raise SystemExit('NO_TEST_HTTPS_BACKUP')
            restore(backups[-1].parent);return
        run('nginx','-t')
        check_dir(CONF.parent);check_dir(HOOK.parent)
        if CONF.is_symlink() or (CONF.exists() and CONF.read_text() not in managed_configs()):
            raise SystemExit('UNKNOWN_EXISTING_TEST_CONFIG_REFUSED')
        if HOOK.is_symlink() or (HOOK.exists() and HOOK.read_text()!=HOOK_TEXT):
            raise SystemExit('UNKNOWN_EXISTING_CERTIFICATE_HOOK_REFUSED')
        dump=run('nginx','-T')
        TLS_BIND=existing_tls_bind(dump)
        HTTP2=existing_http2(dump,TLS_BIND)
        if not CONF.exists() and any(DOMAIN in line.split() for line in re.findall(r'^\s*server_name\s+([^;]+);',dump,re.M)):
            raise SystemExit('TEST_HOSTNAME_ALREADY_CONFIGURED_ELSEWHERE')
        addresses={x[4][0] for x in socket.getaddrinfo(DOMAIN,443)}
        if addresses!={IP}:raise SystemExit('TEST_DNS_DOES_NOT_MATCH_SERVER')
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8768/healthz',timeout=3) as response:
            health=json.load(response)
        if health.get('bundle_sha256')!=EXPECTED_BUNDLE:raise SystemExit('EXPECTED_SANDBOX_NOT_RUNNING')
        account=account_id()  # Reuse existing account, no new terms accepted.
        if (LINEAGE.exists() or RENEWAL.exists()) and not (BASE/'owned-certificate.json').is_file():
            raise SystemExit('UNMANAGED_EXISTING_CERTIFICATE_NAME_REFUSED')
        hashes=config_hashes(dump)
        before=production_status()
        for path in (BASE,BASE/'backups',BASE/'acme',BASE/'work',BASE/'logs'):
            check_dir(path);path.mkdir(mode=0o755,exist_ok=True);os.chmod(path,0o755 if path.name=='acme' or path==BASE else 0o700)
        folder=BASE/'backups'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(3))
        folder.mkdir(mode=0o700)
        receipt={'had_config':CONF.exists(),'had_hook':HOOK.exists(),'had_renewal':RENEWAL.exists(), 'config_hashes':hashes,'production':before}
        for name,path in (('config',CONF),('hook',HOOK)):
            if path.exists():atomic(folder/name,path.read_bytes(),0o600)
        atomic(folder/'receipt.json',json.dumps(receipt).encode(),0o600)
        atomic(BASE/'installer.py',Path(__file__).read_bytes(),0o600)
        atomic(BASE/'certbot.ini',b'# Separate lab certificate; no global CLI hooks or nginx installer.\n',0o600)
        atomic(BASE/'owned-certificate.json',json.dumps({'domain':DOMAIN,'cert_name':NAME}).encode(),0o600)
        print('TEST_HTTPS_BACKUP: '+str(folder),flush=True)
        try:
            atomic(HOOK,HOOK_TEXT.encode(),0o755)
            atomic(CONF,configuration(False).encode())
            reload_checked(hashes)
            assert_production_same(before)
            # Verify this exact new virtual host serves its challenge webroot.
            token=secrets.token_hex(16)
            challenge=BASE/'acme/.well-known/acme-challenge'
            for path in (BASE/'acme/.well-known',challenge):
                check_dir(path);path.mkdir(mode=0o755,exist_ok=True);os.chmod(path,0o755)
            probe=challenge/token
            atomic(probe,token.encode())
            try:
                connection=http.client.HTTPConnection('127.0.0.1',80,timeout=5)
                connection.request('GET','/.well-known/acme-challenge/'+token,headers={'Host':DOMAIN})
                reply=connection.getresponse()
                if reply.status!=200 or reply.read(200)!=token.encode():raise RuntimeError('challenge route failed')
                connection.close()
            finally:probe.unlink(missing_ok=True)
            ensure_test_certificate(account)
            atomic(CONF,configuration(True).encode())
            reload_checked(hashes)
            result=wait_for_sandbox()
            assert_production_same(before)
            print(json.dumps({'ok':True,'build':result['build'],'url':'https://'+DOMAIN+'/lab-app'},sort_keys=True))
            print('TEST_HTTPS_READY_EXISTING_ROUTES_UNCHANGED')
        except BaseException:
            restore(folder)
            raise


if __name__=='__main__':main()
