#!/usr/bin/env python3
"""Safely update only the existing isolated lab pilot with invitation login."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

REPOSITORY='mariyasedova08-beep/ege-blizko-timer-bot'
RUNTIME_COMMIT='76e3c2f4b6007218cdbfb96fe791a91221535cbd'
PINS={
    'lab_sandbox_server.py':'0241b3db862a4f40febcb03a92798815a2b25624f9cca5aa8e40ac16b904fd40',
    'lab_pilot_access.py':'dc262147a0b64b255cbe9d3065efd43e2ec2aee17e78de0de430f11fe4f799c7',
}
BASE=Path('/var/lib/ege-lab-sandbox')
USERS=BASE/'access/users.json'
CURRENT=BASE/'current/server.py'
ADMIN=BASE/'admin'
UNIT='ege-lab-sandbox-preview.service'
URL='https://lab-test.77-233-212-200.sslip.io'
GATE=Path('/etc/systemd/system/ege-lab-sandbox-preview.service.d/30-pilot-access.conf')
EXPECTED_GATE=('# EGE_LAB_PILOT_ACCESS_V1\n[Service]\nExecStart=\n'
 'ExecStart=/usr/bin/python3 -I /var/lib/ege-lab-sandbox/current/server.py '
 '--bundle /var/lib/ege-lab-sandbox/current/bundle.json --port 8768 '
 '--access-file /var/lib/ege-lab-sandbox/access/users.json\n')

def download(name):
    url=f'https://raw.githubusercontent.com/{REPOSITORY}/{RUNTIME_COMMIT}/deploy/{name}'
    with urllib.request.urlopen(url,timeout=40) as response: data=response.read(1_000_001)
    if len(data)>1_000_000 or hashlib.sha256(data).hexdigest()!=PINS[name]:
        raise ValueError('ARTIFACT_DIGEST_MISMATCH: '+name)
    return data

def atomic(path,data,mode):
    fd,name=tempfile.mkstemp(prefix='.lab-invites-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream: stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,mode);os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def run(*args,check=True): return subprocess.run(args,check=check,capture_output=True,text=True,timeout=40)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def public_request(path,method='GET',body=None,cookie=None):
    headers={}
    if body is not None:headers['Content-Type']='application/json'
    if cookie:headers['Cookie']=cookie
    req=urllib.request.Request(URL+path,data=body,headers=headers,method=method)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(req,timeout=15) as response:return response.status,response.headers,response.read(4_000_001)
    except urllib.error.HTTPError as error:return error.code,error.headers,error.read(4000)

def verify():
    status,_,body=public_request('/lab-app')
    if status!=200 or 'Войди в аккаунт преподавателя'.encode() not in body or b'LAB_APP' in body:
        raise ValueError('PUBLIC_LOGIN_PAGE_CHECK_FAILED')
    status,_,_=public_request('/lab-app/api','POST',b'{"action":"load"}')
    if status!=401:raise ValueError('ANONYMOUS_API_ACCESS_NOT_BLOCKED')
    status,_,body=public_request('/healthz')
    health=json.loads(body)
    if status!=200 or health.get('ok') is not True or health.get('sandbox') is not True:
        raise ValueError('SANDBOX_HEALTH_CHECK_FAILED')

def main():
    if os.geteuid()!=0:raise SystemExit('ROOT_CONSOLE_REQUIRED')
    if not USERS.is_file() or USERS.is_symlink():raise SystemExit('PILOT_USERS_FILE_NOT_FOUND_OR_UNSAFE')
    os.chmod(USERS,0o600)
    if not GATE.is_file() or GATE.is_symlink() or GATE.read_text()!=EXPECTED_GATE:
        raise SystemExit('PILOT_GATE_MISMATCH_REFUSING_TO_TOUCH_SERVICE')
    unit_path=Path('/etc/systemd/system')/(UNIT)
    if not unit_path.is_file() or unit_path.is_symlink() or '127.0.0.1:8768' not in unit_path.read_text():
        raise SystemExit('UNKNOWN_SANDBOX_UNIT')
    current_dir=CURRENT.parent.resolve()
    if not current_dir.is_dir() or BASE.resolve() not in current_dir.parents:
        raise SystemExit('SANDBOX_CURRENT_PATH_INVALID')
    if not CURRENT.is_file() or CURRENT.is_symlink():raise SystemExit('SANDBOX_SERVER_FILE_INVALID')
    if not ADMIN.is_dir() or ADMIN.is_symlink():raise SystemExit('PILOT_ADMIN_DIRECTORY_MISSING')
    for name in PINS:
        target=ADMIN/name
        if not target.is_file() or target.is_symlink():raise SystemExit('PILOT_ADMIN_FILE_MISSING: '+name)
    artifacts={name:download(name) for name in PINS}
    paths={CURRENT:CURRENT.read_bytes(),**{ADMIN/name:(ADMIN/name).read_bytes() for name in PINS}}
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=BASE/'backups'/f'{stamp}-invite-login'
    backup.mkdir(mode=0o700,parents=True,exist_ok=False)
    for path,data in paths.items():
        relative=Path('current/server.py') if path==CURRENT else Path('admin')/path.name
        (backup/relative).parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        (backup/relative).write_bytes(data)
    print('INVITE_UPDATE_BACKUP:',backup,flush=True)
    changed=[]
    try:
        atomic(CURRENT,artifacts['lab_sandbox_server.py'],0o644);changed.append(CURRENT)
        for name in PINS:
            target=ADMIN/name;atomic(target,artifacts[name],0o755 if name=='lab_pilot_access.py' else 0o644);changed.append(target)
        run('systemctl','restart',UNIT)
        last=None
        for attempt in range(5):
            try:verify();last=None;break
            except Exception as error:
                last=error
                if attempt<4:time.sleep(1)
        if last:raise last
        (backup/'receipt.json').write_text(json.dumps({'sandbox_only':True,'installed_at':datetime.now(timezone.utc).isoformat(),'runtime_commit':RUNTIME_COMMIT,'files':{str(p):hashlib.sha256(v).hexdigest() for p,v in artifacts.items()}},sort_keys=True))
        print('INVITE_LOGIN_READY',URL+'/lab-app')
        print('CREATE_ONE_USE_LINK: /var/lib/ege-lab-sandbox/admin/lab_pilot_access.py invite --days 7')
        print('SANDBOX_ONLY_NO_PRODUCTION_CHANGE')
    except BaseException:
        run('systemctl','stop',UNIT,check=False)
        for path in reversed(changed):
            relative=Path('current/server.py') if path==CURRENT else Path('admin')/path.name
            atomic(path,(backup/relative).read_bytes(),0o755 if path.name=='lab_pilot_access.py' else 0o644)
        run('systemctl','restart',UNIT,check=False)
        print('INVITE_UPDATE_ROLLED_BACK_FROM_BACKUP')
        raise

if __name__=='__main__':main()
