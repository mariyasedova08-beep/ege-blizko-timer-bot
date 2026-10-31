"""Install opt-in notifications only; never enable them or restore production DB."""
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path('/opt/bots/ege-blizko')
BACKUP = Path('/mnt/ege-notify-backup-20261031-141647')
REF = 'cb77f76715f43f9779b3a11e180b94a08015e15f'
BASE = 'https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/' + REF + '/'
NAMES = ('run_bot_live10.py', 'run_bot_live24.py', 'probnik_result_notify.py')

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def once(text, old, new):
    require(text.count(old) == 1, 'Unexpected source layout; installation cancelled')
    return text.replace(old, new, 1)

def patch10(text):
    require('probnik_result_notify' not in text, 'Notification integration already present; inspect first')
    tree = ast.parse(text)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'save_probnik_sync')
    lines = text.splitlines(keepends=True)
    original = ''.join(lines[fn.lineno-1:fn.end_lineno])
    require('publication_status' not in original, 'Publication guard already present; inspect first')
    guard = '''                publication_status = str(result.get("publication_status") or "legacy").strip().lower()
                if publication_status not in {"опубликовано", "legacy"}:
                    continue
'''
    updated = once(original, '                conn.execute(\n', guard + '                conn.execute(\n')
    queue = '''                if publication_status == "опубликовано":
                    probnik_notice.queue_publication(
                        conn, student_name=student_name, event_name=event_name,
                        event_date=event_date, new_primary=primary,
                        new_secondary=secondary,
                    )
'''
    updated = once(updated, '                rows_saved += 1\n', queue + '                rows_saved += 1\n')
    changed = ''.join(lines[:fn.lineno-1]) + updated + ''.join(lines[fn.end_lineno:])
    return once(changed, 'import run_bot_live9\n', 'import run_bot_live9\nimport probnik_result_notify as probnik_notice\n')

def patch24(text):
    require('probnik_result_notify' not in text, 'Dispatcher integration already present; inspect first')
    text = once(text, 'import run_bot_live23\n', 'import run_bot_live23\nimport probnik_result_notify as probnik_notice\n')
    anchor = '    application.job_queue.run_repeating(live6.tutor_reminder_tick, interval=30, first=10)'
    return once(text, anchor, '    application.job_queue.run_repeating(probnik_notice.dispatch_pending, interval=60, first=25)\n' + anchor)

def install_file(path, content, metadata):
    fd, name = tempfile.mkstemp(prefix='.probnik-install-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chown(name, metadata.st_uid, metadata.st_gid)
        os.chmod(name, metadata.st_mode & 0o777)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def wait_for_health(timeout=600):
    deadline = time.monotonic() + timeout
    next_report = 0
    while time.monotonic() < deadline:
        require(subprocess.run(['systemctl', 'is-active', '--quiet', 'ege-blizko.service']).returncode == 0, 'Service failed during startup')
        try:
            with urlopen('http://127.0.0.1:8080/health', timeout=3) as response:
                if response.status == 200 and json.load(response).get('ok') is True:
                    return
        except (OSError, ValueError):
            pass
        now = time.monotonic()
        if now >= next_report:
            print('WAITING_FOR_HTTP: service active; startup in progress', flush=True)
            next_report = now + 15
        time.sleep(2)
    raise RuntimeError('HTTP startup deadline exceeded; restore original files')


def main():
    require(os.geteuid() == 0, 'Run as root')
    require(BACKUP.is_dir(), 'Verified backup not found')
    cfg = json.loads((ROOT / 'runtime-vars.json').read_text())
    require(str(cfg.get('PROBNIK_RESULT_NOTIFY_ENABLED', '')).strip() != '1', 'Notifications must remain disabled')
    service_env = subprocess.check_output(['systemctl', 'show', 'ege-blizko.service', '-p', 'Environment', '--value'], text=True)
    require('PROBNIK_RESULT_NOTIFY_ENABLED=1' not in shlex.split(service_env), 'Service enables notifications; stop')
    require(subprocess.run(['systemctl', 'is-active', '--quiet', 'ege-blizko.service']).returncode == 0, 'Bot is not active')
    old = {name: (ROOT / name).read_bytes() if (ROOT / name).exists() else None for name in NAMES}
    if old['probnik_result_notify.py'] is not None:
        existing = old['probnik_result_notify.py']
        blob = b'blob ' + str(len(existing)).encode() + b'\0' + existing
        require(hashlib.sha1(blob).hexdigest() == 'aeea548ef21b6c22b2f8aaacd7d34d5f50b8bee6', 'Existing notification module differs; inspect first')
    for name in NAMES[:2]:
        require((BACKUP / name).is_file() and old[name] == (BACKUP / name).read_bytes(), 'Live source differs from verified backup; stop')
    with sqlite3.connect((BACKUP / 'database.sqlite3').as_uri() + '?mode=ro', uri=True) as c:
        require(c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Backup integrity check failed')
    staged = {NAMES[0]: patch10(old[NAMES[0]].decode()).encode(), NAMES[1]: patch24(old[NAMES[1]].decode()).encode()}
    for name in ('probnik_result_notify.py', 'tests/test_probnik_result_notify.py'):
        with urlopen(BASE + name, timeout=30) as r:
            content = r.read()
        # Pinned Git blob identity additionally verifies the downloaded source.
        expected = {'probnik_result_notify.py': 'aeea548ef21b6c22b2f8aaacd7d34d5f50b8bee6', 'tests/test_probnik_result_notify.py': 'b4c1424c869b391748f18b4e3c0d7802605e5d17'}[name]
        blob = b'blob ' + str(len(content)).encode() + b'\0' + content
        require(hashlib.sha1(blob).hexdigest() == expected, 'Downloaded source identity differs')
        staged[name] = content
    with tempfile.TemporaryDirectory(prefix='ege-notify-stage-') as temp:
        work = Path(temp)
        for name, content in staged.items():
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            compile(content, name, 'exec')
        subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_probnik_result_notify.py', '-v'], cwd=work, check=True, env={**os.environ, 'PROBNIK_RESULT_NOTIFY_ENABLED': '0'})
    for name in NAMES:
        require(((ROOT / name).read_bytes() if (ROOT / name).exists() else None) == old[name], 'Source changed during preparation; stop')
    metadata = {name: (ROOT / name).stat() if old[name] is not None else (ROOT / 'run_bot_live10.py').stat() for name in NAMES}
    rollback = BACKUP / 'rollback-notification-files.py'
    rollback.write_text('''import os, shutil, subprocess
from pathlib import Path
root=Path("/opt/bots/ege-blizko")
backup=Path("/mnt/ege-notify-backup-20261031-141647")
for name in ("run_bot_live10.py", "run_bot_live24.py"):
    original=root/name
    meta=original.stat()
    shutil.copyfile(backup/name, original)
    os.chown(original, meta.st_uid, meta.st_gid)
    os.chmod(original, meta.st_mode & 0o777)
# The newly added module is inert after both integration files are restored.
subprocess.run(["systemctl", "restart", "ege-blizko.service"], check=True)
print("ROLLBACK_FILES_RESTORED; database not changed")
''')
    rollback.chmod(0o600)
    touched = []
    try:
        for name in NAMES:
            touched.append(name)
            install_file(ROOT / name, staged[name], metadata[name])
        subprocess.run(['systemctl', 'restart', 'ege-blizko.service'], check=True, timeout=60)
        wait_for_health()
        # Configuration on disk remains unchanged; no queue is activated.
        require(json.loads((ROOT / 'runtime-vars.json').read_text()) == cfg, 'Configuration changed unexpectedly')
    except BaseException:
        for name in touched:
            if old[name] is not None:
                install_file(ROOT / name, old[name], metadata[name])
        subprocess.run(['systemctl', 'restart', 'ege-blizko.service'], timeout=60, check=False)
        print('ROLLBACK_FILES_RESTORED: checking HTTP recovery', flush=True)
        try:
            wait_for_health()
        except Exception:
            print('ROLLBACK_HTTP_NOT_READY: original files restored; service needs investigation', flush=True)
            raise
        print('ROLLBACK_VERIFIED: original integration files restored; health OK; database untouched')
        raise
    print('INSTALLED_DISABLED: 3 files only; service active; health OK; no student messages enabled')
    print('Rollback:', rollback)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # No credential-bearing URL or configuration value in diagnostics.
        print('STOP:', type(exc).__name__)
        if isinstance(exc, RuntimeError):
            print(str(exc))
        sys.exit(1)
