"""Test only the new HTTPS virtual host and rollback; never contact an ACME CA."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
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

    @unittest.skipUnless(shutil.which('nginx') and shutil.which('openssl'),'requires nginx and openssl')
    def test_real_nginx_accepts_both_generated_configurations(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-subj','/CN='+setup.DOMAIN,'-days','1','-keyout',str(root/'privkey.pem'),'-out',str(root/'fullchain.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            test=root/'site.conf';main=root/'nginx.conf'
            temp_paths=' '.join(kind+'_temp_path '+str(root/kind)+';' for kind in ('client_body','proxy','fastcgi','uwsgi','scgi'))
            main.write_text('pid '+str(root/'nginx.pid')+';\nerror_log '+str(root/'error.log')+';\nevents {}\nhttp { '+temp_paths+' access_log '+str(root/'access.log')+'; include '+str(test)+'; }\n')
            with socket.socket() as a, socket.socket() as b:
                a.bind(('127.0.0.1',0));b.bind(('127.0.0.1',0))
                http_port=a.getsockname()[1];tls_port=b.getsockname()[1]
            with patch.object(setup,'LINEAGE',root),patch.object(setup,'BASE',root):
                for tls in (False,True):
                    text=setup.configuration(tls).replace('listen 80;',f'listen 127.0.0.1:{http_port};').replace('listen 443 ssl;',f'listen 127.0.0.1:{tls_port} ssl;')
                    test.write_text(text)
                    result=subprocess.run([shutil.which('nginx'),'-t','-p',str(root),'-c',str(main)],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stderr)
