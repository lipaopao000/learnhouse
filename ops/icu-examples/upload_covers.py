"""Attach reviewed course artwork through the native thumbnail API."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request
import urllib.error
from uuid import uuid4
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'admin-handover'));from client import Client
parser=argparse.ArgumentParser();parser.add_argument('--deployment-dir',type=Path,required=True)
parser.add_argument('--partial',action='store_true',help='Upload reviewed available files while other covers are still being prepared')
args=parser.parse_args();root=args.deployment_dir
state_file=root/'handover/icu-covers-state.json'
state=json.loads(state_file.read_text()) if state_file.exists() else {}
drafts=json.loads((root/'handover/seed-state.json').read_text())['courses']
examples=json.loads((root/'handover/icu-examples-state.json').read_text())
api=Client(root)
mapping=[('platform','平台使用与培训须知'),('handover','ICU入科与规范交接班'),('ventilation','气道管理与机械通气'),('circulation','休克与血流动力学'),('infection','感染与脓毒症'),('sedation','镇痛镇静、谵妄与早期康复'),('renal','AKI、CRRT与内环境'),('nutrition','营养与常见系统问题'),('resuscitation','抢救技能与护理配合'),('cases','病例讨论与教学考核'),('admin','管理员工作台与交接手册'),('examples',examples['course']['name'])]
def save():
    temp=state_file.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(state_file)
for key,title in mapping:
    filename=HERE/'covers'/f'{key}.webp'
    if args.partial and not filename.is_file():continue
    assert filename.is_file(),filename
    course=examples['course'] if key=='examples' else drafts[title]['course']
    uuid=course['course_uuid']
    digest=hashlib.sha256(filename.read_bytes()).hexdigest()
    if key in state:
        assert state[key]['asset_sha256']==digest,'Asset changed after upload; review explicitly'
        continue
    current=api.request('/api/v1/courses/'+uuid+'/meta?with_unpublished_activities=true')
    boundary='LHCover'+uuid4().hex
    data=(f'--{boundary}\r\nContent-Disposition: form-data; name="thumbnail_type"\r\n\r\nimage\r\n--{boundary}\r\nContent-Disposition: form-data; name="thumbnail"; filename="{key}.webp"\r\nContent-Type: image/webp\r\n\r\n'.encode()+filename.read_bytes()+f'\r\n--{boundary}--\r\n'.encode())
    req=urllib.request.Request(api.base+'/api/v1/courses/'+uuid+'/thumbnail',data=data,headers={'Origin':api.base,'Authorization':'Bearer '+api.token,'Content-Type':'multipart/form-data; boundary='+boundary},method='PUT')
    try:
        with urllib.request.urlopen(req,timeout=90) as r: updated=json.load(r)
    except urllib.error.HTTPError as error:
        raise RuntimeError("Thumbnail upload " + str(error.code) + ": " + error.read().decode()[:450]) from None
    assert updated['published']==current['published'] and updated['public']==current['public']
    assert updated['thumbnail_image']
    state[key]={'course_uuid':uuid,'title':title,'before_thumbnail':current.get('thumbnail_image'),'thumbnail_image':updated['thumbnail_image'],'published':updated['published'],'public':updated['public'],'asset_sha256':digest,'asset_file':str(filename.relative_to(HERE))};save()
    print('Uploaded cover:',title,flush=True)
report_path=HERE/'verification.json';report=json.loads(report_path.read_text())
report['course_covers']={'count':len(state),'all_publication_states_preserved':True,'assets':list(state.values())}
report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('Native course covers attached:',len(state))
