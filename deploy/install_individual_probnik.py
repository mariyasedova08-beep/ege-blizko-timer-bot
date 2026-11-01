"""Read-only --check by default; explicit --apply installs a pinned feature."""
import ast
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
SOURCE='https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/ad69d1fc42b7e63b7a57b293f0b506b9b1a813a7/'
GUARD='https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/d57e1291191ec7f47cf97ce05e88875bbb10b93a/deploy/install_probnik_notices_disabled.py'
EXPECTED={
 'individual_probnik.py':'f837299fb45a5cd16fa6021b42ab830bda8df2cc',
 'probnik_result_notify.py':'fb33c10525c99d764e1d4abf16633efd16ac82c3',
 'tests/test_individual_probnik.py':'30122877eeab6a098dcceeacfc0e985d626a35bb',
 'probnik_parent_notify.py':'63a8e50571f3d18fef27f5239d18adddcd742786',
 'tests/test_probnik_parent_notify.py':'23e5f6b15a252fa3b07b065d23f586e60bc0d04a',
 'tests/test_probnik_result_notify.py':'b4c1424c869b391748f18b4e3c0d7802605e5d17',
}


def require(ok,why):
 if not ok:raise RuntimeError(why)


def blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def patch67(text):
 require('individual_probnik' not in text,'Individual integration already exists; inspect first')
 tree=ast.parse(text)
 functions={n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
 require({'_individual_rows','_individual_by_telegram','_individual_by_id','_individuals_text'}<=functions,'Individual source layout differs')
 marker='\n\nif __name__ == "__main__":'
 require(text.count(marker)==1,'Unexpected individual launch layout')
 return text.replace(marker,'\n\nimport sys as _individual_sys\nimport individual_probnik as _individual_probnik\n_individual_probnik.install(_individual_sys.modules[__name__])'+marker)


def matcher():
 import re
 env={'re':re}
 tree=ast.parse((ROOT/'run_bot_live34.py').read_text())
 nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_norm_name']
 require(len(nodes)==1,'Name normalizer missing')
 exec(compile(ast.Module(body=nodes,type_ignores=[]),'<normalizer>','exec'),env)
 from types import SimpleNamespace
 env['live34']=SimpleNamespace(_norm_name=env['_norm_name'])
 tree=ast.parse((ROOT/'run_bot_live56.py').read_text())
 names={'_student_name_candidates','_tokens','unique_probnik_student_match'}
 nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
 require(len(nodes)==3,'Safe student matcher missing')
 exec(compile(ast.Module(body=nodes,type_ignores=[]),'<matcher>','exec'),env)
 return env['_norm_name'],env['unique_probnik_student_match']


def inspect():
 config=ROOT/'runtime-vars.json';raw=config.read_bytes();cfg=json.loads(raw)
 require(str(cfg.get('INDIVIDUAL_PROBNIK_ENABLED','')).strip()!='1','Feature already enabled; do not install twice')
 require(str(cfg.get('PROBNIK_RESULT_NOTIFY_ENABLED','')).strip()=='1','Existing notification tick must be enabled')
 db=Path(cfg['COREAPP_DB_PATH'])
 if not db.is_absolute():db=ROOT/db
 require(db.is_file(),'Configured database missing')
 old={p:(ROOT/p).read_bytes() if (ROOT/p).exists() else None for p in ('run_bot_live67.py','probnik_result_notify.py','individual_probnik.py')}
 require(blob(old['probnik_result_notify.py'])=='0bef0020d16503f15abb89d50252979423df64d9','Student/parent dispatcher differs; preserve current changes')
 patch67(old['run_bot_live67.py'].decode())
 require(old['individual_probnik.py'] is None,'Individual module already present; inspect first')
 normalize,match=matcher()
 with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
  people=conn.execute('SELECT id,display_name,telegram_user_id FROM individual_students WHERE active=1 ORDER BY id').fetchall()
  require(len(people)==2,'Expected exactly Olya and Alina; active individual roster differs')
  aliases=[set(normalize(p[1]).split()) for p in people]
  require(sum('алина' in x for x in aliases)==1 and sum(bool({'оля','ольга'} & x) for x in aliases)==1,'Individual names do not uniquely identify Olya and Alina')
  regular=conn.execute('''SELECT id,coalesce(nullif(display_name,''),nullif(user_name,''),user_email,'Ученик'),
      user_name,user_email,coreapp_user_id,telegram_user_id FROM students WHERE active=1''').fetchall()
  for sid,name,tg in people:
   require(not any(match(name,[row]) for row in regular),'Individual name collides with group student; stop')
   require(tg is None or not any(row[5] is not None and int(row[5])==int(tg) for row in regular),'Individual Telegram is also linked to a group account')
   print('INDIVIDUAL:',name,'| Telegram:', 'linked' if tg is not None else 'not linked',flush=True)
  prior=conn.execute('SELECT DISTINCT student_name FROM probnik_results').fetchall()
  individual_shapes=[(p[0],p[1],p[1],'','',p[2]) for p in people]
  legacy=[name for (name,) in prior if any(match(name,[row]) for row in individual_shapes)]
  print('LEGACY_INDIVIDUAL_NAMES_IN_GROUP_RESULTS:',len(legacy),flush=True)
  require(not legacy,'Individual results already exist in group storage; separate reviewed migration required')
 print('PREFLIGHT_OK: no database writes, no messages, no restart',flush=True)
 return cfg,raw,db,old


def main():
 require(len(sys.argv)==2 and sys.argv[1] in ('--check','--apply'),'Use --check or explicit --apply')
 cfg,original_cfg,db,old=inspect()
 if sys.argv[1]=='--check':return
 require(os.geteuid()==0,'Run release as root')
 with tempfile.TemporaryDirectory(prefix='individual-probnik-release-') as folder:
  work=Path(folder)
  with urlopen(GUARD,timeout=30) as response:guard_data=response.read()
  require(hashlib.sha256(guard_data).hexdigest()=='e936da24b9f4e4e93839362b0fb360b9e2c6605e2ff786c3279a7225d215e92a','Release helper identity differs')
  helper=work/'guard.py';helper.write_bytes(guard_data)
  spec=importlib.util.spec_from_file_location('individual_guard',helper)
  guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
  guard.wait_for_health(timeout=15)
  downloads={}
  for name,expected in EXPECTED.items():
   with urlopen(SOURCE+name,timeout=30) as response:data=response.read()
   require(blob(data)==expected,'Pinned download identity differs')
   downloads[name]=data
   path=work/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
   compile(data,name,'exec')
  patched=patch67(old['run_bot_live67.py'].decode()).encode()
  compile(patched,'run_bot_live67.py','exec')
  subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_*probnik*.py','-v'],cwd=work,check=True)
  os.umask(0o077)
  backup=Path('/mnt')/datetime.now(timezone.utc).strftime('ege-individual-probnik-backup-%Y%m%d-%H%M%S')
  backup.mkdir(mode=0o700);(backup/'runtime-vars.json').write_bytes(original_cfg)
  for name,data in old.items():
   if data is not None:(backup/name).write_bytes(data)
  with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as source:
   with sqlite3.connect(backup/'database.sqlite3') as target:
    source.backup(target);require(target.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Invalid database backup')
  print('BACKUP_VERIFIED:',backup,flush=True)
  require((ROOT/'runtime-vars.json').read_bytes()==original_cfg,'Configuration changed during preparation')
  for name,data in old.items():
   require(((ROOT/name).read_bytes() if (ROOT/name).exists() else None)==data,'Source changed during preparation')
  metadata={name:(ROOT/name).stat() if data is not None else (ROOT/'run_bot_live67.py').stat() for name,data in old.items()}
  configmeta=(ROOT/'runtime-vars.json').stat()
  enabled_cfg={**cfg,'INDIVIDUAL_PROBNIK_ENABLED':'1'}
  replacement=(json.dumps(enabled_cfg,ensure_ascii=False,indent=2)+'\n').encode()
  try:
   guard.install_file(ROOT/'individual_probnik.py',downloads['individual_probnik.py'],metadata['individual_probnik.py'])
   guard.install_file(ROOT/'run_bot_live67.py',patched,metadata['run_bot_live67.py'])
   guard.install_file(ROOT/'probnik_result_notify.py',downloads['probnik_result_notify.py'],metadata['probnik_result_notify.py'])
   guard.install_file(ROOT/'runtime-vars.json',replacement,configmeta)
   subprocess.run(['systemctl','restart','ege-blizko.service'],check=True,timeout=60)
   guard.wait_for_health()
  except BaseException:
   guard.install_file(ROOT/'runtime-vars.json',original_cfg,configmeta)
   for name,data in old.items():
    if data is not None:guard.install_file(ROOT/name,data,metadata[name])
   subprocess.run(['systemctl','restart','ege-blizko.service'],check=False,timeout=60)
   guard.wait_for_health()
   print('ROLLBACK_VERIFIED: original files and flags restored; live database not overwritten',flush=True)
   raise
  print('INDIVIDUAL_PROBNIK_ENABLED: HTTP OK; /start shows Trainers and Probniks; publish and sync after verification',flush=True)
  print('No individual results sent by installer; parent/group records not migrated',flush=True)

if __name__=='__main__':
 try:main()
 except Exception as exc:
  print('STOP:',type(exc).__name__)
  if isinstance(exc,RuntimeError):print(str(exc))
  sys.exit(1)
