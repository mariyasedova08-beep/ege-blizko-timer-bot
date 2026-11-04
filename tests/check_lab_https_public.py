"""Verify the exact public test domain with normal TLS validation; read-only API."""
import hashlib
import json
import urllib.request

URL='https://lab-test.77-233-212-200.sslip.io'
EXPECTED_BUNDLE = '7b14981d9e58785a4f3dc18a3350aeebe3e438457449963d08f87dc60afeb522'
EXPECTED_HTML = 'fb6ff2a3bec736eebdc2cebe21c555805e13c721a79a24d1cf186cc32f09545d'

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
