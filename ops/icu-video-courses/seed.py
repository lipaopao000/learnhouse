"""Create a checkpointed, member-only video library through native LearnHouse APIs.

No source code, old course, account, network route or cache policy is changed.
POST is deliberately not retried: reconcile server state after uncertain failures.
"""
import argparse, http.client, json, mimetypes, sys, urllib.parse
from pathlib import Path
from uuid import uuid4
from catalog import COURSES, NOTICE

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'admin-handover'))
from client import Client

def document(title, sections, links):
    def p(text):return {'type':'paragraph','content':[{'type':'text','text':text}]}
    content=[{'type':'heading','attrs':{'level':1},'content':[{'type':'text','text':title}]},p(NOTICE)]
    for heading, paragraphs in sections:
        content.append({'type':'heading','attrs':{'level':2},'content':[{'type':'text','text':heading}]})
        content.extend(p(t) for t in paragraphs)
    for label,url in links:
        content.append({'type':'paragraph','content':[{'type':'text','text':label,'marks':[{'type':'link','attrs':{'href':url,'target':'_blank','rel':'noopener noreferrer'}}]}]})
    return {'type':'doc','content':content}

def multipart(api,path,fields,file_field,filename,method='POST'):
    """Known-length streaming multipart upload via the existing private Tailnet path."""
    boundary='LearnHouseVideo'+uuid4().hex
    start=b''
    for key,value in fields.items():start+=f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
    start+=f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename.name}"\r\nContent-Type: {mimetypes.guess_type(filename)[0] or "application/octet-stream"}\r\n\r\n'.encode()
    end=f'\r\n--{boundary}--\r\n'.encode()
    connection=http.client.HTTPConnection('100.64.0.6',8806,timeout=600)
    try:
        connection.putrequest(method,path,skip_host=True)
        for key,value in {'Host':'syyedu.toofun.fun','Origin':api.base,'Authorization':'Bearer '+api.token,'Content-Type':'multipart/form-data; boundary='+boundary,'Content-Length':str(len(start)+filename.stat().st_size+len(end))}.items():connection.putheader(key,value)
        connection.endheaders();connection.send(start)
        with filename.open('rb') as file:
            while block:=file.read(1024*1024):connection.send(block)
        connection.send(end);response=connection.getresponse();body=response.read()
        if response.status!=200:raise RuntimeError(f'Upload failed {response.status}: '+body.decode(errors='replace')[:500])
        return json.loads(body)
    finally:connection.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--deployment-dir',type=Path,required=True);args=parser.parse_args()
    root=args.deployment_dir.resolve();work=root/'handover/icu-video-courses';statefile=work/'state.json'
    state=json.loads(statefile.read_text()) if statefile.exists() else {'courses':{},'chapters':{},'activities':{},'covers':{},'links':[]}
    manifest={m['key']:m for m in json.loads((work/'media-manifest.json').read_text())}
    api=Client(root)
    def save():
        temp=statefile.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(statefile)
    if 'folder' not in state:
        state['folder']=api.request('/api/v1/folders/',{'org_id':1,'name':'ICU视频课堂','description':'中文操作与照护视频优先，英语重症基础补充。进入课程先阅读中文导读与来源，登录成员可观看。','public':False,'color':'teal'});save()
    for source in COURSES:
        key=source['key']
        if key not in state['courses']:
            state['courses'][key]=api.request('/api/v1/courses/?org_id=1',{'name':source['name'],'description':source['description'],'public':'false','about':f"面向医师，兼顾护士。{source['language']}。来源：{source['credit']}；{source['year']}。{NOTICE}", 'learnings':'先读导读，再观看原片，最后与带教老师核对本院流程。'},form=True);save()
        course=state['courses'][key];course_uuid=course['course_uuid']
        for suffix,name in [('guide','01 开始学习：中文导读与来源'),('videos','02 完整视频课时')]:
            chapter_key=key+'/'+suffix
            if chapter_key not in state['chapters']:
                state['chapters'][chapter_key]=api.request('/api/v1/chapters/',{'name':name,'org_id':1,'course_id':course['id']});save()
        guide_key=key+'/guide'
        if guide_key not in state['activities']:
            is_en=key=='critical-care-en'
            sections=[('如何学习',[source['description'],f"语言：{source['language']}；版本：{source['year']}。",'建议由带教老师组织：先说清本节目标；观看时记录流程、角色和疑问；最后核对本院现行规程。不要把视频中的具体参数直接套用于患者。']),
                ('观看任务',['每节记录：原片标题、一个关键观察点、一个需要核对的本院流程，以及准备向带教老师提出的问题。','操作示范请重点观察准备、无菌边界、医护配合和记录交接；英语补充课请分别整理 SBAR 四部分、A–E 框架和通气问题排查的提问顺序。' if is_en else '比较示范与本院操作流程：适应证与移除评估、物品准备、无菌边界、消毒与干燥、固定与日常记录。发现差异时先向带教老师核对，不自行改变临床流程。']),
                ('原片目录',[f"{i:02d} {l['title']}｜原题：{l['original']}｜{manifest[l['key']]['duration']/60:.1f} 分钟" for i,l in enumerate(source['lessons'],1)]),
                ('署名、许可与版本',[f"原作者/发布者：{source['credit']}。原片来源与许可链接见下方。",'爱丁堡大学明确将本系列视频以 CC BY-SA 4.0 许可开放。本站保留原片，进行 MP4 容器重封装；视频及其改编继续适用 CC BY-SA 4.0。中文导读为本站另行整理。' if is_en else '使用官方资源共享页提供的原片，依据其利用说明及政府网站资料开放宣告署名转载。仅作全长 H.264/AAC 格式转换，未剪辑、裁切或移除原署名；本站课程编排不表示原发布机构认可本站。', '旧版材料的指征、消毒剂、设备与具体参数可能与当前标准不同。由本院带教/感控团队复核后再用于操作培训。英语原课含疫情时期背景，本站未将其作为当前 COVID-19 治疗方案。'])]
            links=[('原始课程/资源页面',source['source']),('原始许可/资料利用说明',source['license'])]
            if key=='cauti':
                links.append(('CDC：导尿管感染预防建议（2009指南，2024网页整理；供版本核对）','https://www.cdc.gov/infection-control/hcp/cauti/summary-of-recommendations.html'))
            elif key=='cvc':
                links.append(('CDC：血管内导管感染预防建议（2011指南，2024网页整理；供版本核对）','https://www.cdc.gov/infection-control/hcp/intravascular-catheter-related-infections/summary-recommendations.html'))
                links.append(('CDC：含氯己定敷料建议（2017更新；供版本核对）','https://www.cdc.gov/infection-control/hcp/c-i-dressings/summary-recommendations.html'))
            guide=api.request('/api/v1/activities/',{'chapter_id':state['chapters'][guide_key]['id'],'name':'学习导读、原片来源与带教任务','activity_type':'TYPE_DYNAMIC','activity_sub_type':'SUBTYPE_DYNAMIC_PAGE','content':document(source['name'],sections,links),'details':{},'published':True});state['activities'][guide_key]=guide;save()
        for n,lesson in enumerate(source['lessons'],1):
            lesson_key=key+'/'+lesson['key']
            if lesson_key not in state['activities']:
                media=manifest[lesson['key']];file=work/'ready'/media['file'];assert file.stat().st_size==media['bytes']
                meta={'source_url':source['source'],'original_title':lesson['original'],'attribution':source['credit'],'license_url':source['license'],'source_version':source['year'],'media_sha256':media['sha256'],'changes':media['changes']}
                activity=multipart(api,'/api/v1/activities/video',{'name':f"{n:02d} {lesson['title']}（{source['year']}）",'chapter_id':state['chapters'][key+'/videos']['id'],'details':'{}','extra_metadata':json.dumps({'curated_video':meta},ensure_ascii=False)},'video_file',file)
                state['activities'][lesson_key]=activity;save();print('Uploaded',lesson['key'],flush=True)
            activity=state['activities'][lesson_key]
            if not activity['published']:
                state['activities'][lesson_key]=api.request('/api/v1/activities/'+activity['activity_uuid'],{'published':True},method='PUT');save()
        if key not in state['covers']:
            state['covers'][key]=multipart(api,'/api/v1/courses/'+course_uuid+'/thumbnail',{'thumbnail_type':'image'},'thumbnail',HERE.parent/'icu-examples/covers'/(source['cover']+'.webp'),method='PUT')['thumbnail_image'];save()
        if not state['courses'][key]['published']:
            state['courses'][key]=api.request('/api/v1/courses/'+course_uuid,{'published':True,'public':False},method='PUT');save()
        if course_uuid not in state['links']:
            api.request('/api/v1/folders/'+state['folder']['folder_uuid']+'/content?'+urllib.parse.urlencode({'resource_uuid':course_uuid}),{},method='POST');state['links'].append(course_uuid);save()
        print('Published',source['name'],flush=True)
