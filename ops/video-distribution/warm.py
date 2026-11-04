"""Prewarm bounded ranges and compare full hashes on origin and edge.

No credentials are stored on the cloud host. Optional private-course JWT travels
only through encrypted SSH stdin, never in command arguments or output.
"""
import argparse
import json
import pathlib
import re
import subprocess
import urllib.parse
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--deployment-dir', required=True, type=pathlib.Path)
parser.add_argument('--path', required=True)
parser.add_argument('--private', action='store_true')
parser.add_argument('--expected-sha256')
parser.add_argument('--origin-ip', default='100.64.0.4', choices=['100.64.0.4', '100.64.0.8'])
args = parser.parse_args()
assert re.fullmatch(r'/api/v1/stream/(?:video|block)/[A-Za-z0-9_./-]+', args.path)
assert '..' not in args.path.split('/')
if args.expected_sha256:
    assert re.fullmatch(r'[a-f0-9]{64}', args.expected_sha256)
config = {'path': args.path, 'origin_ip': args.origin_ip, 'token': None, 'expected': args.expected_sha256}
if args.private:
    env = json.loads((args.deployment_dir / 'config/env.private.json').read_text())
    form = urllib.parse.urlencode({'username': env['LEARNHOUSE_INITIAL_ADMIN_EMAIL'],
        'password': env['LEARNHOUSE_INITIAL_ADMIN_PASSWORD'], 'org_slug': 'default'}).encode()
    req = urllib.request.Request('https://syyedu.toofun.fun/api/v1/auth/login', data=form,
        headers={'Origin': 'https://syyedu.toofun.fun'})
    with urllib.request.urlopen(req, timeout=30) as r:
        config['token'] = json.load(r)['tokens']['access_token']
code = '''
import json,pathlib,re,time,hashlib,urllib.request
config=CONFIG_VALUE
key=re.search(r'X-LearnHouse-Origin-Key "([a-f0-9]+)"',pathlib.Path('/opt/learnhouse-video-edge/nginx.conf').read_text()).group(1)
results=[]
for name,base in [('origin','http://'+config['origin_ip']+':18887'),('edge','http://127.0.0.1:18887')]:
    headers={'Host':'syyedu.toofun.fun'}
    if name=='origin': headers['X-LearnHouse-Origin-Key']=key
    if config['token']: headers['Authorization']='Bearer '+config['token']
    url=base+config['path']
    with urllib.request.urlopen(urllib.request.Request(url,method='HEAD',headers=headers),timeout=30) as r:
        size=int(r.headers['Content-Length'])
    start=time.monotonic();digest=hashlib.sha256();hits=0;retries=0
    for offset in range(0,size,4194304):
        end=min(offset+4194304,size)-1
        for attempt in range(4):
            try:
                req=urllib.request.Request(url,headers={**headers,'Range':f'bytes={offset}-{end}'})
                with urllib.request.urlopen(req,timeout=45) as r:
                    body=r.read();status=r.status
                    cache=r.headers.get('X-LearnHouse-Video-Cache') or r.headers.get('X-LearnHouse-Origin-Cache')
                    expected_range=f'bytes {offset}-{end}/{size}'
                    assert status==206 and r.headers.get('Content-Range')==expected_range and len(body)==end-offset+1, 'Incomplete range'
                digest.update(body);hits+=cache=='HIT';break
            except Exception:
                if attempt==3: raise
                retries+=1;time.sleep(attempt+1)
    result={'target':name,'bytes':size,'sha256':digest.hexdigest(),'cache_hits':hits,'ranges':(size+4194303)//4194304,'retries':retries,'seconds':round(time.monotonic()-start,3)}
    if config['expected']: assert result['sha256']==config['expected'], 'Source hash mismatch'
    results.append(result)
assert results[0]['sha256']==results[1]['sha256'], 'Origin/edge hash mismatch'
print(json.dumps(results))
'''.replace('CONFIG_VALUE', repr(config))
process = subprocess.run(['ssh', '-o', 'HostName=100.64.0.3', 'toofun', 'python3 -'],
    input=code, text=True, capture_output=True, timeout=1200)
if process.returncode:
    raise RuntimeError(process.stderr[-2500:])
results = json.loads(process.stdout)
output = args.deployment_dir / 'video-distribution/warm-verification.json'
output.write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
