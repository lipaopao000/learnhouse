"""Live cache/ACL regression using a disposable private course and tiny MP4.

Requires an SSH tunnel for a pre-cutover edge URL, or the final HTTPS site.
Only the generated course is deleted. Credentials/tokens never enter output.
"""
import argparse
import hashlib
import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request
import uuid

parser = argparse.ArgumentParser()
parser.add_argument('--deployment-dir', type=pathlib.Path, required=True)
parser.add_argument('--edge-base', default='http://127.0.0.1:19887')
args = parser.parse_args()
root = args.deployment_dir.resolve()
output = root / 'video-distribution'
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
    fixture = (output / 'security-fixture.mp4').read_bytes()
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
    for label, authenticated, expected in [
        ('private_anonymous_before_cache', False, (401, 403)),
        ('private_admin_cache_fill', True, (200,)),
        ('private_admin_cache_hit', True, (200,)),
        ('private_anonymous_after_cache', False, (401, 403)),
    ]:
        status, headers, body = call(path, target=args.edge_base, auth=authenticated)
        cache = headers.get('x-learnhouse-video-cache')
        results.append({'check': label, 'status': status, 'cache': cache, 'bytes': len(body)})
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
