"""Deploy the opt-in CSV tool through the existing Portainer Stack 17."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tarfile

HERE=Path(__file__).resolve().parent
TAG='local/learnhouse:20261105-admin-import-v3'
STATIC_LOCATIONS='''
 location = /dash/users/import {
  alias /srv/admin-tools/user-import.html;
  default_type text/html;
  add_header Cache-Control "no-store" always;
  add_header X-Content-Type-Options nosniff always;
  add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" always;
 }
 location ^~ /handover/assets/ {
  alias /srv/admin-tools/;
  add_header Cache-Control "no-store" always;
  add_header X-Content-Type-Options nosniff always;
 }
'''


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--deployment-dir',required=True,type=Path)
    root=parser.parse_args().deployment_dir.resolve()
    sys.path.insert(0,str(root))
    from portainer import request
    from remote import bash
    release=root/'handover/releases/20261105-admin-import-v3'
    release.mkdir(parents=True,exist_ok=True,mode=0o700)
    def save(path,value):path.write_text(value);path.chmod(0o600)
    stack=request('/api/stacks/17')
    content=request('/api/stacks/17/file')['StackFileContent']
    assert not (release/'stack-before.private.json').exists(), 'Release already submitted; use rollback or inspect snapshots before rerunning'
    compose=json.loads(content)
    assert compose['services']['app']['image']=='local/learnhouse:20261105-email-verification-v2'
    save(release/'stack-before.private.json',json.dumps(stack,ensure_ascii=False,indent=2))
    save(release/'compose-before.private.json',json.dumps({'StackFileContent':content}))
    for name in ['compose.yaml','env.private.json','stack.env','nginx.prod.conf']:
        save(release/(name+'.before.private'),(root/'config'/name).read_text())
    print(bash('set -e\nmkdir -p /mnt/d/deploy/LearnHouse/backups/admin-import-v3\ndocker exec learnhouse-db sh -c \'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"\' > /mnt/d/deploy/LearnHouse/backups/admin-import-v3/database.sql\ncp /mnt/d/deploy/LearnHouse/nginx.prod.conf /mnt/d/deploy/LearnHouse/backups/admin-import-v3/nginx.before.conf\ntest -s /mnt/d/deploy/LearnHouse/backups/admin-import-v3/database.sql\necho "Database and proxy snapshot ready"\n',timeout=120))
    conf=(root/'config/nginx.prod.conf').read_text()
    assert '/dash/users/import' not in conf
    conf=conf.replace(' location / {',STATIC_LOCATIONS+' location / {')
    save(release/'nginx.prod.conf',conf)
    archive=release/'admin-ui.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for name in ['user-import.html','user-import.js','user-import.css']:
            tar.add(HERE/'web'/name,arcname=name)
    subprocess.run(['scp',str(archive),'server-ba-tail:D:/deploy/LearnHouseAdminImport/admin-ui.tar.gz'],check=True)
    subprocess.run(['scp',str(release/'nginx.prod.conf'),'server-ba-tail:D:/deploy/LearnHouse/nginx.prod.conf'],check=True)
    print(bash('set -e\nmkdir -p /mnt/d/deploy/LearnHouse/admin-tools-ui\ntar -xzf /mnt/d/deploy/LearnHouseAdminImport/admin-ui.tar.gz -C /mnt/d/deploy/LearnHouse/admin-tools-ui\necho "Admin static files installed"\n'))
    compose['services']['app']['image']=TAG
    flag='LEARNHOUSE_ADMIN_USER_IMPORT_ENABLED'
    compose['services']['app']['environment'][flag]='${'+flag+'}'
    compose['services']['nginx']['volumes'].append('/mnt/d/deploy/LearnHouse/admin-tools-ui:/srv/admin-tools:ro')
    env={item['name']:item['value'] for item in stack['Env']};env[flag]='true'
    content=json.dumps(compose,ensure_ascii=False,indent=2)
    payload={'StackFileContent':content,'Env':[{'name':key,'value':str(value)} for key,value in env.items()],'Prune':False,'PullImage':False}
    save(release/'update-payload.private.json',json.dumps(payload,ensure_ascii=False))
    result=request('/api/stacks/17?endpointId=1',payload,method='PUT',timeout=240)
    save(release/'stack-after.private.json',json.dumps(result,ensure_ascii=False,indent=2))
    save(root/'config/compose.yaml',content)
    save(root/'config/env.private.json',json.dumps(env,ensure_ascii=False,indent=2))
    save(root/'config/stack.env',''.join(key+'='+str(value)+'\n' for key,value in env.items()))
    save(root/'config/nginx.prod.conf',conf)
    for name in ['compose.yaml','env.private.json','stack.env']:
        subprocess.run(['scp',str(root/'config'/name),'server-ba-tail:D:/deploy/LearnHouse/'+name],check=True)
    print(json.dumps({'stack':result['Name'],'status':result['Status'],'image':TAG,'url':'https://syyedu.toofun.fun/dash/users/import','time':datetime.now(timezone.utc).isoformat()}))


if __name__=='__main__':main()
