"""Build an eight-page original workbook and two self-contained practice tools."""
import json
from pathlib import Path
from html import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether
from reportlab.lib.pagesizes import A4
from catalog import HANDOUTS, NOTICE, SOURCES

HERE=Path(__file__).resolve().parent
OUT=HERE/'output/pdf'; OUT.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(TTFont('CJK','/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
styles={name:ParagraphStyle(name,fontName='CJK',fontSize=size,leading=leading,textColor=HexColor(color),wordWrap='CJK',spaceAfter=after) for name,size,leading,color,after in [
 ('kicker',9,14,'#64748b',12),('title',23,30,'#0f172a',9),('subtitle',11,17,'#475569',14),
 ('notice',9,14,'#7c4a16',14),('heading',12,18,'#0f766e',7),('body',10,16,'#1e293b',7),('source',8,12,'#64748b',4)]}
story=[]
for n,item in enumerate(HANDOUTS,1):
    if n>1: story.append(PageBreak())
    story.extend([Paragraph(f'ICU 教学模板与示例  /  {n:02d}',styles['kicker']),Paragraph(item['title'],styles['title']),Paragraph(item['subtitle'],styles['subtitle']),Paragraph(NOTICE,styles['notice'])])
    for heading,paras in item['sections']:
        story.append(KeepTogether([Paragraph(heading,styles['heading']),Paragraph(escape(paras[0]),styles['body'])]))
        story.extend(Paragraph(escape(p),styles['body']) for p in paras[1:])
        story.append(Spacer(1,5))
    if item['source'] is not None:
        label,url=SOURCES[item['source']]
        story.append(Paragraph('延伸来源：'+escape(label)+'（2026-11-05 核对）',styles['source']))
        story.append(Paragraph(f'<link href="{escape(url)}" color="#0f766e">{escape(url)}</link>',styles['source']))
    else:
        story.append(Paragraph('原创记录与沟通练习；不提供诊疗结论或处方。',styles['source']))
def footer(c,d):
    c.setStrokeColor(HexColor('#e2e8f0'));c.line(42,40,A4[0]-42,40)
    c.setFont('CJK',8);c.setFillColor(HexColor('#64748b'))
    c.drawString(42,26,'省医院 ICU 教学平台  |  教学示例 v1.0  |  2026-11-05')
    c.drawRightString(A4[0]-42,26,f'{d.page} / 8')
SimpleDocTemplate(str(OUT/'icu-teaching-workbook.pdf'),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=38,bottomMargin=51,title='ICU教学模板与示例',author='ICU教学平台').build(story,onFirstPage=footer,onLaterPages=footer)

css='''*{box-sizing:border-box}body{margin:0;background:#fafafa;color:#18181b;font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:960px;margin:auto;padding:28px}small,.muted{color:#71717a}.tag{display:inline-block;background:#f0fdfa;color:#0f766e;border-radius:8px;padding:4px 10px;font-size:12px}h1{font-size:28px;line-height:1.3;margin:16px 0 10px}h2{font-size:18px}p{margin:8px 0 16px}.notice{padding:14px 16px;border:1px solid #e4e4e7;border-radius:12px;background:white;font-size:13px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:22px 0}label{display:block;font-weight:600}label small{display:block;font-weight:400;margin:4px 0 7px}textarea{width:100%;min-height:100px;border:1px solid #d4d4d8;border-radius:10px;padding:12px;font:inherit;background:white;resize:vertical}textarea:focus,button:focus-visible{outline:2px solid #0f766e;outline-offset:2px}button{border:1px solid #d4d4d8;border-radius:10px;padding:10px 16px;background:white;color:#18181b;font:inherit;cursor:pointer;margin:0 8px 10px 0}button.primary{background:#18181b;color:white;border-color:#18181b}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;background:white;border:1px solid #e4e4e7;border-radius:12px;padding:18px;min-height:120px}#status{min-height:24px;color:#0f766e;font-size:13px}@media(max-width:650px){main{padding:18px}.grid{grid-template-columns:1fr}h1{font-size:24px}}'''
tools=[
 dict(key='sbar',title='SBAR交接班练习器',intro='把一段交班整理成四个清楚的部分。先填写虚构内容，再生成练习稿。',
 fields=[('S｜现状','当前问题、观察时间、交接对象'),('B｜背景','入科原因、已有支持、信息来源'),('A｜评估与缺口','客观观察、趋势、自己的判断与尚缺资料'),('R｜请求与闭环','希望谁、何时完成什么；接收确认与复评')],
 example=['病例 A，08:00 呼吸频率 30 次/分，较 07:00 增快，向带教老师汇报。','虚构病例因呼吸困难入科；有氧疗记录，但设备和流量尚需核对。','已有呼吸频率变化；尚缺同期 SpO2、意识、呼吸做功及氧疗条件，暂不能确定原因。','请带教老师床旁共同评估；轮转医师补齐同期资料，护士反馈监测与设备情况，交接双方复述任务。']),
 dict(key='pico',title='PICO文献阅读卡',intro='先写清问题，再记录来源、结果和局限。这里不会自动检索或生成研究结论。',
 fields=[('P｜人群或问题','对象、背景、纳排条件'),('I｜干预或暴露','希望研究的措施'),('C｜对照','比较条件'),('O｜结局','关注结局与观察时长'),('原始来源与结果','题名、作者、年份、DOI/官网；数据与不确定性'),('局限与本地适用性','偏倚、外推限制、与本地制度的关系')],
 example=['ICU 轮转医师。','结构化 SBAR 交接培训。','常规入科介绍。','情景演练中的关键要素完整性。','学习入口：AHRQ TeamSTEPPS SBAR。尚未纳入原始研究，无效果数据，不能得出培训有效的结论。','后续需检索原始研究并核对设计、人群和测量工具；科室培训评价需结合实际工作。'])]
for tool in tools:
    labels=[x[0] for x in tool['fields']]
    fields=''.join(f'<label for="f{i}">{escape(label)}<small>{escape(hint)}</small><textarea id="f{i}" placeholder="只填写虚构或合规脱敏的教学内容"></textarea></label>' for i,(label,hint) in enumerate(tool['fields']))
    script='''const labels=LABELS,example=EXAMPLE;const inputs=labels.map((_,i)=>document.getElementById('f'+i));const out=document.getElementById('output'),status=document.getElementById('status');function generate(){out.textContent='教学练习稿（非诊疗建议）\\n\\n'+labels.map((l,i)=>l+'\\n'+(inputs[i].value.trim()||'【未填写：请补齐或注明未知】')).join('\\n\\n');status.textContent='已生成。请核对事实、来源、时间与信息缺口。'}document.getElementById('generate').onclick=generate;document.getElementById('example').onclick=()=>{inputs.forEach((e,i)=>e.value=example[i]);generate()};document.getElementById('clear').onclick=()=>{inputs.forEach(e=>e.value='');out.textContent='在上方填写后点击“生成练习稿”。';status.textContent='已清空本页内容。'};document.getElementById('copy').onclick=async()=>{try{await navigator.clipboard.writeText(out.textContent);status.textContent='已复制。'}catch(e){const r=document.createRange();r.selectNodeContents(out);const s=window.getSelection();s.removeAllRanges();s.addRange(r);status.textContent='浏览器限制了剪贴板，已选中全文，可手动复制。'}};'''.replace('LABELS',json.dumps(labels,ensure_ascii=False)).replace('EXAMPLE',json.dumps(tool['example'],ensure_ascii=False))
    html=f'''<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{tool['title']}</title><style>{css}</style></head><body><main><span class="tag">ICU 教学示例 · 本地练习</span><h1>{tool['title']}</h1><p class="muted">{tool['intro']}</p><div class="notice">{NOTICE}<br>输入只在当前页面内处理；不上传、不持久保存。关闭页面后请自行保存需要保留的虚构练习稿。</div><div class="grid">{fields}</div><button class="primary" id="generate">生成练习稿</button><button id="example">填入虚构示例</button><button id="clear">清空</button><h2>练习稿</h2><pre id="output">在上方填写后点击“生成练习稿”。</pre><button id="copy">复制练习稿</button><p id="status" role="status" aria-live="polite"></p><small>v1.0 · 由带教老师组织反馈，不设自动评分或诊疗处方。</small></main><script>{script}</script></body></html>'''
    target=HERE/'playgrounds';target.mkdir(exist_ok=True);(target/(tool['key']+'.html')).write_text(html)
print('Built workbook (8 topic pages) and 2 offline tools')
