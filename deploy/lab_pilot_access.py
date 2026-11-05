#!/usr/bin/env python3
"""Manage accounts and one-time invitations for the isolated lab pilot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from lab_sandbox_server import access_password

DEFAULT_FILE=Path('/var/lib/ege-lab-sandbox/access/users.json')
DEFAULT_URL='https://lab-test.77-233-212-200.sslip.io'

def read_config(path):
    if path.is_symlink(): raise ValueError('Symlink user files are not supported')
    if not path.exists(): return {'version':1,'users':{},'invites':{}}
    if path.stat().st_size>65536: raise ValueError('User file too large')
    data=json.loads(path.read_text())
    if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('users'),dict):
        raise ValueError('Invalid existing user file; refusing to replace it')
    data.setdefault('invites',{})
    if not isinstance(data['invites'],dict): raise ValueError('Invalid invitations; refusing to replace them')
    return data

def write_config(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.pilot-users-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(data,stream);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,0o600)
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def update(path, username, revoke=False, days=14, password=None):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}',username): raise ValueError('Invalid username')
    data=read_config(path);users=data['users']
    if revoke:
        if username not in users: raise ValueError('User does not exist')
        users[username]['revoked']=True
    else:
        if username in users: raise ValueError('User already exists')
        if not 1<=days<=90 or not isinstance(password,str) or len(password)<12: raise ValueError('Password must be at least 12 characters; expiry 1–90 days')
        salt=secrets.token_hex(16)
        users[username]={'salt':salt,'digest':access_password(password,salt),'expires':time.time()+days*86400,'revoked':False}
    write_config(path,data)

def create_invite(path, days=7):
    if not 1<=days<=14: raise ValueError('Invitation expiry must be 1–14 days')
    token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
    data=read_config(path);data['invites'][digest]={'expires':time.time()+days*86400,'used':False}
    write_config(path,data)
    return token

def activation(args):
    expected=DEFAULT_FILE
    if args.file!=expected or os.geteuid()!=0: raise ValueError('Activation requires root and the fixed isolated sandbox path')
    expected.parent.chmod(0o755)
    target=Path('/etc/systemd/system/ege-lab-sandbox-preview.service.d/30-pilot-access.conf')
    content=('# EGE_LAB_PILOT_ACCESS_V1\n[Service]\nExecStart=\n'
      'ExecStart=/usr/bin/python3 -I /var/lib/ege-lab-sandbox/current/server.py '
      '--bundle /var/lib/ege-lab-sandbox/current/bundle.json --port 8768 '
      '--access-file '+str(expected)+'\n')
    if target.is_symlink() or (target.exists() and target.read_text()!=content): raise ValueError('Unknown existing pilot drop-in; refusing to overwrite')
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.pilot-access-',dir=target.parent)
    try:
        with os.fdopen(fd,'w') as stream: stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,0o644);os.replace(name,target)
    finally:
        if os.path.exists(name): os.unlink(name)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['add','revoke','invite'])
    parser.add_argument('username',nargs='?')
    parser.add_argument('--file',type=Path,default=DEFAULT_FILE)
    parser.add_argument('--days',type=int,default=14)
    parser.add_argument('--base-url',default=DEFAULT_URL)
    parser.add_argument('--activate',action='store_true',help='Write only the fixed sandbox service drop-in; service restart remains separate')
    args=parser.parse_args()
    if args.action=='invite':
        if args.username: parser.error('invite does not take a username')
        token=create_invite(args.file,args.days)
        print('INVITE_URL:',args.base_url.rstrip('/')+'/invite/'+token)
    else:
        if not args.username: parser.error('add/revoke requires a username')
        password=secrets.token_urlsafe(24) if args.action=='add' else None
        update(args.file,args.username,args.action=='revoke',args.days,password)
        if password: print('USERNAME:',args.username);print('PASSWORD_SHOW_ONCE:',password)
        else: print('PILOT_USER_REVOKED')
    if args.activate: activation(args)
    print('No service restarted. No invitation sent.')

if __name__=='__main__': main()
