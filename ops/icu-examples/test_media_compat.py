"""Exercise the actual packaged Starlette and extracted middleware classes."""
import ast
import tempfile
from pathlib import Path
from fastapi import FastAPI
from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipMiddleware,GZipResponder,IdentityResponder
from starlette.responses import FileResponse,JSONResponse,RedirectResponse,Response,StreamingResponse
from starlette.testclient import TestClient
from starlette.types import ASGIApp,Message,Scope,Receive,Send

source=Path('/app/api/app.py').read_text()
tree=ast.parse(source)
names={'_COMPRESSIBLE_PREFIXES','_is_compressible','_SelectiveGZipResponder','SelectiveGZipMiddleware'}
nodes=[n for n in tree.body if getattr(n,'name',None) in names or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in n.targets)]
exec(compile(ast.Module(body=nodes,type_ignores=[]),'<deployed-gzip>','exec'),globals())
app=FastAPI();app.add_middleware(SelectiveGZipMiddleware,minimum_size=10)
payload=b'%PDF-1.7\n'+b'x'*4096
with tempfile.TemporaryDirectory() as directory:
    pdf=Path(directory)/'example.pdf';pdf.write_bytes(payload)
    @app.get('/pdf')
    def file():return FileResponse(pdf,media_type='application/pdf')
    @app.head('/pdf')
    def head():return Response(headers={'Content-Type':'application/pdf','Content-Length':str(len(payload))})
    @app.get('/stream')
    def stream():return StreamingResponse(iter([payload[:100],payload[100:]]),media_type='application/octet-stream')
    @app.get('/redirect')
    def redirect():return RedirectResponse('/pdf')
    @app.get('/json')
    def json():return JSONResponse({'text':'a'*4096})
    checks=0
    with TestClient(app) as client:
        for encoding in ['gzip','identity']:
            headers={'Accept-Encoding':encoding}
            for route in ['/pdf','/stream']:
                r=client.get(route,headers=headers);assert r.status_code==200 and r.content==payload;assert 'content-encoding' not in r.headers;checks+=1
            r=client.get('/pdf',headers={**headers,'Range':'bytes=0-31'});assert r.status_code==206 and r.content==payload[:32];checks+=1
            r=client.head('/pdf',headers=headers);assert r.status_code==200 and not r.content;checks+=1
            r=client.get('/redirect',headers=headers,follow_redirects=False);assert r.status_code==307;checks+=1
            r=client.get('/json',headers=headers);assert r.json()['text']=='a'*4096;assert (r.headers.get('content-encoding')=='gzip')==(encoding=='gzip');checks+=1
    print({'compression_protocol_checks':checks,'result':'passed'})
