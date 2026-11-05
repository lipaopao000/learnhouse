"""Download only the catalog's officially offered files; no authenticated scraping."""
import argparse, concurrent.futures, hashlib, json, re
from pathlib import Path
import requests
from catalog import COURSES

def download(url, target, params=None):
    if target.exists(): return
    partial=target.with_suffix(target.suffix+'.partial')
    with requests.get(url,params=params,stream=True,timeout=(30,120)) as response:
        response.raise_for_status()
        expected=int(response.headers.get('Content-Length',0))
        with partial.open('wb') as output:
            for block in response.iter_content(1024*1024): output.write(block)
        if expected and partial.stat().st_size != expected: raise RuntimeError('Truncated download: '+target.name)
    partial.replace(target)
    print('Downloaded',target.name,target.stat().st_size,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work-dir',type=Path,required=True);args=p.parse_args()
    dest=args.work_dir/'downloads';dest.mkdir(parents=True,exist_ok=True)
    jobs=[]
    # Media Hopper offers downloads with the public anonymous player session.
    # Read it from the public page; never use a privileged Kaltura credential.
    playlist='https://media.ed.ac.uk/playlist/dedicated/76589901/1_wmyhhzcj/1_yzb092fm'
    response=requests.get(playlist,timeout=60);response.raise_for_status()
    props=json.loads(re.search(r'var lobbyProps = (.*);',response.text)[1])['props']
    anonymous_ks=props['playerConfig']['provider']['ks']
    for course in COURSES:
        for lesson in course['lessons']:
            if 'parts' in lesson:
                for n,file_id in enumerate(lesson['parts'],1):
                    jobs.append(('https://www.cdc.gov.tw/File/Get/'+file_id,dest/f"{lesson['key']}.part{n}.rar",None))
            elif 'file' in lesson:
                jobs.append(('https://www.cdc.gov.tw/File/Get/'+lesson['file'],dest/(lesson['key']+'.mp4'),None))
            else:
                jobs.append((f"https://cdnapisec.kaltura.com/p/2010292/sp/201029200/playManifest/entryId/{lesson['entry']}/format/download/protocol/https/flavorParamIds/0",dest/(lesson['key']+'.mp4'),{'ks':anonymous_ks}))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda pair:download(*pair),jobs))
    manifest=[]
    for url,path,_ in jobs:
        with path.open('rb') as file: digest=hashlib.file_digest(file,'sha256').hexdigest()
        manifest.append(dict(file=path.name,url=url,bytes=path.stat().st_size,sha256=digest))
    (args.work_dir/'download-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
