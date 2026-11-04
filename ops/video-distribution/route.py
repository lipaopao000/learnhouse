"""Switch only LearnHouse's Lucky backend using the canonical versioned rule.

Uses the existing lucky-api client and its private credential file. For writes
through SSH, forward a loopback port to cloud 127.0.0.1:16601 and pass it here.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
import pathlib
import runpy
import urllib.parse

parser = argparse.ArgumentParser()
parser.add_argument('--deployment-dir', type=pathlib.Path, required=True)
parser.add_argument('--target', choices=['edge', 'home'], required=True)
parser.add_argument('--tunnel-port', type=int)
args = parser.parse_args()
client = runpy.run_path('/Users/svipba/bin/lucky-api', run_name='lucky_api_helpers')
config = client['config']()
if args.tunnel_port:
    assert 1024 < args.tunnel_port < 65536
    config['base_url'] = 'http://127.0.0.1:' + str(args.tunnel_port) + urllib.parse.urlsplit(config['base_url']).path
path = '/api/webservice/rule/PevVkiqiyJ7ukGNi'
before = client['request'](config, 'GET', path)
assert before.get('version') and isinstance(before.get('rule'), dict)
folder = args.deployment_dir / 'video-distribution'
folder.mkdir(mode=0o700, exist_ok=True)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
client['secure_write'](folder / ('lucky-before-' + stamp + '.private.json'), before)
payload = copy.deepcopy(before['rule'])
rule = next(x for x in payload['ProxyList'] if x['Key'] == 'Rf0aSQjk2f8tvqrw')
assert rule['Domains'] == ['syyedu.toofun.fun']
assert rule['Locations'] in [['http://100.64.0.6:8806'], ['http://127.0.0.1:18887']]
old_locations = rule['Locations']
rule['Locations'] = ['http://127.0.0.1:18887'] if args.target == 'edge' else ['http://100.64.0.6:8806']
payload['ExpectedVersion'] = before['version']
client['secure_write'](folder / ('lucky-payload-' + stamp + '.private.json'), payload)
client['request'](config, 'PUT', path, payload)
client['audit']('PUT', path, 'ok-via-private-ssh-tunnel-video-' + args.target)
after = client['request'](config, 'GET', path)
client['secure_write'](folder / ('lucky-after-' + stamp + '.private.json'), after)
assert after['rule'] == {k: v for k, v in payload.items() if k != 'ExpectedVersion'}, 'Unexpected canonical configuration difference'
print(json.dumps({'backend_before': old_locations, 'backend_after': rule['Locations'],
    'unrelated_rule_configuration_preserved': True, 'version': after['version']}))
