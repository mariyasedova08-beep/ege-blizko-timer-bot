"""Explicit activation: baseline historical notices, enable flag, restart one bot."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path('/opt/bots/ege-blizko')
EVENT = ('ПРОБНИК №1', '31.10.2026')
CUTOFF = datetime.strptime(EVENT[1], '%d.%m.%Y').date()


def historical_rows(conn):
    rows = conn.execute('''SELECT student_name,event_name,event_date
        FROM probnik_results WHERE primary_score IS NOT NULL OR secondary_score IS NOT NULL''').fetchall()
    previous = []
    current = 0
    for name, event, day in rows:
        date = datetime.strptime(day, '%d.%m.%Y').date()
        if date < CUTOFF:
            previous.append((name, event, day))
        elif date == CUTOFF:
            if (event, day) != EVENT:
                raise RuntimeError('Unexpected event on activation date; inspect first')
            current += 1
        else:
            raise RuntimeError('Future scored result exists; inspect before activation')
    if not current:
        raise RuntimeError('Published October results missing; stop')
    return previous, current


def baseline_history(conn, rows):
    conn.execute('''CREATE TABLE IF NOT EXISTS probnik_result_notice_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fingerprint TEXT NOT NULL UNIQUE,
        student_name TEXT NOT NULL,event_name TEXT NOT NULL,event_date TEXT NOT NULL,
        created_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',sent_at TEXT,reason TEXT)''')
    if conn.execute("SELECT COUNT(*) FROM probnik_result_notice_queue WHERE status='pending'").fetchone()[0]:
        raise RuntimeError('Existing pending notices require review; stop')
    for name, event, day in rows:
        key = hashlib.sha256(json.dumps([name,event,day],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        conn.execute('''INSERT OR IGNORE INTO probnik_result_notice_queue
            (fingerprint,student_name,event_name,event_date,created_at,status,reason)
            VALUES (?,?,?,?,?,'skipped','historical_before_activation')''',
            (key,name,event,day,datetime.now(timezone.utc).isoformat()))


def main():
    if len(sys.argv) != 3 or sys.argv[1] != '--apply':
        raise RuntimeError('Explicit --apply and verified installer path required')
    installer = Path(sys.argv[2])
    if hashlib.sha256(installer.read_bytes()).hexdigest() != 'e936da24b9f4e4e93839362b0fb360b9e2c6605e2ff786c3279a7225d215e92a':
        raise RuntimeError('Installer identity differs')
    spec = importlib.util.spec_from_file_location('guarded_installer', installer)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    for name, patcher in [('run_bot_live10.py',guard.patch10),('run_bot_live24.py',guard.patch24)]:
        if (ROOT/name).read_bytes() != patcher((guard.BACKUP/name).read_text()).encode():
            raise RuntimeError('Live integration source differs; stop')
    module = (ROOT/'probnik_result_notify.py').read_bytes()
    blob = b'blob '+str(len(module)).encode()+b'\0'+module
    if hashlib.sha1(blob).hexdigest() != 'aeea548ef21b6c22b2f8aaacd7d34d5f50b8bee6':
        raise RuntimeError('Notification module differs; stop')
    guard.wait_for_health(timeout=15)
    config_path = ROOT/'runtime-vars.json'
    old_config = config_path.read_bytes()
    cfg = json.loads(old_config)
    if str(cfg.get('PROBNIK_RESULT_NOTIFY_ENABLED','')).strip() == '1':
        raise RuntimeError('Already enabled; inspect first')
    if not cfg.get('COREAPP_DB_PATH'):
        raise RuntimeError('Database path missing')
    db = Path(cfg['COREAPP_DB_PATH'])
    if not db.is_absolute(): db=ROOT/db
    if not db.is_file(): raise RuntimeError('Database missing')
    os.umask(0o077)
    backup=Path('/mnt')/datetime.now(timezone.utc).strftime('ege-notify-activation-%Y%m%d-%H%M%S')
    backup.mkdir(mode=0o700)
    (backup/'runtime-vars.json').write_bytes(old_config)
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as source:
        past,current=historical_rows(source)
        with sqlite3.connect(backup/'database.sqlite3') as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise RuntimeError('Backup invalid')
    print('BACKUP_VERIFIED:',backup,flush=True)
    print('Historical results excluded:',len(past),'October scored results:',current,flush=True)
    with sqlite3.connect(db) as conn:
        # Recheck under the write transaction before changing any queue rows.
        conn.execute('BEGIN IMMEDIATE')
        past,current=historical_rows(conn)
        baseline_history(conn,past)
    cfg['PROBNIK_RESULT_NOTIFY_ENABLED']='1'
    if config_path.read_bytes()!=old_config: raise RuntimeError('Configuration changed concurrently; stop')
    changed=json.dumps(cfg,ensure_ascii=False,indent=2).encode()+b'\n'
    meta=config_path.stat()
    guard.install_file(config_path,changed,meta)
    try:
        subprocess.run(['systemctl','restart','ege-blizko.service'],check=True,timeout=60)
        guard.wait_for_health()
    except BaseException:
        guard.install_file(config_path,old_config,meta)
        subprocess.run(['systemctl','restart','ege-blizko.service'],check=False,timeout=60)
        guard.wait_for_health()
        print('ACTIVATION_ROLLED_BACK: original config restored; historical exclusions retained; database results untouched',flush=True)
        raise
    print('NOTIFICATIONS_ENABLED: health OK; run one Sheets sync to queue October publications',flush=True)

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('STOP:',type(exc).__name__)
        if isinstance(exc,RuntimeError): print(str(exc))
        sys.exit(1)
