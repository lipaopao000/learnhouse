"""Run from a checkout on server-ba WSL. Preserve the deployed v2 mail fixes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
BASE='local/learnhouse:20261105-email-verification-v2'
TAG='local/learnhouse:20261105-admin-import-v3'


def run(*args, **kwargs):
    return subprocess.run(args,check=True,**kwargs)


def main():
    with tempfile.TemporaryDirectory(prefix='learnhouse-admin-import-') as directory:
        context=Path(directory)
        container=run('docker','create',BASE,capture_output=True,text=True).stdout.strip()
        try:
            run('docker','cp',container+':/app/api/src/router.py',str(context/'router.py'),capture_output=True)
        finally:
            run('docker','rm',container,capture_output=True)
        before=(context/'router.py').read_bytes()
        assert b'user_import_router' not in before
        with (context/'router.py').open('a') as handle:
            handle.write('\nfrom src.routers.orgs.user_import import router as user_import_router\nv1_router.include_router(user_import_router, prefix="/orgs", tags=["user-import"])\n')
        shutil.copy2(REPO/'apps/api/src/routers/orgs/user_import.py',context/'user_import.py')
        (context/'Dockerfile').write_text('FROM '+BASE+'\nCOPY router.py /app/api/src/router.py\nCOPY user_import.py /app/api/src/routers/orgs/user_import.py\n')
        run('docker','build','--pull=false','-t',TAG,str(context))
        print(json.dumps({'base':BASE,'image':TAG,'base_router_sha256':hashlib.sha256(before).hexdigest(),'import_sha256':hashlib.sha256((context/'user_import.py').read_bytes()).hexdigest()}))


if __name__=='__main__':main()
