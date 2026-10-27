#!/usr/bin/python3
"""Pinned two-file cabinet hotfix; no database or campaign writes."""
import base64
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request

APP = Path('/opt/bots/ege-blizko')
DB = APP/'data/coreapp_webhooks.db'
STATE = Path('/var/lib/ege-cabinet-snapshot-20261027-v2')
OCTOBER = APP/'october_2026_close.py'
TARGET = APP/'cabinet_schedule_snapshot.py'
RELEASE = 'EGE-CABINET-SNAPSHOT-20261027-REVIEWED'
ROLLBACK = RELEASE+'-ROLLBACK'
OLD_HASH = 'a01d6545212e6ed817c895dc459fdcab563a517ae7829372b64ae9401a0af8c2'
MODULE = base64.b64decode('IiIiTWVtb2l6ZSBzY2hlZHVsZSByZWFkcyBvbmx5IHdpdGhpbiBvbmUgcmVhZC1vbmx5IHJlcG9ydC9yZXF1ZXN0LgoKTm8gdGltZS1iYXNlZCBjYWNoZTogYSBzdWJzZXF1ZW50IHJlcXVlc3QgYWx3YXlzIHNlZXMgY29tbWl0dGVkIHRyYW5zZmVycy4KTm8gd3JpdGVzLCBjYW1wYWlnbiBjaGFuZ2VzLCBvciBjaGFuZ2VzIHRvIGFzc2lnbm1lbnQvZWxpZ2liaWxpdHkgcnVsZXMuCiIiIgpmcm9tIGNvbnRleHRsaWIgaW1wb3J0IGNvbnRleHRtYW5hZ2VyCmZyb20gY29udGV4dHZhcnMgaW1wb3J0IENvbnRleHRWYXIKZnJvbSBmdW5jdG9vbHMgaW1wb3J0IHdyYXBzCmltcG9ydCBzeXMKZnJvbSB0aHJlYWRpbmcgaW1wb3J0IFJMb2NrCgpfc25hcHNob3QgPSBDb250ZXh0VmFyKCdlZ2VfY2FiaW5ldF9zY2hlZHVsZV9zbmFwc2hvdCcsIGRlZmF1bHQ9Tm9uZSkKX2xvY2sgPSBSTG9jaygpCgoKZGVmIF9tZW1vaXplKG1vZHVsZSwgbmFtZSk6CiAgICBvcmlnaW5hbCA9IGdldGF0dHIobW9kdWxlLCBuYW1lLCBOb25lKQogICAgaWYgb3JpZ2luYWwgaXMgTm9uZSBvciBnZXRhdHRyKG9yaWdpbmFsLCAnX2VnZV9zY2hlZHVsZV9tZW1vJywgRmFsc2UpOgogICAgICAgIHJldHVybgogICAgQHdyYXBzKG9yaWdpbmFsKQogICAgZGVmIGNhY2hlZCgqYXJncywgKiprd2FyZ3MpOgogICAgICAgIGNhY2hlID0gX3NuYXBzaG90LmdldCgpCiAgICAgICAgaWYgY2FjaGUgaXMgTm9uZToKICAgICAgICAgICAgcmV0dXJuIG9yaWdpbmFsKCphcmdzLCAqKmt3YXJncykKICAgICAgICBrZXkgPSAob3JpZ2luYWwsIGFyZ3MsIHR1cGxlKHNvcnRlZChrd2FyZ3MuaXRlbXMoKSkpKQogICAgICAgIGlmIGtleSBub3QgaW4gY2FjaGU6CiAgICAgICAgICAgIGNhY2hlW2tleV0gPSBvcmlnaW5hbCgqYXJncywgKiprd2FyZ3MpCiAgICAgICAgcmV0dXJuIGNhY2hlW2tleV0KICAgIGNhY2hlZC5fZWdlX3NjaGVkdWxlX21lbW8gPSBUcnVlCiAgICBzZXRhdHRyKG1vZHVsZSwgbmFtZSwgY2FjaGVkKQoKCmRlZiBfcHJlcGFyZSgpOgogICAgIyBMZXNzb24gdHJhbnNmZXIgaW5zdGFsbHMgYWZ0ZXIgcmV3YXJkcyBkdXJpbmcgc3RhcnR1cDsgcmVzb2x2ZSBsYXppbHkuCiAgICB3aXRoIF9sb2NrOgogICAgICAgIHRyYW5zZmVyID0gc3lzLm1vZHVsZXMuZ2V0KCdlZ2UxMV9sZXNzb25fdHJhbnNmZXInKQogICAgICAgIGlmIHRyYW5zZmVyIGlzIG5vdCBOb25lOgogICAgICAgICAgICBmb3IgbmFtZSBpbiAoJ19lZmZlY3RpdmVfZGF0ZXMnLCAnX2VmZmVjdGl2ZV90cmFjaycsICdfZWZmZWN0aXZlX3N1bmRheScpOgogICAgICAgICAgICAgICAgX21lbW9pemUodHJhbnNmZXIsIG5hbWUpCiAgICAgICAgZGVhZGxpbmVzID0gc3lzLm1vZHVsZXMuZ2V0KCdob21ld29ya19kZWFkbGluZV9sb2dpYycpCiAgICAgICAgaWYgZGVhZGxpbmVzIGlzIG5vdCBOb25lOgogICAgICAgICAgICBfbWVtb2l6ZShkZWFkbGluZXMsICdkdWVfbGVzc29uX2Zvcl9zb3VyY2UnKQogICAgICAgICMgQ2FiaW5ldHMgbWF5IGJlIGltcG9ydGVkIGFmdGVyIHRoZSBPY3RvYmVyIHJld2FyZHMgaG9vay4gQmluZCB0aGVpcgogICAgICAgICMgcmVhZCBlbnRyeSBwb2ludHMgd2hlbmV2ZXIgdGhleSBiZWNvbWUgYXZhaWxhYmxlLCB3aXRob3V0IGltcG9ydGluZwogICAgICAgICMgcGFydGlhbGx5IGluaXRpYWxpemVkIGFwcGxpY2F0aW9uIG1vZHVsZXMgb3IgYmxvY2tpbmcgYm90IHN0YXJ0dXAuCiAgICAgICAgZm9yIG1vZHVsZV9uYW1lLCBmdW5jdGlvbiBpbiAoCiAgICAgICAgICAgICgnZWdlX2FkbWluX3dlYmFwcCcsICdfdmlldycpLAogICAgICAgICAgICAoJ2VnZV9zdHVkZW50X3dlYmFwcCcsICdfcGF5bG9hZCcpLAogICAgICAgICk6CiAgICAgICAgICAgIG1vZHVsZSA9IHN5cy5tb2R1bGVzLmdldChtb2R1bGVfbmFtZSkKICAgICAgICAgICAgaWYgbW9kdWxlIGlzIG5vdCBOb25lOgogICAgICAgICAgICAgICAgX3Njb3BlKG1vZHVsZSwgZnVuY3Rpb24pCgoKQGNvbnRleHRtYW5hZ2VyCmRlZiByZWFkX3NuYXBzaG90KCk6CiAgICBfcHJlcGFyZSgpCiAgICBpZiBfc25hcHNob3QuZ2V0KCkgaXMgbm90IE5vbmU6CiAgICAgICAgeWllbGQKICAgICAgICByZXR1cm4KICAgIHRva2VuID0gX3NuYXBzaG90LnNldCh7fSkKICAgIHRyeToKICAgICAgICB5aWVsZAogICAgZmluYWxseToKICAgICAgICBfc25hcHNob3QucmVzZXQodG9rZW4pCgoKZGVmIF9zY29wZShtb2R1bGUsIG5hbWUpOgogICAgb3JpZ2luYWwgPSBnZXRhdHRyKG1vZHVsZSwgbmFtZSwgTm9uZSkKICAgIGlmIG9yaWdpbmFsIGlzIE5vbmUgb3IgZ2V0YXR0cihvcmlnaW5hbCwgJ19lZ2Vfc2NoZWR1bGVfc2NvcGUnLCBGYWxzZSk6CiAgICAgICAgcmV0dXJuCiAgICBAd3JhcHMob3JpZ2luYWwpCiAgICBkZWYgc2NvcGVkKCphcmdzLCAqKmt3YXJncyk6CiAgICAgICAgd2l0aCByZWFkX3NuYXBzaG90KCk6CiAgICAgICAgICAgIHJldHVybiBvcmlnaW5hbCgqYXJncywgKiprd2FyZ3MpCiAgICBzY29wZWQuX2VnZV9zY2hlZHVsZV9zY29wZSA9IFRydWUKICAgIHNldGF0dHIobW9kdWxlLCBuYW1lLCBzY29wZWQpCgoKZGVmIGluc3RhbGwoKToKICAgIHdpdGggX2xvY2s6CiAgICAgICAgcmV3YXJkcyA9IHN5cy5tb2R1bGVzLmdldCgna3VsZWtfcmV3YXJkcycpCiAgICAgICAgaWYgcmV3YXJkcyBpcyBOb25lIG9yIG5vdCBjYWxsYWJsZShnZXRhdHRyKHJld2FyZHMsICdtb250aF9wYXlsb2FkJywgTm9uZSkpOgogICAgICAgICAgICByYWlzZSBSdW50aW1lRXJyb3IoJ0NBQklORVRfU05BUFNIT1RfUkVXQVJEU19NT0RVTEVfTUlTU0lORycpCiAgICAgICAgX3Njb3BlKHJld2FyZHMsICdtb250aF9wYXlsb2FkJykKICAgICAgICBfcHJlcGFyZSgpCiAgICBwcmludCgnQ2FiaW5ldCBzY2hlZHVsZSBzbmFwc2hvdCByZWFkeTogcmVxdWVzdCBzY29wZWQ7IG5vIHBlcnNpc3RlbnQgY2FjaGUnLCBmbHVzaD1UcnVlKQo=')
PATCHER = base64.b64decode('IiIiUHVyZSBzY29wZWQgaG9vayBpbnRvIHRoZSBhbHJlYWR5IGluc3RhbGxlZCBPY3RvYmVyIGV4Y2VwdGlvbi4iIiIKaW1wb3J0IGFzdAoKSE9PSyA9ICcgICAgaW1wb3J0IGNhYmluZXRfc2NoZWR1bGVfc25hcHNob3RcbiAgICBjYWJpbmV0X3NjaGVkdWxlX3NuYXBzaG90Lmluc3RhbGwoKVxuJwoKCmRlZiB0cmFuc2Zvcm0oZGF0YSk6CiAgICBzb3VyY2UgPSBkYXRhLmRlY29kZSgndXRmLTgnKQogICAgdHJlZSA9IGFzdC5wYXJzZShzb3VyY2UpCiAgICBub2RlcyA9IFtuIGZvciBuIGluIHRyZWUuYm9keSBpZiBpc2luc3RhbmNlKG4sIGFzdC5GdW5jdGlvbkRlZikgYW5kIG4ubmFtZSA9PSAnaW5zdGFsbCddCiAgICBpZiBsZW4obm9kZXMpICE9IDE6CiAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignQ0FCSU5FVF9TTkFQU0hPVF9JTlNUQUxMX0FOQ0hPUl9NSVNTSU5HJykKICAgIG5vZGUgPSBub2Rlc1swXQogICAgbGluZXMgPSBzb3VyY2Uuc3BsaXRsaW5lcyhrZWVwZW5kcz1UcnVlKQogICAgc3RhcnQgPSBzdW0obWFwKGxlbiwgbGluZXNbOm5vZGUubGluZW5vIC0gMV0pKQogICAgZW5kID0gc3VtKG1hcChsZW4sIGxpbmVzWzpub2RlLmVuZF9saW5lbm9dKSkKICAgIGZyYWdtZW50ID0gc291cmNlW3N0YXJ0OmVuZF0KICAgIGlmIGZyYWdtZW50LmNvdW50KEhPT0spID09IDE6CiAgICAgICAgcmV0dXJuIGRhdGEKICAgIGFuY2hvciA9ICcgICAgX0lOU1RBTExFRCA9IFRydWVcbicKICAgIGlmIGZyYWdtZW50LmNvdW50KGFuY2hvcikgIT0gMSBvciAnY2FiaW5ldF9zY2hlZHVsZV9zbmFwc2hvdCcgaW4gc291cmNlOgogICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ0NBQklORVRfU05BUFNIT1RfVU5LTk9XTl9TT1VSQ0UnKQogICAgc291cmNlID0gc291cmNlWzpzdGFydF0gKyBmcmFnbWVudC5yZXBsYWNlKGFuY2hvciwgSE9PSyArIGFuY2hvciwgMSkgKyBzb3VyY2VbZW5kOl0KICAgIHJlc3VsdCA9IHNvdXJjZS5lbmNvZGUoJ3V0Zi04JykKICAgIGNvbXBpbGUocmVzdWx0LCAnb2N0b2Jlcl8yMDI2X2Nsb3NlLnB5JywgJ2V4ZWMnKQogICAgcmV0dXJuIHJlc3VsdAo=')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(args):
    return subprocess.check_output(args, stderr=subprocess.PIPE, text=True).strip()


def regular(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise RuntimeError('NON_REGULAR_FILE')


def atomic(path, data, metadata):
    fd, temporary = tempfile.mkstemp(prefix='.cabinet-', dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data); stream.flush()
            os.fchown(stream.fileno(),metadata['uid'],metadata['gid'])
            os.fchmod(stream.fileno(),metadata['mode']); os.fsync(stream.fileno())
        os.replace(temporary,path)
        fd = os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def transform(data):
    namespace = {}
    exec(compile(PATCHER,'cabinet_snapshot_patch.py','exec'),namespace)
    return namespace['transform'](data)


def metadata(path):
    info = path.stat()
    return {'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}


def api_check(settings, kind, uid):
    payload = f'{int(uid)}.{int(time.time())+120}'
    signature = hmac.new(str(settings['BOT_TOKEN']).encode(),
        (f'ege-{kind}-webapp:'+payload).encode(),hashlib.sha256).hexdigest()
    body = json.dumps({'launch':payload+'.'+signature,'view':'home'}).encode()
    request = urllib.request.Request(f'http://127.0.0.1:8080/{kind}-app/api',
        data=body,headers={'Content-Type':'application/json'})
    started = time.monotonic()
    with urllib.request.urlopen(request,timeout=10) as response:
        data = json.loads(response.read())
        if response.status != 200 or data.get('ok') is not True:
            raise RuntimeError('AUTHENTICATED_API_FAILED')
    print(f'CABINET_SNAPSHOT_API_OK kind={kind} seconds={time.monotonic()-started:.3f}',flush=True)


def healthy(require_marker=True):
    deadline = time.monotonic()+60
    while time.monotonic()<deadline:
        try:
            if run(['systemctl','is-active','ege-blizko']) != 'active':
                raise RuntimeError('SERVICE_NOT_ACTIVE')
            with urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3) as r:
                if r.status != 200: raise RuntimeError('HEALTH_FAILED')
            if require_marker:
                invocation = run(['systemctl','show','ege-blizko','-p','InvocationID','--value'])
                journal = run(['journalctl','-u','ege-blizko',
                    '_SYSTEMD_INVOCATION_ID='+invocation,'--no-pager','-o','cat'])
                if 'Cabinet schedule snapshot ready:' not in journal or 'Kulek rewards ready:' not in journal:
                    raise RuntimeError('STARTUP_NOT_READY')
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError('READINESS_TIMEOUT')


def restore():
    regular(STATE/'original.py'); regular(STATE/'metadata.json')
    original = (STATE/'original.py').read_bytes()
    if digest(original) != OLD_HASH:
        raise RuntimeError('BACKUP_SOURCE_MISMATCH')
    regular(OCTOBER)
    if OCTOBER.read_bytes() not in (original,transform(original)):
        raise RuntimeError('ROLLBACK_SOURCE_CHANGED')
    if os.path.lexists(TARGET):
        regular(TARGET)
        if TARGET.read_bytes()!=MODULE: raise RuntimeError('ROLLBACK_MODULE_CHANGED')
    atomic(OCTOBER,original,json.loads((STATE/'metadata.json').read_text()))
    if TARGET.exists(): TARGET.unlink()
    run(['systemctl','restart','ege-blizko']); healthy(False)
    print('CABINET_SNAPSHOT_ROLLBACK_OK_DATABASE_NOT_RESTORED',flush=True)


def apply():
    regular(OCTOBER); regular(DB)
    settings = json.loads((APP/'runtime-vars.json').read_text())
    if not settings.get('BOT_TOKEN') or str(settings.get('COREAPP_DB_PATH')) != str(DB):
        raise RuntimeError('RUNTIME_CONFIGURATION_UNVERIFIED')
    source = OCTOBER.read_bytes()
    if digest(source) != OLD_HASH:
        if STATE.is_dir() and TARGET.is_file() and TARGET.read_bytes()==MODULE:
            original = (STATE/'original.py').read_bytes()
            if digest(original)==OLD_HASH and source==transform(original):
                healthy(); api_check(settings,'admin',1032290944)
                print('CABINET_SNAPSHOT_ALREADY_INSTALLED_NO_RESTART',flush=True);return
        raise RuntimeError('OCTOBER_SOURCE_CHANGED')
    if os.path.lexists(TARGET) or os.path.lexists(STATE):
        raise RuntimeError('DESTINATION_OR_BACKUP_EXISTS')
    if run(['systemctl','is-active','ege-blizko'])!='active' or run([
        'systemctl','show','ege-blizko','-p','User','--value'])!='ege-bot':
        raise RuntimeError('SERVICE_CONFIGURATION_CHANGED')
    compile(MODULE,'cabinet_schedule_snapshot.py','exec')
    updated = transform(source)
    with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as connection:
        students = [int(r[0]) for r in connection.execute('''SELECT DISTINCT telegram_user_id
            FROM students WHERE active=1 AND course_id=? AND telegram_user_id>0
            ORDER BY telegram_user_id LIMIT 2''',('6a8c4641d6c9f299cf1387a6',))]
        if len(students)!=2: raise RuntimeError('LINKED_COURSE_STUDENTS_MISSING')
    STATE.mkdir(mode=0o700)
    info = metadata(OCTOBER)
    (STATE/'original.py').write_bytes(source)
    (STATE/'metadata.json').write_text(json.dumps(info))
    with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as connection:
        with sqlite3.connect(STATE/'database.sqlite') as destination:
            connection.backup(destination)
            if destination.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise RuntimeError('BACKUP_INTEGRITY_FAILED')
    for path in STATE.iterdir(): os.chmod(path,0o600)
    if OCTOBER.read_bytes()!=source: raise RuntimeError('SOURCE_CHANGED_AFTER_BACKUP')
    try:
        stage = 'atomic_files'
        atomic(TARGET,MODULE,{**info,'mode':0o644})
        atomic(OCTOBER,updated,info)
        stage = 'restart_and_startup'
        run(['systemctl','restart','ege-blizko']); healthy()
        stage = 'admin_api'
        api_check(settings,'admin',1032290944)
        stage = 'student_apis'
        for uid in students: api_check(settings,'student',uid)
    except Exception as error:
        print(f'CABINET_SNAPSHOT_RELEASE_FAILURE stage={stage} error={type(error).__name__}',flush=True)
        restore()
        raise RuntimeError('CABINET_SNAPSHOT_RELEASE_FAILED_AUTO_ROLLBACK_COMPLETED') from None
    print('CABINET_SNAPSHOT_RELEASE_OK_BACKUP_ADMIN_AND_TWO_STUDENTS_VERIFIED',flush=True)


def main():
    if os.geteuid()!=0 or len(sys.argv)!=2 or sys.argv[1] not in (RELEASE,ROLLBACK):
        raise RuntimeError('LITERAL_ROOT_ACTION_REQUIRED')
    with open('/run/lock/ege-blizko-autodeploy.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if sys.argv[1]==ROLLBACK: restore()
        else: apply()


if __name__=='__main__':
    try: main()
    except Exception as error:
        print('CABINET_SNAPSHOT_STOPPED: '+type(error).__name__+': '+str(error),file=sys.stderr)
        sys.exit(1)
