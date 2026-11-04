"""Restore the previous LearnHouse image and verification policy via Portainer."""
import json
import pathlib
import sys

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--deployment-dir', required=True, type=pathlib.Path)
ROOT = parser.parse_args().deployment_dir.resolve()
sys.path.insert(0, str(ROOT))
from portainer import request

HERE = ROOT / 'email-verification/releases/20261105-email-verification-v2'
stack = json.loads((HERE / 'stack-before.private.json').read_text())
compose = json.loads((HERE / 'compose-before.private.json').read_text())['StackFileContent']
payload = {'StackFileContent': compose, 'Env': stack['Env'], 'Prune': False, 'PullImage': False}
result = request('/api/stacks/17?endpointId=1', payload, method='PUT', timeout=240)
for name in ['compose.yaml', 'env.private.json', 'stack.env']:
    destination = ROOT / 'config' / name
    destination.write_text((HERE / (name + '.before.private')).read_text())
    destination.chmod(0o600)
print({'stack': result['Name'], 'status': result['Status'], 'rollback_submitted': True})
