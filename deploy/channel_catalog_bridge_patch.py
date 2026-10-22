#!/usr/bin/python3
"""Guarded byte patch for the VPS-only OGE adapter; never imports bot code."""
import ast
import hashlib
from pathlib import Path

OLD = b"    def public_rows(include_hidden=False):\n        rows = list(original_rows(include_hidden=include_hidden))\n"
NEW = b"    def public_rows(include_hidden=False, assigned_only=False):\n        rows = list(original_rows(include_hidden=include_hidden, assigned_only=assigned_only))\n        if assigned_only:\n            return rows\n"


def transform(data):
    tree = ast.parse(data)
    bridge = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == '_bridge_catalog')
    lines = data.splitlines(keepends=True)
    start = sum(map(len, lines[:bridge.lineno - 1]))
    end = sum(map(len, lines[:bridge.end_lineno]))
    fragment = data[start:end]
    if fragment.count(NEW) == 1 and OLD not in fragment:
        return data
    if fragment.count(OLD) != 1 or NEW in fragment:
        raise ValueError('UNREVIEWED_ADAPTER')
    result = data[:start] + fragment.replace(OLD, NEW, 1) + data[end:]
    compile(result, 'oge_classification_trainer.py', 'exec')
    return result


# Production release scope: exactly one existing file, no database writes.
import fcntl
import json
import os
import stat
import subprocess
import tempfile
import time
import urllib.request

TARGET = Path('/opt/bots/ege-blizko/oge_classification_trainer.py')
STATE = Path('/var/lib/ege-blizko-channel-catalog-20261022')
BEFORE = '0d8a8c2133c2fa611f9ce60cbcea32698d92a7746b2e2e3a71b815cadd3c0a08'
AFTER = 'bf47b1f261be1e45e1275debee376c557a7db237a1b3f02b0c9ed3ba7377d00c'
PUBLIC = Path('/opt/bots/ege-blizko/public_channel_trainers.py')
PUBLIC_HASH = 'be7b8d058da8cfd90ed57f9dae1f9e7769b448763ef56a8a18bdbebeab8c9a53'
RELEASE = 'EGE-CHANNEL-CATALOG-20261022-REVIEWED'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('NON_REGULAR_FILE')


def atomic(path, data, metadata):
    fd, temporary = tempfile.mkstemp(prefix='.channel-catalog-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fchown(stream.fileno(), metadata['uid'], metadata['gid'])
            os.fchmod(stream.fileno(), metadata['mode'])
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def restart():
    subprocess.run(['systemctl', 'restart', 'ege-blizko'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)


def healthy():
    for _ in range(15):
        active = subprocess.run(['systemctl', 'is-active', '--quiet', 'ege-blizko'],
                                timeout=10).returncode == 0
        try:
            with urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3) as response:
                if active and response.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def restore():
    regular(STATE / 'original.py')
    regular(STATE / 'metadata.json')
    original = (STATE / 'original.py').read_bytes()
    if digest(original) != BEFORE:
        raise ValueError('BACKUP_HASH_MISMATCH')
    metadata = json.loads((STATE / 'metadata.json').read_text())
    atomic(TARGET, original, metadata)
    restart()
    if not healthy():
        raise ValueError('ROLLBACK_HEALTH_FAILED')


def release(rollback=False):
    regular(TARGET)
    original = TARGET.read_bytes()
    current = digest(original)
    if rollback:
        if current != AFTER:
            raise ValueError('ROLLBACK_TARGET_CHANGED')
        restore()
        print('CHANNEL_CATALOG_ROLLBACK_OK_NO_DATABASE_CHANGES')
        return
    regular(PUBLIC)
    if digest(PUBLIC.read_bytes()) != PUBLIC_HASH:
        raise ValueError('PUBLIC_ROUTER_CHANGED')
    if current == AFTER:
        if not healthy():
            raise ValueError('ALREADY_PATCHED_BUT_UNHEALTHY')
        print('CHANNEL_CATALOG_ALREADY_FIXED_NO_RESTART')
        return
    if current != BEFORE:
        raise ValueError('PRODUCTION_FILE_CHANGED')
    result = transform(original)
    if digest(result) != AFTER:
        raise ValueError('PATCH_HASH_MISMATCH')
    if not healthy():
        raise ValueError('SERVICE_UNHEALTHY_BEFORE_PATCH')
    info = TARGET.stat()
    metadata = {'uid': info.st_uid, 'gid': info.st_gid,
                'mode': stat.S_IMODE(info.st_mode)}
    STATE.mkdir(mode=0o700, parents=False, exist_ok=False)
    atomic(STATE / 'original.py', original, {'uid': 0, 'gid': 0, 'mode': 0o600})
    atomic(STATE / 'metadata.json', json.dumps(metadata).encode(),
           {'uid': 0, 'gid': 0, 'mode': 0o600})
    regular(TARGET)
    if TARGET.read_bytes() != original:
        raise ValueError('TARGET_CHANGED_DURING_BACKUP')
    try:
        atomic(TARGET, result, metadata)
        restart()
        if not healthy():
            raise ValueError('HEALTH_FAILED_AFTER_PATCH')
    except Exception:
        # Atomic replacement can succeed before a later fsync raises.
        if digest(TARGET.read_bytes()) == AFTER:
            restore()
            print('CHANNEL_CATALOG_AUTO_ROLLBACK_OK_NO_DATABASE_CHANGES')
        raise
    print('CHANNEL_CATALOG_PATCH_OK_BACKUP_AND_HEALTH_VERIFIED')


if __name__ == '__main__':
    import sys
    try:
        if len(sys.argv) == 2 and sys.argv[1] in (RELEASE, RELEASE + '-ROLLBACK'):
            if os.geteuid() != 0:
                raise ValueError('ROOT_REQUIRED')
            os.umask(0o077)
            with open('/run/lock/ege-blizko-autodeploy.lock', 'a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                release(rollback=sys.argv[1].endswith('-ROLLBACK'))
        elif len(sys.argv) == 2:
            data = Path(sys.argv[1]).read_bytes()
            patched = transform(data)
            print('INPUT_SHA256=' + digest(data))
            print('OUTPUT_SHA256=' + digest(patched))
            print('ALREADY_FIXED' if data == patched else 'PATCH_VALIDATED_NOT_APPLIED')
        else:
            raise ValueError('INVALID_ARGUMENTS')
    except Exception as error:
        # Never print source, credentials, DB content or private tracebacks.
        code = str(error) if isinstance(error, ValueError) and str(error).isidentifier() else type(error).__name__
        print('CHANNEL_CATALOG_RELEASE_STOPPED: ' + code)
        sys.exit(1)
