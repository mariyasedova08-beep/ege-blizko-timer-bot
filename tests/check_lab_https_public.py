"""Verify the exact public test domain with normal TLS validation; read-only API."""
import hashlib
import json
import urllib.request

URL='https://lab-test.77-233-212-200.sslip.io'
EXPECTED_BUNDLE = '70bd6f9a9d729ccdd44fbf93533312974a99c7136ee3f093002449ed635622e2'
EXPECTED_HTML = 'a060082578cf1661885b33057ffc34d6721168b57bf22c57d6659878e99689b2'

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
    assert payload['data']['coverage']=={'substances':219,'reactions':1424,'medium_reactions':96}
    print('PUBLIC_TEST_HTTPS_CERTIFICATE_AND_BUILD_VERIFIED')
    print(json.dumps({'build':health['build'],'coverage':payload['data']['coverage'],'url':URL+'/lab-app'},sort_keys=True))

if __name__=='__main__':main()
