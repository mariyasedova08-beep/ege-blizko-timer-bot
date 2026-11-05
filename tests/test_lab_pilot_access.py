"""Pilot gate is exercised on a disposable loopback server, never on the VPS."""
import base64
import http.client
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import time
import urllib.parse
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
        self.assertEqual(self.request('/lab-app')[0],200) # public login shell, never the lab bundle
        for path,method in [('/lab-app/api','POST'),('/lab-app/../lab-app','GET')]:
            self.assertEqual(self.request(path,method=method)[0],401 if path.endswith('/api') else 404)
        for header in ['Basic !!!','Bearer secret','Basic '+base64.b64encode(b'nocolon').decode()]:
            self.assertEqual(self.request('/lab-app/api',method='POST',authorization=header)[0],401)
        self.assertEqual(self.request('/lab-app/api',user='teacher_a',password='wrong',method='POST')[0],401)
        self.assertEqual(self.request('/healthz')[0],200)

    def test_valid_individual_access_and_revocation(self):
        self.assertEqual(self.request(user='teacher_a',password=self.password),(200,b'<html>PRIVATE</html>'))
        status,body=self.request('/lab-app/api',user='teacher_a',password=self.password,method='POST')
        self.assertEqual(status,200);self.assertIn(b'teacher_a',body)
        access.update(self.file,'teacher_a',revoke=True)
        self.assertEqual(self.request('/lab-app/api',user='teacher_a',password=self.password,method='POST')[0],401)
        self.assertEqual(self.request(user='teacher_b',password=self.password+'b')[0],200)
        self.assertNotIn(self.password,self.file.read_text())

    def test_one_time_invitation_registers_user_and_cookie_survives_requests(self):
        token=access.create_invite(self.file,days=7)
        status,body=self.request('/invite/'+token)
        self.assertEqual(status,200);self.assertIn('Создай логин и пароль'.encode(),body)
        username='new_teacher';password='teacher-password-123'
        form=urllib.parse.urlencode({'token':token,'username':username,'password':password}).encode()
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
        conn.request('POST','/lab-app/auth/register',body=form,headers={'Content-Type':'application/x-www-form-urlencoded'})
        response=conn.getresponse();self.assertEqual(response.status,303)
        cookie=response.getheader('Set-Cookie').split(';',1)[0];response.read();conn.close()
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
        conn.request('GET','/lab-app',headers={'Cookie':cookie})
        response=conn.getresponse();self.assertEqual(response.status,200);self.assertIn(b'PRIVATE',response.read());conn.close()
        status,_=self.request('/invite/'+token)
        self.assertEqual(status,410)

    def test_login_form_sets_persistent_cookie_and_logout_revokes_session(self):
        form=urllib.parse.urlencode({'username':'teacher_a','password':self.password}).encode()
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
        conn.request('POST','/lab-app/auth/login',body=form,headers={'Content-Type':'application/x-www-form-urlencoded'})
        response=conn.getresponse();self.assertEqual(response.status,303)
        cookie=response.getheader('Set-Cookie');self.assertIn('Max-Age=',cookie);self.assertIn('Secure',cookie);cookie=cookie.split(';',1)[0]
        response.read();conn.close()
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
        conn.request('POST','/lab-app/api',body='{"action":"load"}',headers={'Cookie':cookie})
        response=conn.getresponse();self.assertEqual(response.status,200);self.assertIn(b'teacher_a',response.read());conn.close()
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
        conn.request('POST','/lab-app/auth/logout',headers={'Cookie':cookie})
        response=conn.getresponse();self.assertEqual(response.status,303);response.read();conn.close()
        self.assertEqual(self.request('/lab-app/api',method='POST')[0],401)

    def test_invite_validation_and_password_bounds(self):
        token=access.create_invite(self.file)
        for username,password in [('ab','long-enough-password'),('okay','short')]:
            form=urllib.parse.urlencode({'token':token,'username':username,'password':password}).encode()
            conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
            conn.request('POST','/lab-app/auth/register',body=form,headers={'Content-Type':'application/x-www-form-urlencoded'})
            response=conn.getresponse();self.assertEqual(response.status,400);response.read();conn.close()
        self.assertFalse(access.read_config(self.file)['invites'][__import__('hashlib').sha256(token.encode()).hexdigest()]['used'])

    def test_expired_corrupt_or_missing_config_fails_closed(self):
        import json
        config=json.loads(self.file.read_text());config['users']['teacher_a']['expires']=time.time()-1
        self.file.write_text(json.dumps(config));self.assertEqual(self.request('/lab-app/api',user='teacher_a',password=self.password,method='POST')[0],401)
        for broken in ['{broken','[]','null']:
            self.file.write_text(broken);self.assertEqual(self.request('/lab-app/api',user='teacher_b',password=self.password+'b',method='POST')[0],401)
        self.file.unlink();self.assertEqual(self.request('/lab-app/api',user='teacher_b',password=self.password+'b',method='POST')[0],401)

    def test_existing_user_is_not_overwritten(self):
        previous=self.file.read_bytes()
        with self.assertRaises(ValueError):access.update(self.file,'teacher_a',password=self.password)
        self.assertEqual(previous,self.file.read_bytes())

    def test_owner_can_rotate_lost_password_without_replacing_username(self):
        password=access.reset_password(self.file,'teacher_a',days=30)
        self.assertGreaterEqual(len(password),24)
        self.assertEqual(self.request('/lab-app',user='teacher_a',password=password)[0],200)
        self.assertEqual(self.request('/lab-app/api',user='teacher_a',password=password,method='POST')[0],200)
