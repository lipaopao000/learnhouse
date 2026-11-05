"""Publish only public account UI assets, with a server-side rollback archive."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import subprocess
import sys
import tarfile

parser=argparse.ArgumentParser();parser.add_argument('--deployment-dir',type=Path,required=True)
root=parser.parse_args().deployment_dir.resolve();sys.path.insert(0,str(root));from remote import bash
web=Path(__file__).resolve().parents[1]/'admin-handover/web'
archive=root/'handover/username-ui.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
    for source in sorted(web.iterdir()):
        assert source.is_file() and source.suffix in {'.css','.js','.html'},'Unexpected public asset'
        tar.add(source,arcname=source.name)
subprocess.run(['scp',str(archive),'server-ba-tail:D:/deploy/LearnHouseUsername/ui.tar.gz'],check=True)
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
print(bash('set -e\ntar -czf /mnt/d/deploy/LearnHouse/backups/username-ui-'+stamp+'.tar.gz -C /mnt/d/deploy/LearnHouse/admin-tools-ui .\ntar -xzf /mnt/d/deploy/LearnHouseUsername/ui.tar.gz -C /mnt/d/deploy/LearnHouse/admin-tools-ui\necho "Account UI published; existing UI archived for rollback"\n'))
