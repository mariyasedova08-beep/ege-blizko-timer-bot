import base64
from datetime import datetime
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, Mock
import os

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('installer',ROOT/'deploy/install_october_close.py')
i=importlib.util.module_from_spec(s);s.loader.exec_module(i)

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.app=Path(self.tmp.name);self.db=self.app/'db.sqlite'
        with sqlite3.connect(self.db) as c:
            c.executescript('''CREATE TABLE students(active,course_id,telegram_user_id);
CREATE TABLE ege11_trainer_assignment_periods(code,starts_at,ends_at);
CREATE TABLE payments(amount); INSERT INTO payments VALUES(100);
INSERT INTO ege11_trainer_assignment_periods VALUES('acid','2026-10-01',NULL);''')
            c.executemany('INSERT INTO students VALUES(1,?,?)',[(i.COURSE,uid) for uid in range(101,114)])
            c.execute("INSERT INTO students VALUES(1,'other-course',999)")
        ctx=patch.multiple(i,APP=self.app,DB=self.db,STATE=self.app/'backup');ctx.start();self.addCleanup(ctx.stop)
        if os.geteuid()!=0:
            ctx=patch.object(i.os,'fchown');ctx.start();self.addCleanup(ctx.stop)
    def test_embedded_release_matches_reviewed_sources(self):
        self.assertEqual(i.MODULE,(ROOT/'october_2026_close.py').read_bytes())
        self.assertEqual(i.TRANSFORM_CODE,(ROOT/'deploy/october_close_patch.py').read_bytes())
        i.module_namespace()
    def test_cohort_is_exactly_thirteen_unique_course_students(self):
        self.assertEqual(i.cohort(),list(range(101,114)))
        with sqlite3.connect(self.db) as c:c.execute('INSERT INTO students VALUES(1,?,?)',(i.COURSE,101))
        self.assertEqual(len(i.cohort()),13)
        with sqlite3.connect(self.db) as c:c.execute('INSERT INTO students VALUES(1,?,?)',(i.COURSE,114))
        with self.assertRaisesRegex(ValueError,'THIRTEEN'):i.cohort()
    def test_queue_has_one_course_and_thirteen_personal_messages_disabled_until_files_ready(self):
        n=i.module_namespace();i.prepare_queue(n,{'chat_id':'-100123','thread_id':'7'},i.cohort())
        with sqlite3.connect(self.db) as c:
            self.assertEqual(dict(c.execute('SELECT kind,count(*) FROM october_2026_deliveries GROUP BY kind')),{'course':1,'student':13})
            cfg=dict(c.execute('SELECT key,value FROM october_2026_config'))
            self.assertEqual(cfg['enabled'],'0');self.assertEqual(cfg['notice_at'],'2026-10-27T19:00:00+03:00')
        i.enable(True)
        i.enable(False)
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM october_2026_deliveries WHERE status='cancelled'").fetchone()[0],14)
            self.assertEqual(c.execute('SELECT sum(amount) FROM payments').fetchone()[0],100)
    def test_online_backup_does_not_lose_later_payments(self):
        i.STATE.mkdir();i.database_backup()
        with sqlite3.connect(self.db) as c:c.execute('INSERT INTO payments VALUES(200)')
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT sum(amount) FROM payments').fetchone()[0],300)
        with sqlite3.connect(i.STATE/'database.sqlite') as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_atomic_preserves_mode_and_owner(self):
        path=self.app/'file.py';path.write_bytes(b'old');path.chmod(0o640);info=path.stat()
        i.atomic(path,b'new',{'uid':info.st_uid,'gid':info.st_gid,'mode':0o640})
        self.assertEqual(path.read_bytes(),b'new');self.assertEqual(path.stat().st_mode&0o777,0o640)
        self.assertEqual(path.stat().st_uid,info.st_uid)
    def test_changed_source_rejected_before_backup_or_restart(self):
        (self.app/'kulek_rewards.py').write_bytes(b'unknown production edit')
        with patch.object(i,'datetime') as dt,patch.object(i,'restart') as restart:
            dt.now.return_value=datetime(2026,10,26,tzinfo=i.ZoneInfo('Europe/Moscow'))
            dt.side_effect=datetime
            with self.assertRaisesRegex(ValueError,'PRODUCTION_VERSION_UNREVIEWED'):i.apply()
            restart.assert_not_called();self.assertFalse(i.STATE.exists())

class FullReleaseTests(unittest.TestCase):
    setUp = InstallerTests.setUp
    def prepare_source(self):
        fixture=("async def monthly_close_tick(context):\n"+'''    now = datetime.now(bot.TIMEZONE)
    if now.day != 1 or now.time() < time(9, 0):
        return
    key = previous_month_key(_month_key())
'''+"    pass\n\nasync def breakthrough_prompt_tick(context):\n"+'''    now = datetime.now(bot.TIMEZONE)
    if now.day != 1 or now.time() < time(9, 0):
        return
    key = previous_month_key(_month_key())
'''+"    pass\n\ndef install():\n    current = month_payload(_month_key(), force=True)\n").encode()
        target=self.app/'kulek_rewards.py';target.write_bytes(fixture);target.chmod(0o640)
        pins={i.digest(fixture):i.digest(i.transform(fixture))}
        contexts=[patch.object(i,'PINS',pins),patch.object(i,'config',return_value={'chat_id':'-100123','thread_id':'7'}),
            patch.object(i,'run',side_effect=lambda args:'ege-bot' if 'User' in args else 'active'),
            patch.object(i,'datetime')]
        for ctx in contexts:
            value=ctx.start();self.addCleanup(ctx.stop)
            if ctx is contexts[-1]:
                value.now.return_value=datetime(2026,10,26,tzinfo=i.ZoneInfo('Europe/Moscow'));value.side_effect=datetime
        return fixture,target
    def test_success_repeat_and_manual_rollback_keep_later_payment(self):
        original,target=self.prepare_source()
        with patch.object(i,'restart') as restart,patch.object(i,'healthy',return_value=True):
            i.apply();i.apply()
            self.assertEqual(restart.call_count,1)
            with sqlite3.connect(self.db) as c:c.execute('INSERT INTO payments VALUES(200)')
            i.apply(rollback=True)
            self.assertEqual(target.read_bytes(),original)
            self.assertEqual(target.stat().st_mode&0o777,0o640)
            self.assertFalse((self.app/'october_2026_close.py').exists())
            with sqlite3.connect(self.db) as c:
                self.assertEqual(c.execute('SELECT sum(amount) FROM payments').fetchone()[0],300)
                self.assertEqual(c.execute("SELECT value FROM october_2026_config WHERE key='enabled'").fetchone()[0],'0')
    def test_failed_health_automatically_rolls_back_and_disables_queue(self):
        original,target=self.prepare_source()
        with patch.object(i,'restart'),patch.object(i,'healthy',side_effect=[False,True]):
            with self.assertRaisesRegex(ValueError,'HEALTH_OR_STARTUP'):i.apply()
        self.assertEqual(target.read_bytes(),original)
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute("SELECT count(*) FROM october_2026_deliveries WHERE status='pending'").fetchone()[0],0)
    def test_error_after_target_rename_is_rolled_back(self):
        original,target=self.prepare_source();actual=i.atomic;failed=False
        def atomic(path,data,metadata):
            nonlocal failed
            actual(path,data,metadata)
            if path==target and data!=original and not failed:
                failed=True;raise OSError('simulated directory fsync failure')
        with patch.object(i,'atomic',side_effect=atomic),patch.object(i,'restart'),patch.object(i,'healthy',return_value=True):
            with self.assertRaises(OSError):i.apply()
        self.assertEqual(target.read_bytes(),original)

if __name__=='__main__':unittest.main()
