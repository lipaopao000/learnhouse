"""Prepare private ICU course drafts and cohorts; never creates real users."""
import argparse
import json
from pathlib import Path
import urllib.parse
from client import Client

parser = argparse.ArgumentParser()
parser.add_argument('--deployment-dir', type=Path, required=True)
args = parser.parse_args()
out = args.deployment_dir / 'handover'
out.mkdir(mode=0o700, exist_ok=True)
state_file = out / 'seed-state.json'
state = json.loads(state_file.read_text()) if state_file.exists() else {'groups': {}, 'folders': {}, 'courses': {}}
api = Client(args.deployment_dir)


def save():
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def doc(title, paragraphs, bullets=(), links=()):
    nodes = [{'type': 'heading', 'attrs': {'level': 1}, 'content': [{'type': 'text', 'text': title}]}]
    nodes += [{'type': 'paragraph', 'content': [{'type': 'text', 'text': p}]} for p in paragraphs]
    if bullets:
        nodes.append({'type': 'bulletList', 'content': [{'type': 'listItem', 'content': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': text}]}]} for text in bullets]})
    for label, url in links:
        nodes.append({'type': 'paragraph', 'content': [{'type': 'text', 'text': label, 'marks': [
            {'type': 'link', 'attrs': {'href': url, 'target': '_blank', 'rel': 'noopener noreferrer'}}]}]})
    return {'type': 'doc', 'content': nodes}


groups = ['本院医师', '进修医师', '住培医师', '轮转医师', '护理人员', '带教老师', '教学管理员']
existing = api.request('/api/v1/usergroups/org/1')
for name in groups:
    if name not in state['groups']:
        group = next((g for g in existing if g['name'] == name), None) or api.request('/api/v1/usergroups/', {
            'org_id': 1, 'name': name, 'description': 'ICU 教学人员分类；分组本身不授予管理员权限。'})
        state['groups'][name] = group
        save()

existing_folders = api.request('/api/v1/folders/org/1/page/1/limit/100')
root_name = 'ICU教学资源'
if root_name not in state['folders']:
    folder = next((f for f in existing_folders if f['name'] == root_name), None) or api.request('/api/v1/folders/', {
        'org_id': 1, 'name': root_name, 'description': '医师为主、兼顾护理的教学资料；由科室审核后发布。', 'public': False})
    state['folders'][root_name] = folder
    save()
for name in ['入科与制度', '核心临床专题', '护理与安全', '病例与考核', '管理员交接']:
    if name not in state['folders']:
        state['folders'][name] = api.request('/api/v1/folders/', {'org_id': 1, 'name': name,
            'description': 'ICU 教学资料分类。', 'public': False,
            'parent_folder_uuid': state['folders'][root_name]['folder_uuid']})
        save()

catalog = [
    ('平台使用与培训须知', '入科与制度', ['账号登录与修改初始密码', '课程学习与问题反馈', '病例脱敏与资料使用']),
    ('ICU入科与规范交接班', '入科与制度', ['入科培训与岗位职责', '结构化交接班', '危急值闭环与沟通', '常用设备与安全检查']),
    ('气道管理与机械通气', '核心临床专题', ['氧疗、HFNC与无创通气', '人工气道与插管配合', '呼吸机模式与波形', 'ARDS与肺保护通气', '撤机与拔管评估']),
    ('休克与血流动力学', '核心临床专题', ['休克识别与床旁评估', '容量反应性与组织灌注', '血管活性药物专题', '床旁超声与循环监测']),
    ('感染与脓毒症', '核心临床专题', ['病原学与感染源评估', '脓毒症规范与病例研讨', '抗菌药物管理', '院内感染防控与隔离']),
    ('镇痛镇静、谵妄与早期康复', '核心临床专题', ['疼痛与镇静评估', '谵妄识别与教学评估', 'ABCDEF团队协作', '早期活动与睡眠照护']),
    ('AKI、CRRT与内环境', '核心临床专题', ['AKI识别与分层', 'CRRT模式、处方阅读与监测', '血气与酸碱分析', '电解质紊乱病例讨论']),
    ('营养与常见系统问题', '核心临床专题', ['重症营养评估', '血糖管理专题', '凝血、出血与血栓', '消化道问题与器官支持']),
    ('抢救技能与护理配合', '护理与安全', ['心肺复苏与团队分工', '气道与呼吸回路应急演练', '血管通路与导管维护', '危重患者转运与安全']),
    ('病例讨论与教学考核', '病例与考核', ['病例复盘模板', '教学查房模板', '课件与视频提交规范', '理论与技能考核记录']),
    ('管理员工作台与交接手册', '管理员交接', ['人员、角色与分组', '网页批量创建账号', '课程资料审核与发布', '运行状态与故障交接']),
]
source_links = {
    '感染与脓毒症': [('SCCM 指南官方入口（发布前核对具体版本）', 'https://www.sccm.org/clinical-resources/guidelines')],
    '镇痛镇静、谵妄与早期康复': [('SCCM ICU Liberation 官方资料', 'https://www.sccm.org/clinical-resources/iculiberation-home')],
    'AKI、CRRT与内环境': [('KDIGO AKI 官方资源（注意草案与正式版本区别）', 'https://kdigo.org/guidelines/acute-kidney-injury/')],
}
all_courses = api.request('/api/v1/courses/org_slug/default/page/1/limit/100?include_unpublished=true')
for title, category, sections in catalog:
    if title not in state['courses']:
        existing_course = next((c for c in all_courses if c['name'] == title), None)
        if existing_course:
            raise RuntimeError('A same-name course already exists outside this seed state; review before changing it')
        course = api.request('/api/v1/courses/?org_id=1', {'name': title, 'description': 'ICU 教学课程草稿｜医师为主、兼顾护士',
            'public': 'false', 'about': '教学框架与资料收集入口。临床内容由指定讲师和审核人补齐、审核后发布。'}, form=True)
        assert not course['public'] and not course['published']
        state['courses'][title] = {'course': course, 'chapters': {}, 'activities': {}}
        save()
        folder = state['folders'][category]
        api.request('/api/v1/folders/' + folder['folder_uuid'] + '/content?' + urllib.parse.urlencode({'resource_uuid': course['course_uuid']}), {}, method='POST')
    record = state['courses'][title]
    course = record['course']
    for number, section in enumerate(sections, 1):
        if section not in record['chapters']:
            record['chapters'][section] = api.request('/api/v1/chapters/', {'name': f'{number:02d} {section}', 'org_id': 1, 'course_id': course['id']})
            save()
        if section in record['activities']:
            continue
        if title == '管理员工作台与交接手册':
            paragraphs = ['本页是管理员交接资料，按实际人员和科室制度填写、审核后使用。']
            bullets = ['分组不等于权限：教学管理员分组不会自动成为 Admin；仅给必要人员管理员权限。',
                '学员使用邮箱和独立初始密码登录，首次登录后修改密码；当前未验证系统强制首次改密功能。',
                '先预览表格并检查邮箱、角色、重复项，再确认创建；现有账号不覆盖密码。',
                '课程及课时分别有发布状态。审核内容和观看范围后，再发布课程与具体课时。',
                '交接时核对真实管理员登录、课程发布、账号恢复、备份及视频自动缓存状态。']
            links = [('网页批量创建账号工具', 'https://syyedu.toofun.fun/dash/users/import'), ('原生用户管理', 'https://syyedu.toofun.fun/dash/users/settings/users')]
        elif title == '平台使用与培训须知':
            paragraphs = ['本平台用于科室教学与培训。请按分配的课程和培训安排完成学习。']
            bullets = ['使用本人邮箱登录，初始密码由管理员分别交付；首次登录后修改，勿共用账号。',
                '打开课程、选择章和课时。若没有播放入口，向带教老师确认课时是否已发布。',
                '问题反馈请记录课程名、课时名、时间和浏览器；不要发送自己的密码。',
                '教学病例应完成脱敏。上传前核对姓名、住院号、身份证号、检查影像及附件中的身份信息。']
            links = []
        else:
            paragraphs = [f'本节主题：{section}。面向 ICU 医师、进修和住培/轮转人员，护理相关环节采用医护共同讨论。',
                '本页为教学提纲和资料收集框架，不是院内正式诊疗操作规程。由科室指定讲师补充具体内容、引用来源和版本，审核后发布。']
            bullets = [f'学习目标：围绕“{section}”明确基本概念、评估思路、团队沟通和常见误区。',
                '资料清单：课程视频或讲课 PPT/PDF；科室现行 SOP；已脱敏的典型病例；配套练习或技能评价表。',
                '讨论提纲：需要收集哪些信息？如何表达评估依据？何时复评？医师和护士如何分工并闭环交接？',
                '考核方式：课前自测、课后病例讨论或情景演练；由带教老师按明确标准记录完成情况。',
                '审核记录：讲师待指定；审核人待指定；资料版本待填写；复审日期待填写。']
            links = source_links.get(title, [])
        activity = api.request('/api/v1/activities/', {'chapter_id': record['chapters'][section]['id'],
            'name': section, 'activity_type': 'TYPE_DYNAMIC', 'activity_sub_type': 'SUBTYPE_DYNAMIC_PAGE',
            'content': doc(section, paragraphs, bullets, links), 'details': {}, 'published': False})
        assert activity['published'] is False
        record['activities'][section] = activity
        save()
    print('Prepared draft:', title, flush=True)

# Make the future access structure ready without adding any real people.
teaching = [r['course']['course_uuid'] for name, r in state['courses'].items() if name != '管理员工作台与交接手册']
folder_ids = [f['folder_uuid'] for name, f in state['folders'].items() if name != '管理员交接']
for name, group in state['groups'].items():
    resources = teaching + folder_ids
    if name == '教学管理员':
        resources += [state['courses']['管理员工作台与交接手册']['course']['course_uuid'], state['folders']['管理员交接']['folder_uuid']]
    api.request('/api/v1/usergroups/' + str(group['id']) + '/add_resources?' + urllib.parse.urlencode({'resource_uuids': ','.join(resources)}), {}, method='POST')
save()
summary = {'courses': len(state['courses']), 'chapters': sum(len(c['chapters']) for c in state['courses'].values()),
    'activities': sum(len(c['activities']) for c in state['courses'].values()), 'groups': len(state['groups']),
    'folders': len(state['folders']), 'published': False, 'real_accounts_created': 0,
    'course_names': list(state['courses'])}
(out / 'seed-verification.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
print(json.dumps(summary, ensure_ascii=False, indent=2))
