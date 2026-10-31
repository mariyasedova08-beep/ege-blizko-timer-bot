"""Explicit parent-result activation with optional October-only backfill."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from urllib.request import urlopen

ROOT=Path('/opt/bots/ege-blizko')
BASE='https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/6067fbb4d8c89d146438dd417c347f39297923ef/'
BLOBS={
 'probnik_parent_notify.py':'63a8e50571f3d18fef27f5239d18adddcd742786',
 'probnik_result_notify.py':'0bef0020d16503f15abb89d50252979423df64d9',
 'tests/test_probnik_parent_notify.py':'23e5f6b15a252fa3b07b065d23f586e60bc0d04a',
 'tests/test_probnik_result_notify.py':'b4c1424c869b391748f18b4e3c0d7802605e5d17',
}


def identity(data):
 return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def activate_config(cfg, when, include_october=False):
 if str(cfg.get('PROBNIK_RESULT_NOTIFY_ENABLED','')).strip()!='1':
  raise RuntimeError('Student notifications are not enabled; stop')
 if str(cfg.get('PROBNIK_PARENT_NOTIFY_ENABLED','')).strip()=='1':
  raise RuntimeError('Parent notifications already enabled; inspect first')
 if when.tzinfo is None: raise RuntimeError('Activation time must have a timezone')
 return {**cfg,'PROBNIK_PARENT_NOTIFY_ENABLED':'1',
         'PROBNIK_PARENT_NOTIFY_SINCE':when.astimezone(timezone.utc).isoformat(),
         'PROBNIK_PARENT_OCTOBER_2026_BACKFILL':'1' if include_october else '0'}


def main():
 if len(sys.argv) not in (3,4) or sys.argv[1]!='--apply' or (len(sys.argv)==4 and sys.argv[3]!='--include-october'):
  raise RuntimeError('Explicit --apply and verified helper path required')
 include_october = len(sys.argv)==4
 if os.geteuid()!=0:raise RuntimeError('Run as root')
 helper=Path(sys.argv[2])
 if hashlib.sha256(helper.read_bytes()).hexdigest()!='e936da24b9f4e4e93839362b0fb360b9e2c6605e2ff786c3279a7225d215e92a':
  raise RuntimeError('Helper identity differs')
 spec=importlib.util.spec_from_file_location('parent_release_guard',helper)
 guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
 guard.wait_for_health(timeout=15)
 current=(ROOT/'probnik_result_notify.py').read_bytes()
 if identity(current)!='aeea548ef21b6c22b2f8aaacd7d34d5f50b8bee6':
  raise RuntimeError('Live student module differs; preserve and inspect it')
 config_path=ROOT/'runtime-vars.json';original_config=config_path.read_bytes()
 cfg=json.loads(original_config)
 activate_config(cfg,datetime.now(timezone.utc),include_october)  # validate without enabling
 db=Path(cfg['COREAPP_DB_PATH'])
 if not db.is_absolute():db=ROOT/db
 if not db.is_file():raise RuntimeError('Database missing')
 with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
  cols={r[1] for r in conn.execute('PRAGMA table_info(parent_links)')}
  if not {'student_id','active'}<=cols or not ({'parent_telegram_user_id','telegram_user_id'}&cols):
   raise RuntimeError('Unsupported parent links; stop')
  count,children=conn.execute('SELECT COUNT(*),COUNT(DISTINCT student_id) FROM parent_links WHERE active=1').fetchone()
  if not count:raise RuntimeError('No verified active parents')
  if include_october:
   october=conn.execute('''SELECT COUNT(*) FROM probnik_result_notice_queue n
       JOIN probnik_results r ON r.student_name=n.student_name
         AND r.event_name=n.event_name AND r.event_date=n.event_date
       WHERE n.event_name='ПРОБНИК №1' AND n.event_date='31.10.2026'
         AND n.status IN ('pending','sent','blocked')
         AND (r.primary_score IS NOT NULL OR r.secondary_score IS NOT NULL)''').fetchone()[0]
   if not october:raise RuntimeError('No verified October publications in student queue; stop')
   print('OCTOBER_PUBLICATIONS_FOR_PARENT_BACKFILL:',october,flush=True)
 print('ACTIVE_PARENT_LINKS:',count,'CHILDREN:',children,flush=True)
 contents={}
 for name,expected in BLOBS.items():
  with urlopen(BASE+name,timeout=30) as response:data=response.read()
  if identity(data)!=expected:raise RuntimeError('Downloaded source identity differs')
  compile(data,name,'exec');contents[name]=data
 old={name:(ROOT/name).read_bytes() if (ROOT/name).exists() else None
      for name in ('probnik_result_notify.py','probnik_parent_notify.py')}
 if old['probnik_parent_notify.py'] is not None and old['probnik_parent_notify.py']!=contents['probnik_parent_notify.py']:
  raise RuntimeError('Different parent module already exists')
 with tempfile.TemporaryDirectory(prefix='parent-notice-tests-') as folder:
  for name,data in contents.items():
   target=Path(folder)/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
  subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_probnik*notify.py','-v'],cwd=folder,check=True)
 os.umask(0o077)
 backup=Path('/mnt')/datetime.now(timezone.utc).strftime('ege-parent-notify-backup-%Y%m%d-%H%M%S')
 backup.mkdir(mode=0o700)
 (backup/'runtime-vars.json').write_bytes(original_config)
 for name,data in old.items():
  if data is not None:(backup/name).write_bytes(data)
 with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as source:
  with sqlite3.connect(backup/'database.sqlite3') as target:
   source.backup(target)
   if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Invalid backup')
 print('BACKUP_VERIFIED:',backup,flush=True)
 if config_path.read_bytes()!=original_config:raise RuntimeError('Config changed concurrently; stop')
 for name,data in old.items():
  actual=(ROOT/name).read_bytes() if (ROOT/name).exists() else None
  if actual!=data:raise RuntimeError('Source changed concurrently; stop')
 metadata={name:(ROOT/name).stat() if data is not None else (ROOT/'probnik_result_notify.py').stat() for name,data in old.items()}
 config_meta=config_path.stat()
 # Record a cutoff immediately before the change. Never replay earlier notices.
 activated=activate_config(cfg,datetime.now(timezone.utc),include_october)
 config_bytes=(json.dumps(activated,ensure_ascii=False,indent=2)+'\n').encode()
 manifest={'files':list(old),'new_parent_module':old['probnik_parent_notify.py'] is None,
           'activation_since':activated['PROBNIK_PARENT_NOTIFY_SINCE'],
           'october_backfill':include_october}
 (backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
 try:
  # Both flag changes are confined to the runtime JSON; student flag is preserved.
  guard.install_file(ROOT/'probnik_parent_notify.py',contents['probnik_parent_notify.py'],metadata['probnik_parent_notify.py'])
  guard.install_file(ROOT/'probnik_result_notify.py',contents['probnik_result_notify.py'],metadata['probnik_result_notify.py'])
  guard.install_file(config_path,config_bytes,config_meta)
  subprocess.run(['systemctl','restart','ege-blizko.service'],check=True,timeout=60)
  guard.wait_for_health()
 except BaseException:
  guard.install_file(config_path,original_config,config_meta)
  for name,data in old.items():
   if data is not None:guard.install_file(ROOT/name,data,metadata[name])
  # A newly added parent module is inert after restoring the original hook/flag.
  subprocess.run(['systemctl','restart','ege-blizko.service'],check=False,timeout=60)
  guard.wait_for_health()
  print('ROLLBACK_VERIFIED: student module and config restored; results database not restored or rewritten',flush=True)
  raise
 print('PARENT_NOTIFICATIONS_ENABLED: HTTP OK; student notices unchanged',flush=True)
 if include_october:print('OCTOBER_PARENT_BACKFILL_ENABLED: only ПРОБНИК №1 / 31.10.2026; per-parent duplicate protection',flush=True)
 print('Activation cutoff:',activated['PROBNIK_PARENT_NOTIFY_SINCE'],flush=True)

if __name__=='__main__':
 try:main()
 except Exception as exc:
  print('STOP:',type(exc).__name__)
  if isinstance(exc,RuntimeError):print(str(exc))
  sys.exit(1)
