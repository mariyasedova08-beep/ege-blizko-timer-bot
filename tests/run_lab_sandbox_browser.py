"""Run the lesson browser suite against the real packaged loopback HTTP server."""
import os
from pathlib import Path
import socket
import subprocess
import secrets
import tempfile
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0))
        port=probe.getsockname()[1]
    # Exercise the actual browser through the pilot gate with disposable credentials.
    sys.path.insert(0,str(ROOT/'deploy'))
    from lab_pilot_access import update
    temporary=tempfile.TemporaryDirectory()
    access_file=Path(temporary.name)/'users.json'
    password=secrets.token_urlsafe(24)
    update(access_file,'browser_test',password=password)
    process=subprocess.Popen([sys.executable,'deploy/lab_sandbox_server.py','--bundle','preview/lab-sandbox/bundle.json','--port',str(port),'--access-file',str(access_file)],cwd=ROOT,stdout=subprocess.DEVNULL)
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(50):
            if process.poll() is not None:raise RuntimeError('sandbox exited before readiness')
            try:
                with opener.open(f'http://127.0.0.1:{port}/healthz',timeout=1):break
            except Exception:time.sleep(.1)
        else:raise RuntimeError('sandbox readiness timeout')
        env=dict(os.environ,LAB_SANDBOX_URL=f'http://127.0.0.1:{port}/lab-app',LAB_PILOT_TEST_USER='browser_test',LAB_PILOT_TEST_PASSWORD=password)
        print('REAL_SANDBOX_HTTP_BROWSER_TEST',flush=True)
        subprocess.run(['node','tests/check_lab_review_browser.cjs'],cwd=ROOT,env=env,check=True)
    finally:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        temporary.cleanup()

if __name__=='__main__':main()
