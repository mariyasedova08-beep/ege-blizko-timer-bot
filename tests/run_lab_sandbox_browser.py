"""Run the lesson browser suite against the real packaged loopback HTTP server."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0))
        port=probe.getsockname()[1]
    process=subprocess.Popen([sys.executable,'deploy/lab_sandbox_server.py','--bundle','preview/lab-sandbox/bundle.json','--port',str(port)],cwd=ROOT,stdout=subprocess.DEVNULL)
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(50):
            if process.poll() is not None:raise RuntimeError('sandbox exited before readiness')
            try:
                with opener.open(f'http://127.0.0.1:{port}/healthz',timeout=1):break
            except Exception:time.sleep(.1)
        else:raise RuntimeError('sandbox readiness timeout')
        env=dict(os.environ,LAB_SANDBOX_URL=f'http://127.0.0.1:{port}/lab-app')
        print('REAL_SANDBOX_HTTP_BROWSER_TEST',flush=True)
        subprocess.run(['node','tests/check_lab_review_browser.cjs'],cwd=ROOT,env=env,check=True)
    finally:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait()

if __name__=='__main__':main()
