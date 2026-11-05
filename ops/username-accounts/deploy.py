"""Update only LearnHouse Stack 17; keep source caches and analytics untouched."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
TAG='local/learnhouse:20261105-username-accounts-v4'
LOCATIONS='''
 location = /login { alias /srv/admin-tools/login.html; default_type text/html; include /etc/nginx/conf.d/account-headers.inc; }
 location = /auth/login { alias /srv/admin-tools/login.html; default_type text/html; include /etc/nginx/conf.d/account-headers.inc; }
 location = /account { alias /srv/admin-tools/account.html; default_type text/html; include /etc/nginx/conf.d/account-headers.inc; }
 location = /account/general { alias /srv/admin-tools/account.html; default_type text/html; include /etc/nginx/conf.d/account-headers.inc; }
 location = /email-login {
  proxy_pass http://app:80/login;
  proxy_set_header Host $http_host;
  proxy_set_header X-Forwarded-Host $http_host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $remote_addr;
  proxy_set_header X-Forwarded-Proto https;
 }
 location = /account/details {
  proxy_pass http://app:80/account/general;
  proxy_set_header Host $http_host;
  proxy_set_header X-Forwarded-Host $http_host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $remote_addr;
  proxy_set_header X-Forwarded-Proto https;
 }
'''
HEADERS='''add_header Cache-Control "no-store" always;
add_header X-Content-Type-Options nosniff always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" always;
'''


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--deployment-dir',type=Path,required=True)
    root=parser.parse_args().deployment_dir.resolve();sys.path.insert(0,str(root))
    from remote import bash
    from portainer import request
    release=root/'handover/releases/20261105-username-accounts-v4';release.mkdir(parents=True,exist_ok=True,mode=0o700)
    def save(path,value):path.write_text(value);path.chmod(0o600)
    stack=request('/api/stacks/17');original=request('/api/stacks/17/file')['StackFileContent']
    assert stack['Status']==1
    assert not (release/'stack-before.private.json').exists(),'Release snapshot already exists; inspect before retrying'
    compose=json.loads(original)
    assert compose['services']['app']['image']=='local/learnhouse:20261105-admin-import-v3'
    save(release/'stack-before.private.json',json.dumps(stack,ensure_ascii=False,indent=2))
    save(release/'compose-before.private.json',json.dumps({'StackFileContent':original}))
    for name in ['compose.yaml','env.private.json','stack.env','nginx.prod.conf']:
        save(release/(name+'.before.private'),(root/'config'/name).read_text())
    # Indexes enforce the uniqueness already expected by native signup; multiple
    # truly empty emails remain legal. This fails before deploy on legacy duplicates.
    print(bash('''set -e
mkdir -p /mnt/d/deploy/LearnHouse/backups/username-accounts-v4
docker exec learnhouse-db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > /mnt/d/deploy/LearnHouse/backups/username-accounts-v4/database.sql
test -s /mnt/d/deploy/LearnHouse/backups/username-accounts-v4/database.sql
cp /mnt/d/deploy/LearnHouse/nginx.prod.conf /mnt/d/deploy/LearnHouse/backups/username-accounts-v4/nginx.before.conf
tar -czf /mnt/d/deploy/LearnHouse/backups/username-accounts-v4/admin-ui.before.tar.gz -C /mnt/d/deploy/LearnHouse/admin-tools-ui .
docker exec -i learnhouse-db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"' <<'SQL'
BEGIN;
CREATE UNIQUE INDEX IF NOT EXISTS lh_selfhost_user_email_ci ON "user" (lower(email)) WHERE email <> '';
CREATE UNIQUE INDEX IF NOT EXISTS lh_selfhost_user_username ON "user" (username) WHERE username <> '';
COMMIT;
SQL
echo 'Database, proxy and UI snapshot ready; identity indexes installed'
''',timeout=120))
    conf=(root/'config/nginx.prod.conf').read_text();assert 'location = /login' not in conf
    # Inline the shared headers so no extra nginx mount is needed.
    conf=conf.replace(' location / {',LOCATIONS.replace('include /etc/nginx/conf.d/account-headers.inc;',HEADERS)+' location / {')
    save(release/'nginx.prod.conf',conf)
    subprocess.run(['scp',str(release/'nginx.prod.conf'),'server-ba-tail:D:/deploy/LearnHouseUsername/nginx.v4.conf'],check=True)
    print(bash('''set -e
network=$(docker inspect learnhouse-nginx --format '{{range $name,$value := .NetworkSettings.Networks}}{{$name}}{{end}}')
docker run --rm --network "$network" -v /mnt/d/deploy/LearnHouseUsername/nginx.v4.conf:/etc/nginx/conf.d/default.conf:ro -v /mnt/d/deploy/LearnHouseUsername/ops/admin-handover/web:/srv/admin-tools:ro nginx:1.30-alpine nginx -t
cp /mnt/d/deploy/LearnHouseUsername/nginx.v4.conf /mnt/d/deploy/LearnHouse/nginx.prod.conf
cp /mnt/d/deploy/LearnHouseUsername/ops/admin-handover/web/* /mnt/d/deploy/LearnHouse/admin-tools-ui/
echo 'Proxy config verified and new account pages installed'
'''))
    compose['services']['app']['image']=TAG
    env={item['name']:item['value'] for item in stack['Env']}
    env['LEARNHOUSE_USERNAME_ACCOUNTS_ENABLED']='true'
    compose['services']['app']['environment']['LEARNHOUSE_USERNAME_ACCOUNTS_ENABLED']='${LEARNHOUSE_USERNAME_ACCOUNTS_ENABLED}'
    # Recreate nginx to load the changed bind-file configuration through Portainer.
    compose['services']['nginx'].setdefault('labels',{})['learnhouse.account-pages']='v4'
    content=json.dumps(compose,ensure_ascii=False,indent=2)
    payload={'StackFileContent':content,'Env':[{'name':k,'value':str(v)} for k,v in env.items()],'Prune':False,'PullImage':False}
    save(release/'update-payload.private.json',json.dumps(payload,ensure_ascii=False))
    result=request('/api/stacks/17?endpointId=1',payload,method='PUT',timeout=240)
    save(release/'stack-after.private.json',json.dumps(result,ensure_ascii=False,indent=2))
    save(root/'config/compose.yaml',content);save(root/'config/env.private.json',json.dumps(env,ensure_ascii=False,indent=2))
    save(root/'config/stack.env',''.join(k+'='+str(v)+'\n' for k,v in env.items()));save(root/'config/nginx.prod.conf',conf)
    for name in ['compose.yaml','env.private.json','stack.env']:
        subprocess.run(['scp',str(root/'config'/name),'server-ba-tail:D:/deploy/LearnHouse/'+name],check=True)
    print(json.dumps({'stack':result['Name'],'status':result['Status'],'image':TAG,'username_accounts':True}))


if __name__=='__main__':main()
