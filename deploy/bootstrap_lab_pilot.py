#!/usr/bin/env python3
"""Install and gate ONLY the isolated Timeweb lab. No invitations or production."""
from datetime import datetime, timezone
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

REPOSITORY='mariyasedova08-beep/ege-blizko-timer-bot'
INSTALLER_COMMIT='a57fb9a804ebdb1b042bd3b9251b48f267a3873a'
RUNTIME_COMMIT='754a1e8c33e4f225ecdeccc4cc5f863947d9e4b6'
PINS={
 'bootstrap_lab_sandbox.py':'a51dc49870e0215ae1ae9c85537b108d333521e5b2773fa12c3735a1eee40efe',
 'lab_pilot_access.py':'a8ab294c99aa09ced02debfb41ebe5ae1592e72741aa6e5edc44b5d6187010e3',
 'lab_sandbox_server.py':'48eda362805eb73f2b9a02365609e5af811792dccdbdb5c8648094edd0b1a0df',
}
BASE=Path('/var/lib/ege-lab-sandbox')
USERS=BASE/'access/users.json'
DROPIN=Path('/etc/systemd/system/ege-lab-sandbox-preview.service.d/30-pilot-access.conf')
ADMIN=BASE/'admin'
URL='https://lab-test.77-233-212-200.sslip.io'
USERNAME='maria'
GATE=('# EGE_LAB_PILOT_ACCESS_V1\n[Service]\nExecStart=\n'
      'ExecStart=/usr/bin/python3 -I /var/lib/ege-lab-sandbox/current/server.py '
      '--bundle /var/lib/ege-lab-sandbox/current/bundle.json --port 8768 '
      '--access-file /var/lib/ege-lab-sandbox/access/users.json\n')


def download(name):
    commit=INSTALLER_COMMIT if name=='bootstrap_lab_sandbox.py' else RUNTIME_COMMIT
    url=f'https://raw.githubusercontent.com/{REPOSITORY}/{commit}/deploy/{name}'
    with urllib.request.urlopen(url,timeout=40) as response:
        data=response.read(1_000_001)
    if len(data)>1_000_000 or hashlib.sha256(data).hexdigest()!=PINS[name]:
        raise ValueError('ARTIFACT_DIGEST_MISMATCH: '+name)
    return data


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def request(path,password=None,body=None):
    headers={'Content-Type':'application/json'}
    if password is not None:
        headers['Authorization']='Basic '+base64.b64encode((USERNAME+':'+password).encode()).decode()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    req=urllib.request.Request(URL+path,data=body,headers=headers)
    try:
        with opener.open(req,timeout=15) as response:
            if response.url!=URL+path:raise ValueError('UNEXPECTED_REDIRECT')
            return response.status,response.read(4_000_001)
    except urllib.error.HTTPError as error:
        return error.code,error.read(1000)


def verify(installer,password,fetch=request):
    for path,body in [('/lab-app',None),('/lab-app/api',b'{"action":"load"}')]:
        if fetch(path,body=body)[0]!=401:
            raise ValueError('ANONYMOUS_ACCESS_NOT_BLOCKED')
        if fetch(path,password=password+'wrong',body=body)[0]!=401:
            raise ValueError('WRONG_PASSWORD_NOT_BLOCKED')
    code,html=fetch('/lab-app',password=password)
    if code!=200 or hashlib.sha256(html).hexdigest()!=installer.EXPECTED_HTML:
        raise ValueError('AUTHENTICATED_HTML_MISMATCH')
    code,raw=fetch('/lab-app/api',password=password,body=b'{"action":"load"}')
    payload=json.loads(raw)
    if code!=200 or payload.get('ok') is not True or payload['data'].get('pilot_user')!=USERNAME or payload['data'].get('preview') is not True:
        raise ValueError('AUTHENTICATED_API_MISMATCH')
    installer.health()


def enable(installer,access,artifacts,fetch=request):
    # Refuse to replace existing pilot credentials or a manually configured gate.
    for path in (USERS,DROPIN,ADMIN):
        if path.exists() or path.is_symlink():raise ValueError('EXISTING_PILOT_CONFIGURATION_REFUSED')
    if installer.UNIT_PATH.is_symlink() or installer.UNIT_PATH.read_text()!=installer.UNIT:
        raise ValueError('UNKNOWN_SANDBOX_SERVICE')
    for folder in (BASE,USERS.parent,DROPIN.parent):
        installer.trusted_directory(folder)
    previous=installer.current_target()
    active=installer.run('systemctl','is-active','--quiet',installer.UNIT_NAME,check=False).returncode==0
    enabled=installer.run('systemctl','is-enabled','--quiet',installer.UNIT_NAME,check=False).returncode==0
    backup=installer.backup(previous,active,enabled)
    print('PILOT_BACKUP: '+str(backup),flush=True)
    password=secrets.token_urlsafe(24)
    owned_users=None;owned_admin=False;owned_gate=False
    try:
        installer.main()
        access.update(USERS,USERNAME,days=30,password=password)
        owned_users=USERS.read_bytes()
        USERS.parent.chmod(0o755)
        ADMIN.mkdir(mode=0o755);owned_admin=True
        for name in ('lab_pilot_access.py','lab_sandbox_server.py'):
            installer.write_atomic(ADMIN/name,artifacts[name],0o755 if name=='lab_pilot_access.py' else 0o644)
        DROPIN.parent.mkdir(parents=True,exist_ok=True)
        installer.write_atomic(DROPIN,GATE.encode(),0o644);owned_gate=True
        installer.run('systemctl','daemon-reload')
        installer.run('systemctl','restart',installer.UNIT_NAME)
        last_error=None
        for attempt in range(4):
            try:
                verify(installer,password,fetch);last_error=None;break
            except Exception as error:
                last_error=error
                if attempt<3:time.sleep(1)
        if last_error is not None:raise last_error
        installer.write_atomic(backup/'pilot-receipt.json',json.dumps({'protected':True,'createdAt':datetime.now(timezone.utc).isoformat(),'username':USERNAME,'build':installer.EXPECTED_BUILD}).encode(),0o600)
    except BaseException:
        # Only remove files created by this transaction; unknown concurrent changes stay gated.
        installer.run('systemctl','stop',installer.UNIT_NAME,check=False)
        if owned_gate:
            if DROPIN.read_bytes()!=GATE.encode():raise RuntimeError('PILOT_GATE_CHANGED_MANUAL_REVIEW_REQUIRED')
            DROPIN.unlink()
        if owned_users is not None:
            if USERS.read_bytes()!=owned_users:raise RuntimeError('PILOT_USERS_CHANGED_MANUAL_REVIEW_REQUIRED')
            USERS.unlink()
        if owned_admin:
            for name in ('lab_pilot_access.py','lab_sandbox_server.py'):
                path=ADMIN/name
                if path.exists() and path.read_bytes()==artifacts[name]:path.unlink()
            ADMIN.rmdir()
        installer.restore(backup)
        print('PILOT_ROLLBACK_COMPLETE_PREVIOUS_SANDBOX_RESTORED',flush=True)
        raise
    # Print only after authenticated TLS and anonymous-denial checks have passed.
    print('PROTECTED_PILOT_READY '+URL+'/lab-app')
    print('USERNAME: '+USERNAME)
    print('PASSWORD_SHOW_ONCE: '+password)
    print('EXPIRES_IN_DAYS: 30')
    print('NO_INVITATIONS_SENT_NO_PRODUCTION_DEPLOYMENT_PERFORMED')


def main():
    if os.geteuid()!=0:raise SystemExit('ROOT_CONSOLE_REQUIRED')
    artifacts={name:download(name) for name in PINS}
    with tempfile.TemporaryDirectory(prefix='ege-lab-pilot-') as folder:
        root=Path(folder)
        for name,content in artifacts.items():(root/name).write_bytes(content)
        # Imports are pinned sandbox-only standard-library files, never the bot.
        sys.path.insert(0,str(root))
        import lab_pilot_access as access
        spec=importlib.util.spec_from_file_location('pilot_installer',root/'bootstrap_lab_sandbox.py')
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        enable(installer,access,artifacts)


if __name__=='__main__':main()
