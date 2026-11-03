#!/usr/bin/env python3
"""Manage only isolated pilot users. Never sends invitations or restarts services."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from lab_sandbox_server import access_password


def update(path, username, revoke=False, days=14, password=None):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}', username):
        raise ValueError('Use a username of 1–48 Latin letters, digits, _ or -')
    if path.is_symlink():
        raise ValueError('Symlink user files are not supported')
    if path.exists():
        if path.stat().st_size > 65536:
            raise ValueError('User file too large')
        config=json.loads(path.read_text())
        if config.get('version') != 1 or not isinstance(config.get('users'),dict):
            raise ValueError('Invalid existing user file; refusing to replace it')
    else:
        config={'version':1,'users':{}}
    users=config['users']
    if revoke:
        if username not in users:
            raise ValueError('User does not exist')
        users[username]['revoked']=True
    else:
        if username in users:
            raise ValueError('User already exists; use a new username')
        if not 1 <= days <= 90 or not isinstance(password,str) or len(password)<20:
            raise ValueError('Expiry must be 1–90 days and password at least 20 characters')
        salt=secrets.token_hex(16)
        users[username]={'salt':salt,'digest':access_password(password,salt),'expires':time.time()+days*86400,'revoked':False}
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.pilot-users-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(config,stream);stream.flush();os.fsync(stream.fileno())
        # DynamicUser must read hashes; no plaintext passwords are stored.
        os.chmod(name,0o644)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['add','revoke'])
    parser.add_argument('username')
    parser.add_argument('--file',type=Path,default=Path('/var/lib/ege-lab-sandbox/access/users.json'))
    parser.add_argument('--days',type=int,default=14)
    parser.add_argument('--activate',action='store_true',help='Write only the fixed sandbox service drop-in; service restart remains separate')
    args=parser.parse_args()
    password=secrets.token_urlsafe(24) if args.action=='add' else None
    update(args.file,args.username,args.action=='revoke',args.days,password)
    if args.activate:
        expected=Path('/var/lib/ege-lab-sandbox/access/users.json')
        if args.file != expected or os.geteuid()!=0:
            raise ValueError('Activation requires root and the fixed isolated sandbox path')
        expected.parent.chmod(0o755)
        target=Path('/etc/systemd/system/ege-lab-sandbox-preview.service.d/30-pilot-access.conf')
        content=('# EGE_LAB_PILOT_ACCESS_V1\n[Service]\nExecStart=\n'
                 'ExecStart=/usr/bin/python3 -I /var/lib/ege-lab-sandbox/current/server.py '
                 '--bundle /var/lib/ege-lab-sandbox/current/bundle.json --port 8768 '
                 '--access-file '+str(expected)+'\n')
        if target.is_symlink() or (target.exists() and target.read_text()!=content):
            raise ValueError('Unknown existing pilot drop-in; refusing to overwrite')
        target.parent.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.pilot-access-',dir=target.parent)
        try:
            with os.fdopen(fd,'w') as stream:
                stream.write(content);stream.flush();os.fsync(stream.fileno())
            os.chmod(name,0o644);os.replace(name,target)
        finally:
            if os.path.exists(name):os.unlink(name)
    if password:
        print('USERNAME:',args.username)
        print('PASSWORD_SHOW_ONCE:',password)
    else:print('PILOT_USER_REVOKED')
    print('No service restarted. No invitation sent.')


if __name__=='__main__':main()
