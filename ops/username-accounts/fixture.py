"""Private test-fixture operations, strictly restricted to synthetic imports."""
import argparse
from pathlib import Path
import re
import sys
import subprocess
import tempfile
from uuid import uuid4

parser=argparse.ArgumentParser();parser.add_argument('--deployment-dir',type=Path,required=True)
parser.add_argument('--user-id',type=int,required=True);parser.add_argument('--username',required=True)
parser.add_argument('--action',choices=['cleanup','prepare-mail'],required=True)
parser.add_argument('--target-email',default='');parser.add_argument('--code',default='')
args=parser.parse_args()
assert args.user_id>3 and re.fullmatch(r'lh_test_[a-f0-9]{16}',args.username)
if args.action=='prepare-mail':
    assert re.fullmatch(r'lh-import-test-[a-f0-9]{16}@toofun\.fun',args.target_email)
    assert re.fullmatch(r'\d{6}',args.code)
sys.path.insert(0,str(args.deployment_dir.resolve()));from remote import bash
program='''
import os,json,hashlib,secrets,psycopg2,re,shutil
from pathlib import Path
from src.core.redis import get_redis_client
uid=USER_ID
username=TEST_USERNAME
action=TEST_ACTION
target=TEST_EMAIL
code=TEST_CODE
dsn=os.environ['LEARNHOUSE_SQL_CONNECTION_STRING'].replace('postgresql+psycopg2://','postgresql://').replace('postgresql+asyncpg://','postgresql://')
r=get_redis_client()
with psycopg2.connect(dsn) as db:
 with db.cursor() as cursor:
  cursor.execute('SELECT username,email,signup_method,is_superadmin,extra_metadata,password_changed_at,user_uuid FROM "user" WHERE id=%s FOR UPDATE',(uid,))
  row=cursor.fetchone()
  if row is None:
   assert action=='cleanup'
  else:
   assert row[0]==username and row[2]=='admin_import' and not row[3] and (row[4] or {}).get('admin_import')
   assert not row[1] or re.fullmatch(r'lh-import-test-[a-f0-9]{16}@toofun\\.fun',row[1])
   if action=='cleanup':
    cursor.execute('DELETE FROM "user" WHERE id=%s AND username=%s',(uid,username));assert cursor.rowcount==1
   else:
    salt=secrets.token_hex(16)
    payload={'email':target,'salt':salt,'digest':hashlib.sha256((salt+code).encode()).hexdigest(),'credential_epoch':str(row[5])}
    r.setex('account_email_pending:'+str(uid),600,json.dumps(payload))
if action=='cleanup' and row is not None:
 assert re.fullmatch(r'user_[0-9a-f-]{36}',row[6])
 shutil.rmtree(Path('/app/api/content/users')/row[6],ignore_errors=True)
if action=='cleanup' and r:r.delete('session:'+str(uid),'account_email_pending:'+str(uid),'jwt_revoked_before:'+str(uid))
print('Synthetic fixture operation complete; no mail sent')
'''.replace('USER_ID',str(args.user_id)).replace('TEST_USERNAME',repr(args.username)).replace('TEST_ACTION',repr(args.action)).replace('TEST_EMAIL',repr(args.target_email)).replace('TEST_CODE',repr(args.code))
remote_name='fixture-op-'+uuid4().hex+'.py'
with tempfile.NamedTemporaryFile(mode='w',suffix='.py',dir=args.deployment_dir/'handover') as handle:
    handle.write(program);handle.flush()
    subprocess.run(['scp',handle.name,'server-ba-tail:D:/deploy/LearnHouseUsername/'+remote_name],check=True)
    remote_path='/mnt/d/deploy/LearnHouseUsername/'+remote_name
    print(bash("set -e\ntrap 'rm -f "+remote_path+"' EXIT\ndocker exec -i -w /app/api learnhouse-app /app/api/.venv/bin/python - < "+remote_path+'\n'))
