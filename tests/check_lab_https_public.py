"""Verify the exact public test domain with normal TLS validation; read-only API."""
import hashlib
import json
import urllib.request

URL='https://lab-test.77-233-212-200.sslip.io'
EXPECTED_BUNDLE = 'db90347814e12df4682488f4f48d2db30dff36084f08caab70b3e6d319c89a49'
EXPECTED_HTML = 'a0194feb8f2b62e094a0ba790feda6259ab93f69f2bc227a3869895960307f0e'

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
