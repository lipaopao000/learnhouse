import json
import pathlib
import sys
from datetime import datetime, timezone

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--deployment-dir', required=True, type=pathlib.Path)
ROOT = parser.parse_args().deployment_dir.resolve()
sys.path.insert(0, str(ROOT))
from portainer import request

DIR = ROOT / 'email-verification'

def save(path, value):
    path.write_text(value)
    path.chmod(0o600)

stack = request('/api/stacks/17')
original = request('/api/stacks/17/file')['StackFileContent']
assert stack['Status'] == 1
save(DIR / 'stack-before.private.json', json.dumps(stack, ensure_ascii=False, indent=2))
save(DIR / 'compose-before.private.json', json.dumps({'StackFileContent': original}, ensure_ascii=False, indent=2))
compose = json.loads(original)
assert compose['services']['app']['image'] == 'ghcr.io/learnhouse/app:latest'
compose['services']['app']['image'] = 'local/learnhouse:20261105-email-verification-v1'
settings = {
    'LEARNHOUSE_REQUIRE_EMAIL_VERIFICATION': 'true',
    'LEARNHOUSE_EMAIL_VERIFICATION_REQUIRED_SINCE': datetime.now(timezone.utc).isoformat(),
}
env = {item['name']: item['value'] for item in stack['Env']}
env.update(settings)
for key in settings:
    compose['services']['app']['environment'][key] = '${' + key + '}'
content = json.dumps(compose, ensure_ascii=False, indent=2)
payload = {'StackFileContent': content, 'Env': [{'name': key, 'value': str(value)} for key, value in env.items()], 'Prune': False, 'PullImage': False}
save(DIR / 'update-payload.private.json', json.dumps(payload, ensure_ascii=False, indent=2))
result = request('/api/stacks/17?endpointId=1', payload, method='PUT', timeout=240)
save(DIR / 'stack-after.private.json', json.dumps(result, ensure_ascii=False, indent=2))
for name in ['compose.yaml', 'env.private.json', 'stack.env']:
    save(DIR / (name + '.before.private'), (ROOT / 'config' / name).read_text())
save(ROOT / 'config/compose.yaml', content)
save(ROOT / 'config/env.private.json', json.dumps(env, ensure_ascii=False, indent=2))
save(ROOT / 'config/stack.env', ''.join(key + '=' + str(value) + '\n' for key, value in env.items()))
print(json.dumps({'stack': result['Name'], 'status': result['Status'], 'image': compose['services']['app']['image'], **settings}, ensure_ascii=False))
