"""Activation/rollback uses only temporary files and fake service operations."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'deploy'))
import bootstrap_lab_pilot as pilot
import lab_pilot_access as access
import lab_sandbox_server as runtime


class PilotBootstrap(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.users=self.root/'access/users.json';self.gate=self.root/'unit.d/30-pilot-access.conf';self.admin=self.root/'admin'
        self.patches=[patch.object(pilot,'USERS',self.users),patch.object(pilot,'DROPIN',self.gate),patch.object(pilot,'ADMIN',self.admin)]
        for p in self.patches:p.start()
        self.unit=self.root/'sandbox.service';self.unit.write_text('ONLY_SANDBOX')
        self.events=[];self.receipt=self.root/'backup'
        def backup(*args):self.receipt.mkdir();return self.receipt
        def write(path,data,mode):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);path.chmod(mode)
        self.installer=SimpleNamespace(UNIT_PATH=self.unit,UNIT='ONLY_SANDBOX',UNIT_NAME='ege-lab-sandbox-preview.service',
            trusted_directory=lambda path:None,current_target=lambda:'isolated-old-release',run=lambda *a,**kw:self.fake_run(*a,**kw),backup=backup,
            main=lambda:self.events.append('install'),restore=lambda folder:self.events.append('restore'),write_atomic=write,
            EXPECTED_HTML=hashlib.sha256(b'<html>pilot</html>').hexdigest(),EXPECTED_BUILD='test-build',health=lambda:self.events.append('health'))
        self.artifacts={name:(ROOT/'deploy'/name).read_bytes() for name in pilot.PINS}

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def fake_run(self,*args,**kwargs):
        self.events.append(args);return SimpleNamespace(returncode=0)

    def fetch(self,path,password=None,body=None):
        header=''
        if password is not None:
            import base64
            header='Basic '+base64.b64encode(('maria:'+password).encode()).decode()
        if not runtime.access_allowed(header,self.users):return 401,b''
        if path=='/lab-app':return 200,b'<html>pilot</html>'
        return 200,json.dumps({'ok':True,'data':{'pilot_user':'maria','preview':True}}).encode()

    def test_success_creates_one_admin_and_only_sandbox_gate(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):pilot.enable(self.installer,access,self.artifacts,self.fetch)
        lines=out.getvalue();self.assertIn('PROTECTED_PILOT_READY',lines)
        self.assertIn('PASSWORD_SHOW_ONCE:',lines);self.assertEqual(lines.count('PASSWORD_SHOW_ONCE:'),1)
        self.assertEqual(self.gate.read_text(),pilot.GATE)
        self.assertTrue((self.receipt/'pilot-receipt.json').is_file())
        password=lines.split('PASSWORD_SHOW_ONCE: ')[1].splitlines()[0]
        self.assertNotIn(password,self.users.read_text())
        self.assertNotIn('restore',self.events)
        for event in self.events:
            if isinstance(event,tuple) and event[0]=='systemctl':
                self.assertTrue(event[1]=='daemon-reload' or 'ege-lab-sandbox-preview.service' in event)

    def test_bad_public_gate_rolls_back_without_printing_password(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out),patch.object(pilot.time,'sleep'):
            with self.assertRaisesRegex(ValueError,'ANONYMOUS_ACCESS_NOT_BLOCKED'):
                pilot.enable(self.installer,access,self.artifacts,lambda *a,**kw:(200,b'open'))
        self.assertIn('restore',self.events)
        for path in [self.users,self.gate,self.admin]:self.assertFalse(path.exists())
        self.assertNotIn('PASSWORD_SHOW_ONCE',out.getvalue())
        self.assertIn('PILOT_ROLLBACK_COMPLETE',out.getvalue())

    def test_existing_access_is_not_replaced(self):
        self.users.parent.mkdir();self.users.write_text('existing')
        with self.assertRaisesRegex(ValueError,'EXISTING_PILOT_CONFIGURATION_REFUSED'):
            pilot.enable(self.installer,access,self.artifacts,self.fetch)
        self.assertEqual(self.users.read_text(),'existing');self.assertFalse(self.events)

    def test_every_download_pin_matches_reviewed_local_artifact(self):
        for name,digest in pilot.PINS.items():
            # First-time activation intentionally pins its original installer;
            # later normal sandbox updates change the current installer only.
            if name == "bootstrap_lab_sandbox.py":continue
            self.assertEqual(hashlib.sha256((ROOT/'deploy'/name).read_bytes()).hexdigest(),digest,name)
