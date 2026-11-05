#!/usr/bin/env python3
"""Install a separate, forced-command, read-only SSH identity for the lab test.

Run as root once, from a trusted console. Existing deploy users, keys, sshd,
firewall, nginx, bot files and services are never edited or restarted.
"""
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tempfile

USER = 'ege-lab-inspect'
HOME = Path('/var/lib/ege-lab-inspect')
KEY = Path('/root/.ssh/ege_lab_test_actions')
LIBEXEC = Path('/usr/local/libexec')
INSPECTOR = LIBEXEC / 'ege-lab-test-inspect.py'
ENTRY = LIBEXEC / 'ege-lab-test-ssh'
SUDOERS = Path('/etc/sudoers.d/ege-lab-test-inspect')

INSPECTOR_SOURCE = '''#!/usr/bin/python3 -I
"""Fixed read-only report. No user arguments or application imports."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import urllib.request

ROOT = Path('/home/maria-admin/lab-test-20261028')
FILES = ('ege_lab_webapp.py', 'lab_standalone_preview.py',
         'ege_lab_substances.py', 'ege_lab_inorganic_reactions.py',
         'ege_lab_exchange_matrix.py', 'ege_lab_mn_cr_pdf_import.py',
         'ege_task6_bank.py', 'ege_task6_reactions.py', 'ege_task6_progress.py')

def report():
    if len(sys.argv) != 1:
        raise SystemExit('LAB_TEST_INSPECT_DENIED')
    if ROOT.resolve() != ROOT or not ROOT.is_dir():
        raise SystemExit('LAB_TEST_DIRECTORY_UNAVAILABLE')
    result = {'mode': 'read-only', 'files': {}}
    for name in FILES:
        try:
            fd = os.open(ROOT / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > 2_000_000:
                    result['files'][name] = {'state': 'not-regular-or-too-large'}
                    continue
                content = stream.read(2_000_001)
            result['files'][name] = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
        except OSError:
            result['files'][name] = {'state': 'missing-or-unreadable'}
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:8767/lab-app', timeout=2) as response:
            result['loopback_preview_http_status'] = response.status
    except Exception:
        result['loopback_preview_http_status'] = 'unavailable'
    return result

if __name__ == '__main__':
    print(json.dumps(report(), sort_keys=True))
'''

ENTRY_SOURCE = '''#!/bin/sh
# Root-owned forced command; arguments are never evaluated.
set -eu
[ "$#" -eq 0 ] || exit 1
if [ "${SSH_ORIGINAL_COMMAND:-}" != "lab-test-status-v1" ]; then
    echo LAB_TEST_SSH_DENIED >&2
    exit 1
fi
exec /usr/bin/sudo -n -u maria-admin /usr/local/libexec/ege-lab-test-inspect.py
'''
SUDOERS_SOURCE = 'ege-lab-inspect ALL=(maria-admin) NOPASSWD: /usr/local/libexec/ege-lab-test-inspect.py ""\n'


def checked(cmd, **kwargs):
    return subprocess.run(cmd, check=True, **kwargs)


def verify_existing(path, content):
    if path.is_symlink():
        raise SystemExit(f'REFUSING_SYMLINK: {path}')
    if path.exists() and (not path.is_file() or path.read_text() != content or path.stat().st_uid != 0):
        raise SystemExit(f'REFUSING_TO_OVERWRITE: {path}')


def install_new(path, content, mode):
    verify_existing(path, content)
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
    os.chmod(path, mode)


def main():
    if os.geteuid() != 0:
        raise SystemExit('ROOT_CONSOLE_REQUIRED')
    for command in ('useradd', 'ssh-keygen', 'sudo', 'visudo'):
        if not shutil.which(command):
            raise SystemExit(f'MISSING_PROGRAM: {command}')
    pwd.getpwnam('maria-admin')
    if HOME.is_symlink() or LIBEXEC.is_symlink():
        raise SystemExit('INSTALL_DIRECTORY_IS_SYMLINK')
    test_dir = Path('/home/maria-admin/lab-test-20261028')
    if not test_dir.is_dir() or test_dir.resolve() != test_dir:
        raise SystemExit('TEST_DIRECTORY_NOT_FOUND_OR_SYMLINK')
    for path, content in ((INSPECTOR, INSPECTOR_SOURCE), (ENTRY, ENTRY_SOURCE), (SUDOERS, SUDOERS_SOURCE)):
        verify_existing(path, content)
    try:
        account = pwd.getpwnam(USER)
    except KeyError:
        account = None
    if account and (account.pw_dir != str(HOME) or not ENTRY.exists()):
        raise SystemExit('EXISTING_ACCOUNT_NOT_OWNED_BY_THIS_SETUP')
    # Validate the sudo rule before installing anything.
    with tempfile.NamedTemporaryFile(mode='w', prefix='lab-inspect-sudo-', delete=True) as trial:
        trial.write(SUDOERS_SOURCE)
        trial.flush()
        checked(['visudo', '-cf', trial.name], stdout=subprocess.DEVNULL)
    if KEY.is_symlink() or KEY.with_suffix('.pub').is_symlink():
        raise SystemExit('KEY_PATH_IS_SYMLINK')
    KEY.parent.mkdir(mode=0o700, exist_ok=True)
    if not KEY.exists():
        checked(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'ege-lab-test-readonly', '-f', str(KEY)])
    if KEY.stat().st_uid != 0 or KEY.stat().st_mode & 0o077:
        raise SystemExit('PRIVATE_KEY_PERMISSIONS_NOT_PRIVATE')
    public = checked(['ssh-keygen', '-y', '-f', str(KEY)], capture_output=True, text=True).stdout.strip()
    if not public.startswith('ssh-ed25519 ') or '\n' in public:
        raise SystemExit('UNEXPECTED_PUBLIC_KEY_FORMAT')
    authorized = 'restrict,command="/usr/local/libexec/ege-lab-test-ssh" ' + public + '\n'
    verify_existing(HOME / '.ssh/authorized_keys', authorized)
    if not account:
        checked(['useradd', '--system', '--create-home', '--home-dir', str(HOME), '--shell', '/bin/sh', USER])
    # Root owns all entry points. The SSH identity cannot replace its restrictions.
    HOME.mkdir(mode=0o755, exist_ok=True)
    os.chown(HOME, 0, 0)
    os.chmod(HOME, 0o755)
    ssh_dir = HOME / '.ssh'
    if ssh_dir.is_symlink():
        raise SystemExit('SSH_DIRECTORY_IS_SYMLINK')
    # sshd reads authorized_keys as the login UID; root ownership prevents
    # replacement, while public-read permissions permit key authentication.
    ssh_dir.mkdir(mode=0o755, exist_ok=True)
    os.chown(ssh_dir, 0, 0)
    os.chmod(ssh_dir, 0o755)
    LIBEXEC.mkdir(mode=0o755, exist_ok=True)
    install_new(INSPECTOR, INSPECTOR_SOURCE, 0o755)
    install_new(ENTRY, ENTRY_SOURCE, 0o755)
    install_new(SUDOERS, SUDOERS_SOURCE, 0o440)
    install_new(ssh_dir / 'authorized_keys', authorized, 0o644)
    # Execute precisely the permitted diagnostic as its restricted run-as user.
    checked(['sudo', '-n', '-u', USER, 'env', 'SSH_ORIGINAL_COMMAND=lab-test-status-v1', str(ENTRY)])
    print('LAB_TEST_READONLY_ACCESS_INSTALLED')
    print('PRIVATE_KEY_FOR_GITHUB_ONLY: ' + str(KEY))
    print('NO_PRODUCTION_FILES_CHANGED_NO_SERVICES_RESTARTED')


if __name__ == '__main__':
    main()
