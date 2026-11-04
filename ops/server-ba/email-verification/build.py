"""Build the minimal API overlay against the exact deployed official image."""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = 'ghcr.io/learnhouse/app@sha256:9dd05e16fe1aecf5b668dc4d415c38bf1fd20274a927b50bc51a98388b3639bb'
TAG = 'local/learnhouse:20261105-email-verification-v2'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Check the extracted and patched files without building')
    args = parser.parse_args()
    manifest = json.loads((HERE / 'source-hashes.json').read_text())
    with tempfile.TemporaryDirectory(prefix='learnhouse-verification-') as directory:
        context = pathlib.Path(directory)
        container = run('docker', 'create', BASE, capture_output=True, text=True).stdout.strip()
        try:
            for relative, hashes in manifest.items():
                target = context / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if hashes.get('original'):
                    source = '/app/api/' + relative.removeprefix('apps/api/')
                    run('docker', 'cp', container + ':' + source, str(target), capture_output=True)
                    assert hashlib.sha256(target.read_bytes()).hexdigest() == hashes['original'], 'Official source changed: ' + relative
                else:
                    shutil.copy2(ROOT / relative, target)
        finally:
            run('docker', 'rm', container, capture_output=True)
        run('git', 'apply', '--check', str(HERE / 'runtime.patch'), cwd=context)
        run('git', 'apply', str(HERE / 'runtime.patch'), cwd=context)
        for relative, hashes in manifest.items():
            assert hashlib.sha256((context / relative).read_bytes()).hexdigest() == hashes['patched'], 'Patched source changed: ' + relative
        shutil.copy2(HERE / 'Dockerfile', context / 'Dockerfile')
        print('Official source and patched source hashes verified', flush=True)
        if not args.check:
            run('docker', 'build', '--pull=false', '-t', TAG, str(context))


if __name__ == '__main__':
    main()
