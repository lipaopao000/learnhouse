"""Build a one-class overlay for the deployed Starlette compression protocol.

Run on server-ba's WSL host. Uses the same fixed responder already present in
the tracked upstream app.py, without replacing unrelated deployed app changes.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

BASE='local/learnhouse:20261105-username-accounts-v4'
TAG='local/learnhouse:20261105-icu-examples-v5'
FIX='''class _SelectiveGZipResponder(GZipResponder):
    """Choose Starlette's pass-through path before it handles response.start."""

    async def send_with_compression(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            content_type = Headers(raw=message["headers"]).get("content-type", "")
            if not _is_compressible(content_type):
                media_type = content_type.partition(";")[0].strip().lower()
                self.exclude_content_types = (*self.exclude_content_types, media_type)
        await super().send_with_compression(message)
'''
def run(*args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def main():
    with tempfile.TemporaryDirectory(prefix='lh-media-compat-') as directory:
        context=Path(directory);container=run('docker','create',BASE,capture_output=True,text=True).stdout.strip()
        try:run('docker','cp',container+':/app/api/app.py',str(context/'app.py'),capture_output=True)
        finally:run('docker','rm',container,capture_output=True)
        original=(context/'app.py').read_text();tree=ast.parse(original)
        target=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='_SelectiveGZipResponder')
        old=ast.get_source_segment(original,target)
        assert 'self.content_type_is_excluded = not _is_compressible' in old,'Unexpected base responder'
        patched=original.replace(old,FIX.rstrip(),1);compile(patched,'app.py','exec')
        (context/'app.py').write_text(patched)
        (context/'Dockerfile').write_text('FROM '+BASE+'\nCOPY app.py /app/api/app.py\n')
        run('docker','build','--pull=false','-t',TAG,str(context))
        print(json.dumps({'image':TAG,'base':BASE,'file':'app.py','before_sha256':hashlib.sha256(original.encode()).hexdigest(),'after_sha256':hashlib.sha256(patched.encode()).hexdigest()}))
if __name__=='__main__':main()
