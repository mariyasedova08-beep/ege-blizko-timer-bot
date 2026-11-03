#!/usr/bin/env python3
"""Install ONLY the isolated loopback laboratory sandbox; never deploy the bot."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import stat
import subprocess
import tempfile
import time
import urllib.request

PACKAGE_COMMIT = '02ce32da78406067585c986e8e972236190f6005'
BUNDLE_SHA256 = '32b4b9bf354bf3a3210e6870c21ba4505b7dcde01c62d6250e3f0183e9be19c2'
EXPECTED_BUILD = '671f63038bad7558'
EXPECTED_HTML = '263cfac4c1a16f98169f5163a68246b5a6f8342f6008f1bf1167049ca4ff28a6'
EXPECTED_PAYLOAD = 'b2d25ff52edc29aadc5dddbad502cd45717150da14c3e506b95135d78eb164a4'
SERVER_SHA256 = '48eda362805eb73f2b9a02365609e5af811792dccdbdb5c8648094edd0b1a0df'
OLD_INSPECTOR_SHA256 = '576bf5ee70b75262a6b22824ca85b02b70ffa7d2fda49e767c8bd201c58124ff'
BASE = Path('/var/lib/ege-lab-sandbox')
UNIT_NAME = 'ege-lab-sandbox-preview.service'
UNIT_PATH = Path('/etc/systemd/system') / UNIT_NAME
INSPECTOR = Path('/usr/local/libexec/ege-lab-test-inspect.py')
PORT = 8768
UNIT = '''# EGE_LAB_SANDBOX_MANAGED_V1
[Unit]
Description=EGE BLIZKO isolated laboratory preview (no bot)
After=network.target

[Service]
Type=simple
DynamicUser=yes
WorkingDirectory=/var/lib/ege-lab-sandbox/current
ExecStart=/usr/bin/python3 -I /var/lib/ege-lab-sandbox/current/server.py --bundle /var/lib/ege-lab-sandbox/current/bundle.json --port 8768
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictAddressFamilies=AF_INET AF_UNIX
IPAddressDeny=any
IPAddressAllow=localhost
InaccessiblePaths=-/opt/bots -/root -/home
MemoryMax=256M
TasksMax=32
UMask=0077

[Install]
WantedBy=multi-user.target
'''
NEW_INSPECTOR = '#!/usr/bin/python3 -I\n"""Fixed read-only report. No user arguments or application imports."""\nimport hashlib\nimport json\nimport os\nfrom pathlib import Path\nimport stat\nimport sys\nimport urllib.request\n\nROOT = Path(\'/home/maria-admin/lab-test-20261028\')\nFILES = (\'ege_lab_webapp.py\', \'lab_standalone_preview.py\',\n         \'ege_lab_substances.py\', \'ege_lab_inorganic_reactions.py\',\n         \'ege_lab_exchange_matrix.py\', \'ege_lab_mn_cr_pdf_import.py\',\n         \'ege_task6_bank.py\', \'ege_task6_reactions.py\', \'ege_task6_progress.py\')\n\ndef report():\n    if len(sys.argv) != 1:\n        raise SystemExit(\'LAB_TEST_INSPECT_DENIED\')\n    if ROOT.resolve() != ROOT or not ROOT.is_dir():\n        raise SystemExit(\'LAB_TEST_DIRECTORY_UNAVAILABLE\')\n    result = {\'mode\': \'read-only\', \'files\': {}}\n    for name in FILES:\n        try:\n            fd = os.open(ROOT / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)\n            with os.fdopen(fd, \'rb\') as stream:\n                info = os.fstat(stream.fileno())\n                if not stat.S_ISREG(info.st_mode) or info.st_size > 2_000_000:\n                    result[\'files\'][name] = {\'state\': \'not-regular-or-too-large\'}\n                    continue\n                content = stream.read(2_000_001)\n            result[\'files\'][name] = {\'bytes\': len(content), \'sha256\': hashlib.sha256(content).hexdigest()}\n        except OSError:\n            result[\'files\'][name] = {\'state\': \'missing-or-unreadable\'}\n    try:\n        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))\n        with opener.open(\'http://127.0.0.1:8767/lab-app\', timeout=2) as response:\n            result[\'loopback_preview_http_status\'] = response.status\n    except Exception:\n        result[\'loopback_preview_http_status\'] = \'unavailable\'\n    try:\n        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(\'http://127.0.0.1:8768/healthz\', timeout=2) as response:\n            sandbox = json.loads(response.read(20_000))\n        allowed = (\'ok\', \'sandbox\', \'build\', \'bundle_sha256\', \'html_sha256\', \'payload_sha256\', \'coverage\')\n        result[\'sandbox_8768\'] = {key:sandbox[key] for key in allowed if key in sandbox}\n    except Exception:\n        result[\'sandbox_8768\'] = {\'ok\':False, \'state\':\'unavailable\'}\n    return result\n\nif __name__ == \'__main__\':\n    print(json.dumps(report(), sort_keys=True))\n'


def run(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def trusted_directory(path):
    if path.is_symlink():
        raise ValueError(f'symlink directory refused: {path}')
    if path.exists() and (not path.is_dir() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022):
        raise ValueError(f'non-root or writable directory refused: {path}')


def write_atomic(path, content, mode=0o644):
    trusted_directory(path.parent)
    if path.is_symlink():
        raise ValueError(f'symlink file refused: {path}')
    fd, tmp = tempfile.mkstemp(prefix='.lab-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def download(name, expected):
    if len(PACKAGE_COMMIT) != 40 or not all(c in '0123456789abcdef' for c in PACKAGE_COMMIT):
        raise ValueError('package commit not pinned')
    relative = {'bundle.json':'preview/lab-sandbox/bundle.json', 'server.py':'deploy/lab_sandbox_server.py'}[name]
    url = f'https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/{PACKAGE_COMMIT}/{relative}'
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read(8_000_001)
    if len(data) > 8_000_000 or digest(data) != expected:
        raise ValueError(f'package digest mismatch: {name}')
    return data


def current_target(base=BASE):
    current = base / 'current'
    if current.is_symlink():
        target = current.resolve(strict=True)
        if target.parent != base / 'releases' or not target.is_dir():
            raise ValueError('current points outside sandbox releases')
        return str(target)
    if current.exists():
        raise ValueError('current must be a managed symlink')
    return None


def activate(target, base=BASE):
    target = Path(target)
    if target.parent != base / 'releases' or target.is_symlink() or not target.is_dir():
        raise ValueError('release outside sandbox refused')
    current_target(base)
    temp = base / ('.current-' + secrets.token_hex(6))
    try:
        temp.symlink_to(target)
        os.replace(temp, base / 'current')
    finally:
        if temp.is_symlink():
            temp.unlink()


def backup(previous, active, enabled):
    folder = BASE / 'backups' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(3))
    folder.mkdir(mode=0o700)
    for name, source in (('unit', UNIT_PATH), ('inspector', INSPECTOR)):
        if source.exists():
            write_atomic(folder / name, source.read_bytes(), 0o600)
    receipt = {'previous':previous, 'active':active, 'enabled':enabled,
               'had_unit':UNIT_PATH.exists(), 'had_inspector':INSPECTOR.exists()}
    write_atomic(folder / 'receipt.json', json.dumps(receipt).encode(), 0o600)
    return folder


def restore(folder):
    if folder.parent != BASE / 'backups' or folder.is_symlink():
        raise ValueError('invalid backup')
    receipt = json.loads((folder / 'receipt.json').read_bytes())
    run('systemctl', 'stop', UNIT_NAME, check=False)
    if receipt['previous']:
        activate(receipt['previous'])
    elif (BASE / 'current').is_symlink():
        current_target()
        (BASE / 'current').unlink()
    for key, path in (('unit', UNIT_PATH), ('inspector', INSPECTOR)):
        if receipt['had_' + key]:
            write_atomic(path, (folder / key).read_bytes(), 0o644 if key == 'unit' else 0o755)
        elif path.exists():
            # Only our newly created unit can be removed; never delete another service.
            if key != 'unit' or path.read_text() != UNIT:
                raise ValueError('unknown file during rollback')
            run('systemctl', 'disable', UNIT_NAME, check=False)
            path.unlink()
    run('systemctl', 'daemon-reload')
    if receipt['enabled']:
        run('systemctl', 'enable', UNIT_NAME)
    else:
        run('systemctl', 'disable', UNIT_NAME, check=False)
    if receipt['active']:
        run('systemctl', 'start', UNIT_NAME)
    print('SANDBOX_ROLLBACK_COMPLETE')


def health():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{PORT}/healthz', timeout=2) as response:
        result = json.loads(response.read(20_000))
    if result.get('sandbox') is not True or result.get('bundle_sha256') != BUNDLE_SHA256:
        raise ValueError('wrong sandbox build running')
    for key, expected in (('build', EXPECTED_BUILD), ('html_sha256', EXPECTED_HTML), ('payload_sha256', EXPECTED_PAYLOAD)):
        if result.get(key) != expected:
            raise ValueError('wrong sandbox content: ' + key)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('ROOT_CONSOLE_REQUIRED')
    for program in ('systemctl', 'python3'):
        if not shutil.which(program):
            raise SystemExit('MISSING_PROGRAM: ' + program)
    trusted_directory(BASE)
    if args.rollback:
        backups = sorted((BASE / 'backups').glob('*/receipt.json'))
        if not backups:
            raise SystemExit('NO_SANDBOX_BACKUP')
        restore(backups[-1].parent)
        return
    trusted_directory(UNIT_PATH.parent)
    if UNIT_PATH.exists() and (UNIT_PATH.is_symlink() or UNIT_PATH.read_text() != UNIT):
        raise SystemExit('UNKNOWN_EXISTING_SANDBOX_UNIT_REFUSED')
    if INSPECTOR.is_symlink() or not INSPECTOR.is_file() or INSPECTOR.stat().st_uid != 0:
        raise SystemExit('READONLY_INSPECTOR_NOT_FOUND_OR_UNTRUSTED')
    if digest(INSPECTOR.read_bytes()) not in {OLD_INSPECTOR_SHA256, digest(NEW_INSPECTOR.encode())}:
        raise SystemExit('EXISTING_INSPECTOR_CHANGED_REFUSING_OVERWRITE')
    active = run('systemctl', 'is-active', '--quiet', UNIT_NAME, check=False).returncode == 0
    enabled = run('systemctl', 'is-enabled', '--quiet', UNIT_NAME, check=False).returncode == 0
    if not active:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', PORT))
    # All downloads are hash-checked before service configuration is touched.
    bundle = download('bundle.json', BUNDLE_SHA256)
    server = download('server.py', SERVER_SHA256)
    for folder in (BASE, BASE / 'releases', BASE / 'backups'):
        trusted_directory(folder)
        folder.mkdir(mode=0o755, exist_ok=True)
        os.chmod(folder, 0o755)
    previous = current_target()
    release = BASE / 'releases' / BUNDLE_SHA256[:16]
    trusted_directory(release)
    release.mkdir(mode=0o755, exist_ok=True)
    os.chmod(release, 0o755)
    for name, content in (('bundle.json', bundle), ('server.py', server)):
        path = release / name
        if path.exists() and path.read_bytes() != content:
            raise ValueError('immutable release content mismatch')
        write_atomic(path, content)
    saved = backup(previous, active, enabled)
    print('SANDBOX_BACKUP: ' + str(saved))
    write_atomic(BASE / 'installer.py', Path(__file__).read_bytes(), 0o600)
    try:
        write_atomic(UNIT_PATH, UNIT.encode())
        write_atomic(INSPECTOR, NEW_INSPECTOR.encode(), 0o755)
        activate(release)
        run('systemctl', 'daemon-reload')
        run('systemctl', 'restart', UNIT_NAME)
        result = None
        for _ in range(15):
            try:
                result = health()
                break
            except Exception:
                time.sleep(1)
        if result is None:
            raise RuntimeError('sandbox healthcheck failed')
        run('systemctl', 'enable', UNIT_NAME)
        print(json.dumps(result, sort_keys=True))
        print('SANDBOX_READY_LOOPBACK_ONLY http://127.0.0.1:8768/lab-app')
        print('NO_PRODUCTION_DEPLOYMENT_PERFORMED')
    except BaseException:
        restore(saved)
        raise


if __name__ == '__main__':
    main()
