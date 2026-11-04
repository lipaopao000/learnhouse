"""Bounded live network/cache comparison; never clears production caches.

Cloud-side measurements compare identical 4MiB ranges from three locations.
Public measurements originate on this Mac, including TLS and access checks.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import threading
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--deployment-dir', type=Path, required=True)
parser.add_argument('--output-dir', type=Path, required=True)
args = parser.parse_args()
args.output_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
video = json.loads((args.deployment_dir / 'video-distribution/public-video.json').read_text())
code = '''
import urllib.request,pathlib,re,time,hashlib,json,statistics
path=PATH_VALUE
key=re.search(r'X-LearnHouse-Origin-Key "([a-f0-9]+)"',pathlib.Path('/opt/learnhouse-video-edge/nginx.conf').read_text()).group(1)
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
results=[];hashes={}
for name,url,headers in [
 ('home_to_cloud','http://100.64.0.6:8806'+path,{}),
 ('origin_cache_to_cloud','http://100.64.0.4:18887'+path,{'X-LearnHouse-Origin-Key':key}),
 ('cloud_cache_loopback','http://127.0.0.1:18887'+path,{})]:
 for i in range(3):
  req=urllib.request.Request(url,headers={**headers,'Host':'syyedu.toofun.fun','Range':'bytes=0-4194303'})
  start=time.monotonic()
  with op.open(req,timeout=45) as r:
   first=r.read(1);ttfb=time.monotonic()-start;body=first+r.read();elapsed=time.monotonic()-start
   assert r.status==206 and len(body)==4194304 and r.headers.get('Content-Range')=='bytes 0-4194303/277382743'
   digest=hashlib.sha256(body).hexdigest();hashes[name]=digest
   results.append({'leg':name,'attempt':i+1,'bytes':len(body),'seconds':round(elapsed,4),'ttfb_ms':round(ttfb*1000,1),'mbps':round(len(body)*8/elapsed/1e6,2),'cache':r.headers.get('X-LearnHouse-Origin-Cache') or r.headers.get('X-LearnHouse-Video-Cache'),'sha256':digest})
assert len(set(hashes.values()))==1,'Range contents differ across cache layers'
with op.open(urllib.request.Request('http://127.0.0.1:18887'+path,headers={'Host':'syyedu.toofun.fun','Range':'bytes=0-16777215'}),timeout=45) as r:
 body=r.read();assert r.status==206 and len(body)==16777216;hash16=hashlib.sha256(body).hexdigest()
print(json.dumps({'samples':results,'hash4':next(iter(hashes.values())),'hash16':hash16}))
'''.replace('PATH_VALUE', repr(video['path']))
r = subprocess.run(['ssh', '-o', 'HostName=100.64.0.3', 'toofun', 'python3 -'],
    input=code, text=True, capture_output=True, timeout=180)
if r.returncode:
    raise RuntimeError(r.stderr[-2000:])
cloud = json.loads(r.stdout)
(args.output_dir / 'cloud-network-samples.json').write_text(json.dumps(cloud, indent=2))
print(json.dumps({'cloud_completed': cloud['samples']}), flush=True)


def download(size, expected, barrier=None):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request('https://syyedu.toofun.fun' + video['path'], headers={
        'Range': f'bytes=0-{size-1}'})
    if barrier:
        barrier.wait(timeout=20)
    start = time.monotonic()
    with op.open(req, timeout=90) as response:
        first = response.read(1)
        ttfb = time.monotonic() - start
        body = first + response.read()
        elapsed = time.monotonic() - start
        assert response.status == 206 and len(body) == size
        assert response.headers.get('Content-Range') == f'bytes 0-{size-1}/{video["bytes"]}'
        assert hashlib.sha256(body).hexdigest() == expected
        cache = response.headers.get('X-LearnHouse-Video-Cache')
        assert cache == 'HIT'
    return {'bytes': size, 'seconds': round(elapsed, 4), 'ttfb_ms': round(ttfb*1000, 1),
        'mbps': round(size*8/elapsed/1e6, 2), 'cache': cache, 'sha256_verified': True}


public = [download(16777216, cloud['hash16']) for _ in range(3)]
print(json.dumps({'public_single_completed': public}), flush=True)
barrier = threading.Barrier(16)
started = time.monotonic()
with ThreadPoolExecutor(max_workers=16) as executor:
    concurrent = list(executor.map(lambda _: download(4194304, cloud['hash4'], barrier), range(16)))
elapsed = time.monotonic() - started
summary = {
    'cloud_medians': {name: {
        'mbps': statistics.median(x['mbps'] for x in cloud['samples'] if x['leg'] == name),
        'ttfb_ms': statistics.median(x['ttfb_ms'] for x in cloud['samples'] if x['leg'] == name)
    } for name in ['home_to_cloud', 'origin_cache_to_cloud', 'cloud_cache_loopback']},
    'public_single': {'samples': public, 'median_mbps': statistics.median(x['mbps'] for x in public),
        'median_ttfb_ms': statistics.median(x['ttfb_ms'] for x in public)},
    'public_16_concurrent': {'successes': len(concurrent), 'bytes': sum(x['bytes'] for x in concurrent),
        'seconds': round(elapsed, 3), 'aggregate_mbps': round(sum(x['bytes'] for x in concurrent)*8/elapsed/1e6, 2),
        'samples': concurrent},
    'limits': 'One Mac client; bounded ranges; cloud loopback is not public egress; not a sustained 200-viewer load test.'
}
(args.output_dir / 'speed-verification.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
