"""Check inspection-only entrypoints without installing accounts or sudo rules."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lab_inspect_setup', ROOT/'deploy/bootstrap_lab_test_inspect.py')
setup=importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)

class InspectSetup(unittest.TestCase):
    def test_inspector_compiles_and_has_no_app_imports_or_shell_commands(self):
        compile(setup.INSPECTOR_SOURCE, '<inspector>', 'exec')
        self.assertNotIn('import run_bot',setup.INSPECTOR_SOURCE)
        self.assertNotIn('subprocess',setup.INSPECTOR_SOURCE)
        self.assertNotIn('/opt/bots',setup.INSPECTOR_SOURCE)

    def test_unknown_ssh_command_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'entry';path.write_text(setup.ENTRY_SOURCE)
            result=subprocess.run(['sh',str(path)],env={'SSH_ORIGINAL_COMMAND':'id; reboot'},capture_output=True,text=True)
            self.assertEqual(result.returncode,1)
            self.assertEqual(result.stderr.strip(),'LAB_TEST_SSH_DENIED')
            subprocess.run(['sh','-n',str(path)],check=True)

    def test_existing_different_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'existing';path.write_text('original')
            with self.assertRaises(SystemExit): setup.install_new(path,'different',0o600)
            self.assertEqual(path.read_text(),'original')

    def test_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'link';path.symlink_to(Path(directory)/'target')
            with self.assertRaises(SystemExit):setup.verify_existing(path,'anything')

    def test_sudo_rule_cannot_run_root_or_accept_arguments(self):
        self.assertEqual(setup.SUDOERS_SOURCE,'ege-lab-inspect ALL=(maria-admin) NOPASSWD: /usr/local/libexec/ege-lab-test-inspect.py ""\n')
