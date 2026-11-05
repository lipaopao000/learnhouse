"""Build the username overlay against the exact deployed v3 source hashes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from patch_runtime import FILES,patch

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
BASE='local/learnhouse:20261105-admin-import-v3'
TAG='local/learnhouse:20261105-username-accounts-v4'
EXTRA=['src/security/account_identity.py','src/routers/account_access.py','src/routers/orgs/user_import.py']


def run(*args,**kwargs):return subprocess.run(args,check=True,**kwargs)


def main():
    hashes=json.loads((HERE/'runtime-hashes.json').read_text())
    with tempfile.TemporaryDirectory(prefix='learnhouse-username-') as directory:
        context=Path(directory)
        container=run('docker','create',BASE,capture_output=True,text=True).stdout.strip()
        try:
            for relative in FILES:
                target=context/relative;target.parent.mkdir(parents=True,exist_ok=True)
                run('docker','cp',container+':/app/api/'+relative,str(target),capture_output=True)
                assert hashlib.sha256(target.read_bytes()).hexdigest()==hashes[relative]['original'],relative+' base changed'
                target.write_text(patch(relative,target.read_text()))
                assert hashlib.sha256(target.read_bytes()).hexdigest()==hashes[relative]['patched'],relative+' patch changed'
        finally:run('docker','rm',container,capture_output=True)
        for relative in EXTRA:
            target=context/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(REPO/'apps/api'/relative,target)
        (context/'Dockerfile').write_text('FROM '+BASE+'\n'+''.join('COPY '+r+' /app/api/'+r+'\n' for r in FILES+EXTRA))
        run('docker','build','--pull=false','-t',TAG,str(context))
        print(json.dumps({'image':TAG,'base':BASE,'runtime_files_verified':len(FILES)}))


if __name__=='__main__':main()
