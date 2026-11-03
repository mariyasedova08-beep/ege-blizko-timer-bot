"""Pilot gate is exercised on a disposable loopback server, never on the VPS."""
import base64
import http.client
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'deploy'))
import lab_sandbox_server as runtime
import lab_pilot_access as access


class PilotAccess(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.file=Path(self.temp.name)/'users.json'
        self.password='test-only-random-password-123456'
        access.update(self.file,'teacher_a',password=self.password)
        access.update(self.file,'teacher_b',password=self.password+'b')
        self.http=ThreadingHTTPServer(('127.0.0.1',0),runtime.handler_for(b'<html>PRIVATE</html>',{'ok':True,'data':{'preview':True}}, {'ok':True,'sandbox':True,'build':'test'}, self.file))
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();self.temp.cleanup()

    def request(self,path='/lab-app',user=None,password=None,method='GET',authorization=None):
        headers={}
        if user:headers['Authorization']='Basic '+base64.b64encode((user+':'+password).encode()).decode()
        if authorization:headers['Authorization']=authorization
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
        conn.request(method,path,body='{"action":"load"}' if method=='POST' else None,headers=headers)
        response=conn.getresponse();result=(response.status,response.read());conn.close();return result

    def test_html_and_api_deny_anonymous_wrong_and_malformed_credentials(self):
        for path,method in [('/lab-app','GET'),('/lab-app/api','POST'),('/lab-app?token=pretend','GET'),('/lab-app/../lab-app','GET')]:
            self.assertEqual(self.request(path,method=method)[0],401)
        for header in ['Basic !!!','Bearer secret','Basic '+base64.b64encode(b'nocolon').decode()]:
            self.assertEqual(self.request(authorization=header)[0],401)
        self.assertEqual(self.request(user='teacher_a',password='wrong')[0],401)
        self.assertEqual(self.request('/healthz')[0],200)

    def test_valid_individual_access_and_revocation(self):
        self.assertEqual(self.request(user='teacher_a',password=self.password),(200,b'<html>PRIVATE</html>'))
        status,body=self.request('/lab-app/api',user='teacher_a',password=self.password,method='POST')
        self.assertEqual(status,200);self.assertIn(b'teacher_a',body)
        access.update(self.file,'teacher_a',revoke=True)
        self.assertEqual(self.request(user='teacher_a',password=self.password)[0],401)
        self.assertEqual(self.request(user='teacher_b',password=self.password+'b')[0],200)
        self.assertNotIn(self.password,self.file.read_text())

    def test_expired_corrupt_or_missing_config_fails_closed(self):
        import json
        config=json.loads(self.file.read_text());config['users']['teacher_a']['expires']=time.time()-1
        self.file.write_text(json.dumps(config));self.assertEqual(self.request(user='teacher_a',password=self.password)[0],401)
        self.file.write_text('{broken');self.assertEqual(self.request(user='teacher_b',password=self.password+'b')[0],401)
        self.file.unlink();self.assertEqual(self.request(user='teacher_b',password=self.password+'b')[0],401)

    def test_existing_user_is_not_overwritten(self):
        previous=self.file.read_bytes()
        with self.assertRaises(ValueError):access.update(self.file,'teacher_a',password=self.password)
        self.assertEqual(previous,self.file.read_bytes())
