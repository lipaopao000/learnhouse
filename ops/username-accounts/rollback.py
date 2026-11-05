"""Restore v3 image/env/pages; keep account data and compatible identity indexes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

parser=argparse.ArgumentParser();parser.add_argument('--deployment-dir',type=Path,required=True)
root=parser.parse_args().deployment_dir.resolve();sys.path.insert(0,str(root))
from portainer import request
from remote import bash
release=root/'handover/releases/20261105-username-accounts-v4'
stack=json.loads((release/'stack-before.private.json').read_text())
content=json.loads((release/'compose-before.private.json').read_text())['StackFileContent']
for name in ['compose.yaml','env.private.json','stack.env','nginx.prod.conf']:
    target=root/'config'/name;target.write_text((release/(name+'.before.private')).read_text());target.chmod(0o600)
    subprocess.run(['scp',str(target),'server-ba-tail:D:/deploy/LearnHouse/'+name],check=True)
print(bash('set -e\ntar -xzf /mnt/d/deploy/LearnHouse/backups/username-accounts-v4/admin-ui.before.tar.gz -C /mnt/d/deploy/LearnHouse/admin-tools-ui\n'))
result=request('/api/stacks/17?endpointId=1',{'StackFileContent':content,'Env':stack['Env'],'Prune':False,'PullImage':False},method='PUT',timeout=240)
print({'status':result['Status'],'warning':'v3 cannot sign in the newly created username-only accounts; restore v4 to re-enable them. No account data is deleted.'})
