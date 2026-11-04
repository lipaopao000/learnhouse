"""Render deployment files without placing the origin key in Git or stdout."""
import argparse
import json
import pathlib
import secrets

parser = argparse.ArgumentParser()
parser.add_argument('--deployment-dir', required=True, type=pathlib.Path)
parser.add_argument('--origin-ip', default='100.64.0.4', choices=['100.64.0.4', '100.64.0.8'])
args = parser.parse_args()
target = args.deployment_dir.resolve() / 'video-distribution'
target.mkdir(mode=0o700, parents=True, exist_ok=True)
private = target / 'origin-key.private.json'
if private.exists():
    key = json.loads(private.read_text())['key']
else:
    key = secrets.token_hex(32)
    private.write_text(json.dumps({'key': key}))
private.chmod(0o600)
for source, output in [
    ('origin.nginx.conf.template', 'origin.nginx.private.conf'),
    ('edge.nginx.conf.template', 'edge.nginx.private.conf'),
    ('install-origin.ps1', 'install-origin.ps1'),
    ('prefetch.ps1', 'prefetch.ps1'),
    ('install-prefetch.ps1', 'install-prefetch.ps1'),
]:
    content = (pathlib.Path(__file__).parent / source).read_text()
    content = content.replace('__ORIGIN_IP__', args.origin_ip).replace('__ORIGIN_KEY__', key)
    path = target / output
    path.write_text(content)
    path.chmod(0o600)
prefetch = target / 'prefetch.private.json'
prefetch.write_text(json.dumps({'read_key': key, 'origin_base': 'http://' + args.origin_ip + ':18887',
    'export_base': 'http://100.64.0.6:8806/__learnhouse_export'}, indent=2))
prefetch.chmod(0o600)
print(json.dumps({'origin': args.origin_ip, 'output': str(target)}))
