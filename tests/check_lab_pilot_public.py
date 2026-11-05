"""Read-only public verification after activation. Never needs the owner's password."""
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deploy'))
import bootstrap_lab_sandbox as expected

URL='https://lab-test.77-233-212-200.sslip.io'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def get(path,body=None):
    opener=urllib.request.build_opener(NoRedirect())
    request=urllib.request.Request(URL+path,data=body,headers={'Content-Type':'application/json'})
    try:
        with opener.open(request,timeout=20) as response:
            return response.status,response.headers,response.read(30000)
    except urllib.error.HTTPError as error:
        return error.code,error.headers,error.read(1000)


def main():
    for path,body in [('/lab-app',None),('/lab-app?test=anonymous',None),('/lab-app/api',b'{"action":"load"}')]:
        code,headers,_=get(path,body)
        assert code==401,(path,code)
        assert headers.get('WWW-Authenticate','').startswith('Basic ')
        assert 'no-store' in headers.get('Cache-Control','')
    code,_,raw=get('/healthz');assert code==200
    health=json.loads(raw)
    assert health.get('ok') is True and health.get('sandbox') is True
    for key,value in [('build',expected.EXPECTED_BUILD),('bundle_sha256',expected.BUNDLE_SHA256),('html_sha256',expected.EXPECTED_HTML),('payload_sha256',expected.EXPECTED_PAYLOAD)]:
        assert health.get(key)==value,key
    print('PUBLIC_PILOT_TLS_ANONYMOUS_GATE_AND_BUILD_VERIFIED')
    print(json.dumps({'build':health['build'],'protected':True,'url':URL+'/lab-app'},sort_keys=True))

if __name__=='__main__':main()
