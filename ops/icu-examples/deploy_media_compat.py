"""Deploy the already-built media fix using Portainer Stack 17, with snapshot."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
from media_compat import BASE,TAG
parser=argparse.ArgumentParser();parser.add_argument('--deployment-dir',type=Path,required=True)
root=parser.parse_args().deployment_dir.resolve();sys.path.insert(0,str(root))
from portainer import request
stack=request('/api/stacks/17');original=request('/api/stacks/17/file')['StackFileContent']
compose=json.loads(original);assert compose['services']['app']['image']==BASE
release=root/'handover/releases/20261105-icu-examples-v5';release.mkdir(parents=True,mode=0o700,exist_ok=True)
snapshot=release/('before-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.private.json')
snapshot.write_text(json.dumps({'stack':stack,'compose':original},ensure_ascii=False));snapshot.chmod(0o600)
compose['services']['app']['image']=TAG
content=json.dumps(compose,ensure_ascii=False,indent=2)
result=request('/api/stacks/17?endpointId=1',{'StackFileContent':content,'Env':stack['Env'],'Prune':False,'PullImage':False},method='PUT',timeout=240)
p=root/'config/compose.yaml';p.write_text(content);p.chmod(0o600)
subprocess.run(['scp',str(p),'server-ba-tail:D:/deploy/LearnHouse/compose.yaml'],check=True)
print(json.dumps({'image':TAG,'stack_status':result['Status'],'snapshot':snapshot.name}))
