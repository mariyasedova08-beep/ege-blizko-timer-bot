"""Verify the exact public test domain with normal TLS validation; read-only API."""
import hashlib
import json
import urllib.request

URL='https://lab-test.77-233-212-200.sslip.io'
EXPECTED_BUNDLE = 'b7686b7b437a9ae650a15ac3a12b118a56925394c740d99aedadd4ec74cf1457'
EXPECTED_HTML = 'd869c3b1953d11450c5e0f2324ab3217e4211735f80ed2844948a4bc880c5492'

def get(path,body=None):
    request=urllib.request.Request(URL+path,data=body,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=20) as response:
        assert response.status==200
        assert response.url==URL+path, 'unexpected redirect'
        return response.read(4_000_001)


def main():
    health=json.loads(get('/healthz'))
    assert health.get('ok') is True and health.get('sandbox') is True
    assert health['bundle_sha256']==EXPECTED_BUNDLE
    assert hashlib.sha256(get('/lab-app')).hexdigest()==EXPECTED_HTML
    payload=json.loads(get('/lab-app/api',b'{"action":"load"}'))
    assert payload['ok'] is True and payload['data']['preview'] is True
    assert payload['data']['coverage']=={'substances':219,'reactions':1434,'medium_reactions':96}
    print('PUBLIC_TEST_HTTPS_CERTIFICATE_AND_BUILD_VERIFIED')
    print(json.dumps({'build':health['build'],'coverage':payload['data']['coverage'],'url':URL+'/lab-app'},sort_keys=True))

if __name__=='__main__':main()
