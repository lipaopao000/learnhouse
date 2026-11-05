"""Redeploy an already configured v4 Stack after a verified overlay rebuild."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone

parser=argparse.ArgumentParser();parser.add_argument('--deployment-dir',type=Path,required=True)
root=parser.parse_args().deployment_dir.resolve();sys.path.insert(0,str(root))
from portainer import request
stack=request('/api/stacks/17');original=request('/api/stacks/17/file')['StackFileContent'];compose=json.loads(original)
assert compose['services']['app']['image']=='local/learnhouse:20261105-username-accounts-v4'
revision=hashlib.sha256((Path(__file__).parent/'runtime-hashes.json').read_bytes()).hexdigest()[:16]
compose['services']['app'].setdefault('labels',{})['learnhouse.username-accounts-source']=revision
release=root/'handover/releases/20261105-username-accounts-v4'
snapshot=release/('rebuild-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.private.json')
snapshot.write_text(json.dumps({'stack':stack,'compose':original},ensure_ascii=False));snapshot.chmod(0o600)
content=json.dumps(compose,ensure_ascii=False,indent=2)
result=request('/api/stacks/17?endpointId=1',{'StackFileContent':content,'Env':stack['Env'],'Prune':False,'PullImage':False},method='PUT',timeout=240)
p=root/'config/compose.yaml';p.write_text(content);p.chmod(0o600)
subprocess.run(['scp',str(p),'server-ba-tail:D:/deploy/LearnHouse/compose.yaml'],check=True)
print({'status':result['Status'],'source_revision':revision})
