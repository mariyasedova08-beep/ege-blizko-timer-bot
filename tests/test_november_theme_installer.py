import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('november_installer',ROOT/'deploy/install_november_theme.py')
i = importlib.util.module_from_spec(spec);spec.loader.exec_module(i)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name)/'app';self.app.mkdir()
        self.state = Path(self.temp.name)/'backup'
        self.originals = {}
        for role,name in i.FILES.items():
            source = ('<!doctype html><html><head><style>.private-autumn{color:tan}</style></head>'
              '<body><main id="app"><div class="top"></div></main>'
              '<script>function renderHome(){};var view="view-home";'
              'var privateFeature="keep";</script></body></html>').encode()
            (self.app/name).write_bytes(source);(self.app/name).chmod(0o640)
            self.originals[role] = source
        self.database = self.app/'payments.sqlite'
        with sqlite3.connect(self.database) as c:
            c.execute('CREATE TABLE payments(value)');c.execute('INSERT INTO payments VALUES(1)')
        self.guards = patch.multiple(i,APP=self.app,STATE=self.state)
        self.guards.start();self.addCleanup(self.guards.stop)
        for name,kwargs in [
            ('health',{}),('credentials',{'return_value':({'BOT_TOKEN':'test'},[101,102])}),
            ('get_page',{'side_effect':lambda role:(self.app/i.FILES[role]).read_bytes()}),
            ('api_check',{})]:
            guard=patch.object(i,name,**kwargs);mock=guard.start();self.addCleanup(guard.stop)
            setattr(self,name+'_mock',mock)

    def test_adds_only_reviewed_blocks_preserves_private_scripts_and_permissions(self):
        before=self.database.read_bytes();i.apply()
        for role,name in i.FILES.items():
            self.assertEqual((self.app/name).read_bytes(),i.transform(self.originals[role],role))
            self.assertEqual((self.state/name).read_bytes(),self.originals[role])
            self.assertEqual((self.app/name).stat().st_mode & 0o777,0o640)
        self.assertEqual(self.database.read_bytes(),before)
        self.assertEqual(self.api_check_mock.call_count,3)

    def test_repeat_is_idempotent(self):
        i.apply();before={p:p.read_bytes() for p in self.state.iterdir()}
        i.apply()
        self.assertEqual({p:p.read_bytes() for p in self.state.iterdir()},before)

    def test_failed_api_rolls_back_without_restoring_new_payments(self):
        def fail(*args):
            with sqlite3.connect(self.database) as c:c.execute('INSERT INTO payments VALUES(2)')
            raise TimeoutError()
        self.api_check_mock.side_effect=fail
        with self.assertRaisesRegex(RuntimeError,'AUTO_ROLLBACK'):i.apply()
        for role,name in i.FILES.items():self.assertEqual((self.app/name).read_bytes(),self.originals[role])
        with sqlite3.connect(self.database) as c:
            self.assertEqual(c.execute('SELECT value FROM payments').fetchall(),[(1,),(2,)])

    def test_second_file_failure_restores_first_file(self):
        real=i.atomic;calls=[]
        def atomic(*args):
            calls.append(args[0])
            if len(calls)==2:raise OSError('simulated failure')
            real(*args)
        with patch.object(i,'atomic',side_effect=atomic):
            with self.assertRaisesRegex(RuntimeError,'AUTO_ROLLBACK'):i.apply()
        for role,name in i.FILES.items():self.assertEqual((self.app/name).read_bytes(),self.originals[role])

    def test_different_served_html_aborts_before_changes(self):
        self.get_page_mock.return_value=b'other';self.get_page_mock.side_effect=None
        with self.assertRaisesRegex(RuntimeError,'LIVE_TEMPLATE'):i.apply()
        self.assertFalse(self.state.exists())

    def test_manual_rollback_refuses_a_newer_html_change(self):
        i.apply();target=self.app/i.FILES['teacher'];target.write_bytes(target.read_bytes()+b'<!--new deployment-->')
        with self.assertRaisesRegex(RuntimeError,'ROLLBACK_CONFLICT'):i.rollback()
        self.assertTrue(target.read_bytes().endswith(b'<!--new deployment-->'))

    def test_embedded_sources_match_reviewed_sources(self):
        self.assertEqual(i.CSS,(ROOT/'ege_november_theme.css').read_text())
        self.assertEqual(i.JS,(ROOT/'ege_november_theme.js').read_text())
        self.assertEqual(i.PATCHER,(ROOT/'deploy/november_theme_patch.py').read_bytes())


if __name__=='__main__':unittest.main()
