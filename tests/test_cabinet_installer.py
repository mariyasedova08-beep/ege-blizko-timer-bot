import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cabinet_installer',ROOT/'deploy/install_cabinet_snapshot.py')
i = importlib.util.module_from_spec(spec); spec.loader.exec_module(i)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name)/'app'; self.app.mkdir()
        self.db = self.app/'db.sqlite'; self.state = Path(self.temp.name)/'backup'
        self.october = self.app/'october_2026_close.py'
        self.original = b'_INSTALLED=False\ndef install():\n    global _INSTALLED\n    _INSTALLED = True\n'
        self.october.write_bytes(self.original); self.october.chmod(0o640)
        self.target = self.app/'cabinet_schedule_snapshot.py'
        (self.app/'runtime-vars.json').write_text(json.dumps({'BOT_TOKEN':'test-not-a-token','COREAPP_DB_PATH':str(self.db)}))
        with sqlite3.connect(self.db) as connection:
            connection.execute('CREATE TABLE students(active,course_id,telegram_user_id)')
            connection.executemany('INSERT INTO students VALUES(1,?,?)',
                [('6a8c4641d6c9f299cf1387a6',uid) for uid in (101,102)])
            connection.execute('CREATE TABLE payments(value)')
            connection.execute('INSERT INTO payments VALUES(123)')
        self.guards = patch.multiple(i,APP=self.app,DB=self.db,STATE=self.state,
            OCTOBER=self.october,TARGET=self.target,OLD_HASH=i.digest(self.original))
        self.guards.start(); self.addCleanup(self.guards.stop)
        self.commands = []
        def command(args):
            self.commands.append(args)
            return 'ege-bot' if 'User' in args else 'active'
        self.runner = patch.object(i,'run',side_effect=command); self.runner.start();self.addCleanup(self.runner.stop)
        self.health = patch.object(i,'healthy');self.health.start();self.addCleanup(self.health.stop)
        self.api = patch.object(i,'api_check');self.api_mock=self.api.start();self.addCleanup(self.api.stop)

    def test_apply_checks_teacher_and_two_students_preserves_database_and_mode(self):
        before = self.db.read_bytes()
        i.apply()
        self.assertEqual(self.october.read_bytes(),i.transform(self.original))
        self.assertEqual(self.target.read_bytes(),i.MODULE)
        self.assertEqual(self.october.stat().st_mode & 0o777,0o640)
        self.assertEqual(self.db.read_bytes(),before)
        self.assertEqual([c.args[1] for c in self.api_mock.call_args_list],['admin','student','student'])
        self.assertTrue((self.state/'database.sqlite').is_file())

    def test_failed_api_rolls_back_code_without_replacing_new_payments(self):
        def fail(*args):
            with sqlite3.connect(self.db) as connection:
                connection.execute('INSERT INTO payments VALUES(456)')
            raise TimeoutError()
        self.api_mock.side_effect=fail
        with self.assertRaisesRegex(RuntimeError,'AUTO_ROLLBACK_COMPLETED'): i.apply()
        self.assertEqual(self.october.read_bytes(),self.original)
        self.assertFalse(self.target.exists())
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute('SELECT value FROM payments').fetchall(),[(123,),(456,)])

    def test_repeat_has_no_restart_and_manual_rollback_restores(self):
        i.apply(); self.commands.clear(); i.apply()
        self.assertFalse(any('restart' in command for command in self.commands))
        i.restore()
        self.assertEqual(self.october.read_bytes(),self.original)
        self.assertFalse(self.target.exists())

    def test_unknown_source_is_not_touched(self):
        self.october.write_bytes(self.original+b'# private change\n')
        with self.assertRaisesRegex(RuntimeError,'SOURCE_CHANGED'): i.apply()
        self.assertFalse(self.state.exists())

    def test_rollback_refuses_subsequent_changes(self):
        i.apply(); self.target.write_bytes(b'# newer module\n')
        with self.assertRaisesRegex(RuntimeError,'MODULE_CHANGED'): i.restore()

    def test_embedded_sources_equal_reviewed_files(self):
        self.assertEqual(i.MODULE,(ROOT/'cabinet_schedule_snapshot.py').read_bytes())
        self.assertEqual(i.PATCHER,(ROOT/'deploy/cabinet_snapshot_patch.py').read_bytes())


if __name__=='__main__': unittest.main()
