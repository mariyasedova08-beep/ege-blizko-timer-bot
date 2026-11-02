"""Test only the new HTTPS virtual host and rollback; never contact an ACME CA."""
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('https_setup',ROOT/'deploy/bootstrap_lab_test_https.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)

class LabHTTPS(unittest.TestCase):
    def test_templates_use_only_new_virtual_host_and_loopback_backend(self):
        text=setup.configuration(True)
        self.assertEqual(text.count('server_name '+setup.DOMAIN+';'),2)
        self.assertIn('proxy_pass http://127.0.0.1:8768;',text)
        self.assertNotIn('default_server',text)
        self.assertNotIn('include ',text)
        self.assertNotIn('/opt/bots',text)
        for host in setup.EXISTING:self.assertNotIn('server_name '+host+';',text)
        self.assertTrue(setup.existing_http2('server {\nlisten 443 ssl http2;\n}'))
        self.assertIn('listen 443 ssl http2;',setup.configuration(True,True))
        self.assertNotIn('http2',setup.configuration(True,False))
        with self.assertRaises(RuntimeError):setup.existing_http2('listen 443 ssl proxy_protocol;')

    def test_certificate_challenge_has_separate_webroot_before_tls(self):
        text=setup.configuration(False)
        self.assertIn('location ^~ /.well-known/acme-challenge/',text)
        self.assertIn('return 503',text)
        self.assertNotIn('listen 443',text)
        self.assertNotIn('return 308',text)

    def test_certbot_cannot_select_nginx_standalone_or_global_hooks(self):
        args=setup.certbot_command('a'*32)
        self.assertEqual(args[:2],['certbot','certonly'])
        self.assertIn('--webroot',args);self.assertIn('--no-directory-hooks',args)
        for flag in ('--nginx','--standalone','--agree-tos','--register-unsafely-without-email'):
            self.assertNotIn(flag,args)
        self.assertEqual(args[args.index('--cert-name')+1],setup.NAME)
        self.assertEqual(args[args.index('-d')+1],setup.DOMAIN)
        self.assertEqual(args[args.index('--config')+1],str(setup.BASE/'certbot.ini'))

    def test_modified_existing_config_stops_operation(self):
        with tempfile.TemporaryDirectory() as folder:
            old=Path(folder)/'working.conf';old.write_text('original')
            hashes=setup.config_hashes('# configuration file '+str(old)+':\n')
            self.assertEqual(hashes[str(old)],hashlib.sha256(b'original').hexdigest())
            setup.verify_unchanged(hashes)
            old.write_text('changed')
            with self.assertRaises(RuntimeError):setup.verify_unchanged(hashes)

    def test_rollback_removes_only_our_new_host_and_preserves_issued_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);folder=base/'backups/receipt';folder.mkdir(parents=True)
            conf=base/'test.conf';conf.write_text(setup.configuration(True))
            hook=base/'hook';hook.write_text(setup.HOOK_TEXT)
            renewal=base/'test-renewal.conf';renewal.write_text('new certificate renewal')
            certificate=base/'fullchain.pem';certificate.write_text('retain certificate')
            production=base/'working.conf';production.write_text('must stay')
            before={'host':{'status':200}}
            (folder/'receipt.json').write_text(json.dumps({'had_config':False,'had_hook':False,'had_renewal':False,'config_hashes':{},'production':before}))
            with patch.object(setup,'BASE',base),patch.object(setup,'CONF',conf),patch.object(setup,'HOOK',hook),patch.object(setup,'RENEWAL',renewal),patch.object(setup,'reload_checked') as reload,patch.object(setup,'assert_production_same') as health:
                conf.write_text(setup.configuration(True))
                setup.restore(folder)
            self.assertFalse(conf.exists());self.assertFalse(hook.exists());self.assertFalse(renewal.exists())
            self.assertEqual((folder/'new-test-renewal.disabled').read_text(),'new certificate renewal')
            self.assertEqual(certificate.read_text(),'retain certificate')
            self.assertEqual(production.read_text(),'must stay')
            reload.assert_called_once_with({});health.assert_called_once_with(before)

    def test_unknown_config_is_not_removed_during_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);folder=base/'backups/receipt';folder.mkdir(parents=True)
            conf=base/'test.conf';conf.write_text('foreign configuration')
            (folder/'receipt.json').write_text(json.dumps({'had_config':False,'had_hook':False,'had_renewal':False,'config_hashes':{},'production':{}}))
            with patch.object(setup,'BASE',base),patch.object(setup,'CONF',conf):
                with self.assertRaises(RuntimeError):setup.restore(folder)
            self.assertEqual(conf.read_text(),'foreign configuration')

    def test_wrong_https_backend_is_rejected(self):
        with patch.object(setup,'tls_request',return_value=(200,'certificate',b'{"sandbox":false}')):
            with self.assertRaises(RuntimeError):setup.verify_sandbox()

    def test_existing_site_certificate_change_is_detected(self):
        before={'host':{'status':200,'certificate_sha256':'old'}}
        with patch.object(setup,'production_status',return_value={'host':{'status':200,'certificate_sha256':'new'}}):
            with self.assertRaises(RuntimeError):setup.assert_production_same(before)

    def test_waits_for_new_nginx_workers_without_disabling_tls(self):
        expected={'ok':True,'sandbox':True}
        stale=ssl.SSLCertVerificationError('stale certificate hostname')
        with patch.object(setup,'verify_sandbox',side_effect=[stale,stale,expected]) as verify,patch.object(setup.time,'sleep') as sleep:
            self.assertEqual(setup.wait_for_sandbox(attempts=3,delay=1),expected)
            self.assertEqual(verify.call_count,3);self.assertEqual(sleep.call_count,2)

    def test_persistent_certificate_error_is_never_accepted(self):
        with patch.object(setup,'verify_sandbox',side_effect=ssl.SSLCertVerificationError('wrong hostname')) as verify,patch.object(setup.time,'sleep'):
            with self.assertRaises(RuntimeError):setup.wait_for_sandbox(attempts=3,delay=0)
            self.assertEqual(verify.call_count,3)

    def test_openssl_zero_exit_with_negative_hostname_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'fullchain.pem').touch();(root/'privkey.pem').touch()
            with patch.object(setup,'LINEAGE',root),patch.object(setup,'run',return_value='Hostname '+setup.DOMAIN+' does NOT match certificate'):
                with self.assertRaises(RuntimeError):setup.certificate_usable()

    def test_saved_renewal_restored_and_valid_certificate_reused_without_ca_order(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);lineage=base/'lineage';lineage.mkdir()
            archive=Path('/etc/letsencrypt/archive')/setup.NAME
            content='version = 2.9.0\narchive_dir = '+str(archive)+'\n'+''.join(key+' = '+str(lineage/(key+'.pem'))+'\n' for key in ('cert','privkey','chain','fullchain'))
            content+='[renewalparams]\nauthenticator = webroot\ndeploy_hook = '+str(setup.HOOK)+'\n[[webroot_map]]\n'+setup.DOMAIN+' = '+str(base/'acme')+'\n'
            backup=base/'backups/old';backup.mkdir(parents=True)
            (backup/'new-test-renewal.disabled').write_text(content)
            renewal=base/'renewal.conf'
            with patch.object(setup,'BASE',base),patch.object(setup,'LINEAGE',lineage),patch.object(setup,'RENEWAL',renewal),patch.object(setup,'check_dir',lambda path:None),patch.object(setup,'certificate_usable',return_value=True),patch.object(setup,'run') as run:
                setup.ensure_test_certificate('existing-account')
            self.assertEqual(renewal.read_text(),content)
            run.assert_not_called()
            self.assertTrue((backup/'new-test-renewal.disabled').exists())

    def test_renewal_for_other_certificate_is_rejected(self):
        content='archive_dir = /etc/letsencrypt/archive/production\ncert = /etc/letsencrypt/live/production/cert.pem\n[renewalparams]\nauthenticator = webroot\n'
        with self.assertRaises(ValueError):setup.validate_saved_renewal(content)

    @unittest.skipUnless(shutil.which('nginx') and shutil.which('openssl'),'requires nginx and openssl')
    def test_real_nginx_reload_replaces_wrong_certificate_before_accepting_build(self):
        spec=importlib.util.spec_from_file_location('reload_sandbox_server',ROOT/'deploy/lab_sandbox_server.py')
        backend_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend_module)
        html,payload,health=backend_module.load_bundle(ROOT/'preview/lab-sandbox/bundle.json')
        backend=ThreadingHTTPServer(('127.0.0.1',0),backend_module.handler_for(html,payload,health))
        thread=threading.Thread(target=backend.serve_forever,daemon=True);thread.start()
        process=None
        try:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);old=root/'old';old.mkdir();new=root/'new';new.mkdir()
                for folder,host in ((old,'old.invalid'),(new,setup.DOMAIN)):
                    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','60','-subj','/CN='+host,'-addext','subjectAltName=DNS:'+host,'-keyout',str(folder/'privkey.pem'),'-out',str(folder/'fullchain.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                with socket.socket() as a,socket.socket() as b:
                    a.bind(('127.0.0.1',0));b.bind(('127.0.0.1',0))
                    http_port=a.getsockname()[1];tls_port=b.getsockname()[1]
                site=root/'site.conf';main=root/'nginx.conf'
                paths=' '.join(kind+'_temp_path '+str(root/kind)+';' for kind in ('client_body','proxy','fastcgi','uwsgi','scgi'))
                main.write_text('pid '+str(root/'pid')+';\nerror_log '+str(root/'error.log')+';\nevents {}\nhttp { '+paths+' access_log off; include '+str(site)+'; }\n')
                def write_config(lineage):
                    with patch.object(setup,'LINEAGE',lineage),patch.object(setup,'BASE',root):
                        text=setup.configuration(True,False).replace('listen 80;',f'listen 127.0.0.1:{http_port};').replace('listen 443 ssl;',f'listen 127.0.0.1:{tls_port} ssl;').replace('http://127.0.0.1:8768',f'http://127.0.0.1:{backend.server_port}')
                    site.write_text(text)
                write_config(old)
                process=subprocess.Popen([shutil.which('nginx'),'-p',str(root),'-c',str(main),'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                for _ in range(100):
                    if process.poll() is not None:raise RuntimeError('test nginx exited')
                    try:
                        with socket.create_connection(('127.0.0.1',tls_port),timeout=.2):break
                    except OSError:time.sleep(.05)
                context=ssl.create_default_context()
                context.load_verify_locations(cadata=(old/'fullchain.pem').read_text()+(new/'fullchain.pem').read_text())
                self.assertTrue(context.check_hostname);self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
                def request(host,path='/',method='GET',body=None):
                    with socket.create_connection(('127.0.0.1',tls_port),timeout=3) as raw:
                        with context.wrap_socket(raw,server_hostname=host) as sock:
                            data=body or b''
                            sock.sendall(f'{method} {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\nContent-Length: {len(data)}\r\n\r\n'.encode()+data)
                            response=http.client.HTTPResponse(sock);response.begin()
                            return response.status,hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest(),response.read()
                with patch.object(setup,'tls_request',side_effect=request):
                    with self.assertRaises(ssl.SSLCertVerificationError):setup.verify_sandbox()
                    write_config(new)
                    subprocess.run([shutil.which('nginx'),'-p',str(root),'-c',str(main),'-s','reload'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    self.assertEqual(setup.wait_for_sandbox(attempts=50,delay=.05)['build'],health['build'])
                process.terminate();process.wait(timeout=5);process=None
        finally:
            if process is not None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            backend.shutdown();backend.server_close();thread.join()

    @unittest.skipUnless(shutil.which('nginx') and shutil.which('openssl'),'requires nginx and openssl')
    def test_real_nginx_accepts_both_generated_configurations(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-subj','/CN='+setup.DOMAIN,'-days','60','-keyout',str(root/'privkey.pem'),'-out',str(root/'fullchain.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            test=root/'site.conf';main=root/'nginx.conf'
            temp_paths=' '.join(kind+'_temp_path '+str(root/kind)+';' for kind in ('client_body','proxy','fastcgi','uwsgi','scgi'))
            main.write_text('pid '+str(root/'nginx.pid')+';\nerror_log '+str(root/'error.log')+';\nevents {}\nhttp { '+temp_paths+' access_log '+str(root/'access.log')+'; include '+str(test)+'; }\n')
            with socket.socket() as a, socket.socket() as b:
                a.bind(('127.0.0.1',0));b.bind(('127.0.0.1',0))
                http_port=a.getsockname()[1];tls_port=b.getsockname()[1]
            with patch.object(setup,'LINEAGE',root),patch.object(setup,'BASE',root):
                self.assertTrue(setup.certificate_usable())
                for tls,http2 in ((False,False),(True,False),(True,True)):
                    text=setup.configuration(tls,http2).replace('listen 80;',f'listen 127.0.0.1:{http_port};').replace('listen 443 ssl',f'listen 127.0.0.1:{tls_port} ssl')
                    test.write_text(text)
                    result=subprocess.run([shutil.which('nginx'),'-t','-p',str(root),'-c',str(main)],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stderr)
