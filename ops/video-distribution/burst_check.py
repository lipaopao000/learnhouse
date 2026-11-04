"""Bounded public cache burst check, up to 200 requests of at most 4MiB."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import ssl
import threading
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--deployment-dir', type=Path, required=True)
parser.add_argument('--output-dir', type=Path, required=True)
parser.add_argument('--clients', type=int, default=200)
parser.add_argument('--range-mib', type=int, default=1)
args = parser.parse_args()
assert 1 <= args.clients <= 200 and 1 <= args.range_mib <= 4
video = json.loads((args.deployment_dir / 'video-distribution/public-video.json').read_text())
size = args.range_mib * 1048576
assert size <= video['bytes']
context = ssl.create_default_context()
barrier = threading.Barrier(args.clients)


def download(wait=False):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
    req = urllib.request.Request('https://syyedu.toofun.fun' + video['path'], headers={'Range': f'bytes=0-{size-1}'})
    if wait:
        barrier.wait(timeout=30)
    start = time.monotonic()
    try:
        with op.open(req, timeout=90) as r:
            first = r.read(1)
            ttfb = time.monotonic() - start
            body = first + r.read()
            assert r.status == 206 and len(body) == size
            assert r.headers.get('Content-Range') == f'bytes 0-{size-1}/{video["bytes"]}'
            assert r.headers.get('X-LearnHouse-Video-Cache') == 'HIT'
        return {'success': True, 'bytes': len(body), 'ttfb_ms': round(ttfb*1000, 1),
            'seconds': round(time.monotonic()-start, 4), 'sha256': hashlib.sha256(body).hexdigest()}
    except Exception as e:
        return {'success': False, 'error': str(e), 'seconds': round(time.monotonic()-start, 4)}


baseline = download()
assert baseline['success'], baseline
started = time.monotonic()
with ThreadPoolExecutor(max_workers=args.clients) as pool:
    samples = list(pool.map(lambda _: download(True), range(args.clients)))
elapsed = time.monotonic() - started
successes = [x for x in samples if x['success'] and x['sha256'] == baseline['sha256']]
ttfb = sorted(x['ttfb_ms'] for x in successes)
result = {'clients': args.clients, 'range_bytes': size, 'successes': len(successes),
    'failures': len(samples)-len(successes), 'total_bytes': sum(x['bytes'] for x in successes),
    'seconds': round(elapsed, 3), 'aggregate_mbps': round(sum(x['bytes'] for x in successes)*8/elapsed/1e6, 2),
    'ttfb_p50_ms': ttfb[len(ttfb)//2] if ttfb else None,
    'ttfb_p95_ms': ttfb[min(len(ttfb)-1,int(len(ttfb)*.95))] if ttfb else None,
    'samples': samples, 'limitation': 'Single-client burst test; not sustained playback by 200 independent viewers.'}
args.output_dir.mkdir(parents=True, exist_ok=True)
(args.output_dir / 'concurrent-verification.json').write_text(json.dumps(result, indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='samples'}, indent=2))
assert result['failures'] == 0, 'Some public requests failed or returned inconsistent data'
