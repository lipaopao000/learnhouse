"""Remove only a synthetic import fixture, without native deletion emails."""
import argparse
import base64
from pathlib import Path
import sys

parser=argparse.ArgumentParser()
parser.add_argument('--deployment-dir',required=True,type=Path)
parser.add_argument('--user-id',required=True,type=int)
parser.add_argument('--email',required=True)
args=parser.parse_args()
import re
assert re.fullmatch(r'lh-import-test-[0-9a-f]{16}@toofun\.fun',args.email)
assert args.user_id>3
sys.path.insert(0,str(args.deployment_dir.resolve()))
from remote import bash
program='''
import os,psycopg2
from src.core.redis import get_redis_client
uid=USER_ID
email=TEST_EMAIL
dsn=os.environ['LEARNHOUSE_SQL_CONNECTION_STRING'].replace('postgresql+psycopg2://','postgresql://').replace('postgresql+asyncpg://','postgresql://')
with psycopg2.connect(dsn) as db:
 with db.cursor() as cursor:
  cursor.execute('SELECT email,signup_method,is_superadmin,extra_metadata FROM "user" WHERE id=%s FOR UPDATE',(uid,))
  row=cursor.fetchone()
  if row is not None:
   assert row[0]==email and row[1]=='admin_import' and not row[2] and (row[3] or {}).get('admin_import'), 'Not an eligible test fixture'
   cursor.execute('DELETE FROM "user" WHERE id=%s AND email=%s',(uid,email))
   assert cursor.rowcount==1
redis=get_redis_client()
if redis:redis.delete('session:'+str(uid))
print('Synthetic account removed without email notifications')
'''.replace('USER_ID',str(args.user_id)).replace('TEST_EMAIL',repr(args.email))
encoded=base64.b64encode(program.encode()).decode()
print(bash('set -e\ndocker exec -w /app/api learnhouse-app /app/api/.venv/bin/python -c "import base64; exec(base64.b64decode(\''+encoded+'\'))"\n'))
