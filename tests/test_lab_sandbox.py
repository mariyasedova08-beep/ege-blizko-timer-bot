"""Exercise the packaged HTTP runtime and isolated release filesystem behavior."""
import base64
import gzip
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

server=module('sandbox_server','deploy/lab_sandbox_server.py')
installer=module('sandbox_installer','deploy/bootstrap_lab_sandbox.py')
builder=module('sandbox_builder','deploy/build_lab_sandbox.py')

class SandboxRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle=ROOT/'preview/lab-sandbox/bundle.json'
        cls.html,cls.payload,cls.health=server.load_bundle(cls.bundle)
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.handler_for(cls.html,cls.payload,cls.health))
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join()

    def request(self,method,path,body=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=4)
        c.request(method,path,body=body,headers=headers or {})
        r=c.getresponse();data=r.read();status=r.status;c.close();return status,data

    def test_bundle_matches_current_sources_deterministically(self):
        self.assertEqual(builder.build(),self.bundle.read_bytes())
        self.assertEqual(installer.BUNDLE_SHA256, self.health['bundle_sha256'])
        self.assertEqual(installer.EXPECTED_BUILD, self.health['build'])
        self.assertEqual(installer.EXPECTED_HTML, self.health['html_sha256'])
        self.assertEqual(installer.EXPECTED_PAYLOAD, self.health['payload_sha256'])
        self.assertEqual(self.health['coverage'],{'substances':219,'reactions':1423,'medium_reactions':89})
        self.assertIn('Тестовая лаборатория'.encode(),self.html)
        self.assertNotIn(b'https://telegram.org/js/telegram-web-app.js',self.html)

    def test_real_http_html_load_and_health_match_package(self):
        status,body=self.request('GET','/lab-app');self.assertEqual(status,200);self.assertEqual(body,self.html)
        status,body=self.request('GET','/healthz');self.assertEqual(status,200);self.assertEqual(json.loads(body),self.health)
        status,body=self.request('POST','/lab-app/api',json.dumps({'action':'load'}));self.assertEqual(status,200);self.assertEqual(json.loads(body),self.payload)

    def test_no_filesystem_or_production_routes(self):
        for path in ('/','/etc/passwd','/../etc/passwd','/lab-app/../../etc/passwd','/lab-app/api','/admin','/%2e%2e/etc/passwd'):
            self.assertEqual(self.request('GET',path)[0],404,path)

    def test_events_do_not_mutate_payload_and_bad_actions_fail(self):
        before=json.dumps(self.payload,sort_keys=True)
        status,body=self.request('POST','/lab-app/api','{"action":"event","type":"experiment"}')
        self.assertEqual(status,200);self.assertTrue(json.loads(body)['preview'])
        self.assertEqual(json.dumps(self.payload,sort_keys=True),before)
        status,body=self.request('POST','/lab-app/api','{"action":"task6_start"}')
        self.assertFalse(json.loads(body)['ok'])
        for body in ('[]','null','broken','x'*50001):self.assertEqual(self.request('POST','/lab-app/api',body)[0],400)

    def test_modified_or_oversized_bundle_refused(self):
        content=json.loads(self.bundle.read_bytes());content['html_sha256']='0'*64
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'bundle';target.write_text(json.dumps(content))
            with self.assertRaises(ValueError):server.load_bundle(target)
        packed=base64.b64encode(gzip.compress(b'x'*(server.MAX_CONTENT+1))).decode()
        with self.assertRaises(ValueError):server.unpack(packed)

class SandboxInstall(unittest.TestCase):
    def test_atomic_switch_preserves_old_release_and_rejects_outside(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);(base/'releases').mkdir()
            a=base/'releases/first';a.mkdir();(a/'note').write_text('keep')
            b=base/'releases/second';b.mkdir()
            installer.activate(a,base);self.assertEqual(installer.current_target(base),str(a))
            installer.activate(b,base);self.assertEqual(installer.current_target(base),str(b))
            self.assertEqual((a/'note').read_text(),'keep')
            with self.assertRaises(ValueError):installer.activate(base,base)

    def test_bad_existing_current_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);(base/'current').write_text('foreign')
            with self.assertRaises(ValueError):installer.current_target(base)
            self.assertEqual((base/'current').read_text(),'foreign')

    def test_rollback_restores_previous_files_target_and_only_own_service(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);(base/'backups/receipt').mkdir(parents=True)
            (base/'releases/old').mkdir(parents=True);(base/'releases/new').mkdir()
            installer.activate(base/'releases/new',base)
            backup=base/'backups/receipt'
            (backup/'receipt.json').write_text(json.dumps({'previous':str(base/'releases/old'),'active':True,'enabled':True,'had_unit':True,'had_inspector':True}))
            (backup/'unit').write_text('old unit');(backup/'inspector').write_text('old inspector')
            unit=base/'unit';unit.write_text('new unit');inspect=base/'inspector';inspect.write_text('new inspector')
            from unittest.mock import patch
            calls=[]
            def mock_run(*args,**kwargs):calls.append(args);return subprocess.CompletedProcess(args,0,'','')
            original=installer.activate
            with patch.object(installer,'trusted_directory',lambda path:None),patch.object(installer,'BASE',base),patch.object(installer,'UNIT_PATH',unit),patch.object(installer,'INSPECTOR',inspect),patch.object(installer,'run',mock_run),patch.object(installer,'activate',lambda target:original(target,base)):
                installer.restore(backup)
            self.assertEqual(unit.read_text(),'old unit');self.assertEqual(inspect.read_text(),'old inspector')
            self.assertEqual(installer.current_target(base),str(base/'releases/old'))
            for command in calls:
                self.assertEqual(command[0],'systemctl')
                self.assertTrue(command==('systemctl','daemon-reload') or command[-1]=='ege-lab-sandbox-preview.service')

    def test_download_rejects_wrong_hash_without_installation(self):
        from unittest.mock import patch
        import io
        with patch.object(installer,'PACKAGE_COMMIT','a'*40),patch.object(installer.urllib.request,'urlopen',return_value=io.BytesIO(b'wrong')):
            with self.assertRaises(ValueError):installer.download('bundle.json',installer.BUNDLE_SHA256)

    def test_failed_update_restores_existing_release_and_only_its_service(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);old=base/'releases/old';old.mkdir(parents=True);(base/'backups').mkdir()
            (old/'sentinel').write_text('old release preserved')
            installer.activate(old,base)
            unit=base/'unit';unit.write_text(installer.UNIT)
            inspect=base/'inspector';inspect.write_text(installer.NEW_INSPECTOR)
            # Model a trusted root-owned helper without requiring chown on the CI runner.
            class RootOwnedInspector(type(inspect)):
                def stat(self, *args, **kwargs):
                    values=list(super().stat(*args, **kwargs));values[4]=0
                    return os.stat_result(values)
            trusted_inspect=RootOwnedInspector(inspect)
            commands=[]
            def mock_run(*args,**kwargs):
                commands.append(args);return subprocess.CompletedProcess(args,0,'','')
            original_current,original_activate=installer.current_target,installer.activate
            source=(ROOT/'preview/lab-sandbox/bundle.json').read_bytes()
            code=(ROOT/'deploy/lab_sandbox_server.py').read_bytes()
            with patch.object(installer.os,'geteuid',return_value=0),patch.object(installer.shutil,'which',return_value='/mock/program'),patch.object(installer,'trusted_directory',lambda path:None),patch.object(installer,'BASE',base),patch.object(installer,'UNIT_PATH',unit),patch.object(installer,'INSPECTOR',trusted_inspect),patch.object(installer,'run',side_effect=mock_run),patch.object(installer,'download',side_effect=[source,code]),patch.object(installer,'current_target',side_effect=lambda base_arg=base:original_current(base_arg)),patch.object(installer,'activate',side_effect=lambda target:original_activate(target,base)),patch.object(installer,'health',side_effect=ValueError('failed new build')),patch.object(installer.time,'sleep'),patch('sys.argv',['bootstrap_lab_sandbox.py']):
                with self.assertRaisesRegex(RuntimeError,'sandbox healthcheck failed'):
                    installer.main()
            self.assertEqual(installer.current_target(base),str(old))
            self.assertEqual((old/'sentinel').read_text(),'old release preserved')
            self.assertEqual(unit.read_text(),installer.UNIT)
            self.assertEqual(inspect.read_text(),installer.NEW_INSPECTOR)
            self.assertEqual(len(list((base/'backups').glob('*/receipt.json'))),1)
            self.assertIn(('systemctl','restart',installer.UNIT_NAME),commands)
            self.assertIn(('systemctl','stop',installer.UNIT_NAME),commands)
            for command in commands:
                self.assertEqual(command[0],'systemctl')
                self.assertTrue(command==('systemctl','daemon-reload') or command[-1]==installer.UNIT_NAME)
