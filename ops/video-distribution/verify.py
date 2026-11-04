"""Live cache/ACL regression using a disposable private course and tiny MP4.

Requires an SSH tunnel for a pre-cutover edge URL, or the final HTTPS site.
Only the generated course is deleted. Credentials/tokens never enter output.
"""
import argparse
import base64
import hashlib
import json
import pathlib
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

parser = argparse.ArgumentParser()
parser.add_argument('--deployment-dir', type=pathlib.Path, required=True)
parser.add_argument('--edge-base', default='http://127.0.0.1:19887')
parser.add_argument('--fixture-size-mib', type=int, default=0, choices=range(0, 17))
parser.add_argument('--verify-origin', action='store_true')
parser.add_argument('--verify-prefetch', action='store_true')
parser.add_argument('--output-dir', type=pathlib.Path)
args = parser.parse_args()
root = args.deployment_dir.resolve()
output = args.output_dir or root / 'video-distribution'
output.mkdir(mode=0o700, parents=True, exist_ok=True)
base = 'https://syyedu.toofun.fun'
env = json.loads((root / 'config/env.private.json').read_text())
token = None
results = []
course_uuid = None


def call(path, *, data=None, method=None, auth=True, target=base, headers=None):
    h = {'Host': 'syyedu.toofun.fun', 'Origin': base, **(headers or {})}
    if auth and token:
        h['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(target + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


def api(path, data, *, form=False, method='POST'):
    raw = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
    status, _, body = call(path, data=raw, method=method, headers={
        'Content-Type': 'application/x-www-form-urlencoded' if form else 'application/json'})
    if status != 200:
        raise RuntimeError(f'{method} {path}: {status}: {body[:300]!r}')
    return json.loads(body)


login = api('/api/v1/auth/login', {
    'username': env['LEARNHOUSE_INITIAL_ADMIN_EMAIL'],
    'password': env['LEARNHOUSE_INITIAL_ADMIN_PASSWORD'], 'org_slug': 'default'}, form=True)
token = login['tokens']['access_token']
try:
    course = api('/api/v1/courses/?org_id=1', {
        'name': 'Disposable video cache ACL check', 'description': 'Temporary deployment verification',
        'public': 'false', 'about': 'Deleted automatically after verification'}, form=True)
    course_uuid = course['course_uuid']
    (output / 'fixture-state.json').write_text(json.dumps({'course_uuid': course_uuid}))
    chapter = api('/api/v1/chapters/', {
        'name': 'Temporary', 'org_id': 1, 'course_id': course['id']})
    fixture = (root / 'video-distribution/security-fixture.mp4').read_bytes()
    if args.fixture_size_mib:
        padding = args.fixture_size_mib * 1048576 - len(fixture)
        assert padding >= 8
        # A valid ISO BMFF free box pads the synthetic clip to a known size.
        fixture += struct.pack('>I4s', padding, b'free') + bytes(padding - 8)
    boundary = 'LearnHouseCacheCheck' + uuid.uuid4().hex
    chunks = []
    for key, value in {'name': 'Temporary video', 'chapter_id': chapter['id'], 'details': '{}'}.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    chunks.extend([
        f'--{boundary}\r\nContent-Disposition: form-data; name="video_file"; filename="check.mp4"\r\nContent-Type: video/mp4\r\n\r\n'.encode(),
        fixture, f'\r\n--{boundary}--\r\n'.encode()])
    status, _, body = call('/api/v1/activities/video', data=b''.join(chunks), headers={
        'Content-Type': 'multipart/form-data; boundary=' + boundary})
    assert status == 200, (status, body[:300])
    activity = json.loads(body)
    org = json.loads(call('/api/v1/orgs/slug/default')[2])
    path = '/api/v1/stream/video/' + '/'.join([
        org['org_uuid'], course_uuid, activity['activity_uuid'], activity['content']['filename']])
    (output / 'fixture-state.json').write_text(json.dumps({'course_uuid': course_uuid, 'path': path}))
    if args.verify_prefetch:
        # Observe the timer; do NOT trigger the worker manually.
        started = time.monotonic()
        deadline = started + 300
        entry = None
        while time.monotonic() < deadline:
            script = "$ProgressPreference='SilentlyContinue'; Get-Content D:\\deploy\\LearnHouseVideo\\prefetch-state.json -Raw -ErrorAction SilentlyContinue"
            command = 'powershell -NoProfile -EncodedCommand ' + base64.b64encode(script.encode('utf-16le')).decode()
            probe = subprocess.run(['ssh', 'icu-jump', command], capture_output=True, timeout=15)
            try:
                state = json.loads(probe.stdout.decode('utf-8-sig'))
                entry = state.get(path)
            except (ValueError, UnicodeError):
                entry = None
            if entry and entry.get('complete') and entry.get('next_offset') == len(fixture):
                break
            time.sleep(5)
        assert entry and entry.get('complete') and entry.get('next_offset') == len(fixture), 'Unattended prefetch did not complete'
        results.append({'check': 'unattended_prefetch_before_view', 'complete': True,
            'bytes': len(fixture), 'wait_seconds': round(time.monotonic()-started, 3)})
    for label, authenticated, expected in [
        ('private_anonymous_before_cache', False, (401, 403)),
        ('private_admin_cache_fill', True, (200,)),
        ('private_admin_cache_hit', True, (200,)),
        ('private_anonymous_after_cache', False, (401, 403)),
    ]:
        started = time.monotonic()
        status, headers, body = call(path, target=args.edge_base, auth=authenticated)
        elapsed = time.monotonic() - started
        cache = headers.get('x-learnhouse-video-cache')
        results.append({'check': label, 'status': status, 'cache': cache, 'bytes': len(body),
            'seconds': round(elapsed, 4), 'mbps': round(len(body)*8/elapsed/1e6, 2) if authenticated else None})
        assert status in expected, results[-1]
        if authenticated:
            assert body == fixture, 'Cached private video bytes differ'
        if label == 'private_admin_cache_hit':
            assert cache == 'HIT', 'Private fixture must be cached before testing denial'
    # Browser cookie sessions must remain valid through the auth subrequest.
    status, headers, body = call(path, target=args.edge_base, auth=False,
        headers={'Cookie': 'LH_access=' + token, 'Range': 'bytes=0-31'})
    results.append({'check': 'private_cookie_range', 'status': status, 'cache': headers.get('x-learnhouse-video-cache')})
    assert status == 206 and body == fixture[:32], results[-1]
    if args.verify_origin:
        config = {'path': path, 'token': token, 'expected': hashlib.sha256(fixture).hexdigest()}
        code = '''
import json,pathlib,re,urllib.request,hashlib,time
config=CONFIG_VALUE
key=re.search(r'X-LearnHouse-Origin-Key "([a-f0-9]+)"',pathlib.Path('/opt/learnhouse-video-edge/nginx.conf').read_text()).group(1)
url='http://100.64.0.4:18887'+config['path']
req=urllib.request.Request(url,headers={'X-LearnHouse-Origin-Key':key,'Authorization':'Bearer '+config['token']})
started=time.monotonic()
with urllib.request.urlopen(req,timeout=45) as r:
 body=r.read();elapsed=time.monotonic()-started;cache=r.headers.get('X-LearnHouse-Origin-Cache')
 assert r.status==200 and cache=='HIT' and hashlib.sha256(body).hexdigest()==config['expected']
 print(json.dumps({'check':'private_origin_cache_hit','status':r.status,'cache':cache,'bytes':len(body),'sha256_verified':True,'seconds':round(elapsed,4),'mbps':round(len(body)*8/elapsed/1e6,2)}))
'''.replace('CONFIG_VALUE', repr(config))
        proc = subprocess.run(['ssh', '-o', 'HostName=100.64.0.3', 'toofun', 'python3 -'],
            input=code, text=True, capture_output=True, timeout=60)
        assert proc.returncode == 0, proc.stderr[-1500:]
        results.append(json.loads(proc.stdout))
finally:
    if course_uuid:
        status, _, body = call('/api/v1/courses/' + course_uuid, method='DELETE')
        results.append({'check': 'fixture_cleanup', 'status': status})
        assert status == 200, (status, body[:200])
    (output / 'acl-verification.json').write_text(json.dumps(results, indent=2))
if course_uuid:
    status, _, _ = call(path, target=args.edge_base)
    results.append({'check': 'deleted_resource_even_admin', 'status': status})
    assert status == 403, 'Cached bytes must be inaccessible after resource deletion'
    (output / 'acl-verification.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
