"""Restore the previous image, environment and proxy config (keeps user data)."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

parser=argparse.ArgumentParser();parser.add_argument('--deployment-dir',type=Path,required=True)
root=parser.parse_args().deployment_dir.resolve();sys.path.insert(0,str(root))
from portainer import request
release=root/'handover/releases/20261105-admin-import-v3'
stack=json.loads((release/'stack-before.private.json').read_text())
content=json.loads((release/'compose-before.private.json').read_text())['StackFileContent']
for name in ['compose.yaml','env.private.json','stack.env','nginx.prod.conf']:
    target=root/'config'/name;target.write_text((release/(name+'.before.private')).read_text());target.chmod(0o600)
    subprocess.run(['scp',str(target),'server-ba-tail:D:/deploy/LearnHouse/'+name],check=True)
result=request('/api/stacks/17?endpointId=1',{'StackFileContent':content,'Env':stack['Env'],'Prune':False,'PullImage':False},method='PUT',timeout=240)
print({'stack':result['Name'],'status':result['Status'],'data_preserved':True})
