"""Curated source catalog. Downloaded media and credentials stay outside Git."""
CDC = 'https://www.cdc.gov.tw/Category/MPage/K20wqCzSTz_eSz3Yyk0m9w'
CDC_LICENSE = 'https://www.cdc.gov.tw/Category/Fpage/TxkBIR9agw_IBRRmvn9TcQ'
ED = 'https://open.ed.ac.uk/covid-19-critical-care-application-and-understanding/'
CC = 'https://creativecommons.org/licenses/by-sa/4.0/'
NOTICE = '历史教学资料，用于带教讨论，不作为本院现行操作规程。操作指征、消毒剂、耗材和具体参数须由本院带教及感控团队按最新规范复核；视频学习不等于取得独立操作资质。'
COURSES = [
 dict(key='cvc', name='中心静脉导管｜置入与每日照护（中文视频）', cover='infection',
      description='两节中文完整示范：中心导管置入、每日照护与医护配合。原片发布于2015年，附来源、学习任务和版本复核提示。',
      source=CDC, license=CDC_LICENSE, credit='台湾卫生福利部疾病管制署', year='2015', language='中文（原片繁体字幕）',
      lessons=[dict(key='cvc-insert', title='中心导管组合式置入措施', original='中心導管組合式置入措施', parts=['Cr_h3ek0YewAAJZJJO0New','05UGVt75M7lJ_Ggq3dUcbw','58AL4rgNzGfFA2wuofbA3g','K60aRshJVjZnoj1M_zOQ-w']),
               dict(key='cvc-care', title='中心导管组合式每日照护措施', original='中心導管組合式照護措施', parts=['gJmwLdCB33mLhBjsB1hmJQ','-f7BaR81RFNZRtYHEcJkDw'])]),
 dict(key='cauti', name='导尿管安全｜置入与感染预防（中文视频）', cover='renal',
      description='三节中文示范：女性、男性导尿管置入及每日照护。适合医师熟悉操作协作、护士开展带教；保留原片并明确历史版本。',
      source=CDC, license=CDC_LICENSE, credit='台湾卫生福利部疾病管制署', year='2017页面更新版', language='中文（原片繁体字幕）',
      lessons=[dict(key='cauti-female',title='女性导尿管置放：无菌操作与配合',original='降低導尿管相關泌尿道感染組合式置放措施（女性）',parts=['029MqnUz3WXeJGyxY008lg','ek698zrrPMhKtUZot-e_RQ']),
               dict(key='cauti-male',title='男性导尿管置放：无菌操作与配合',original='降低導尿管相關泌尿道感染組合式置放措施（男性）',parts=['Oi3nHhIQx3a3V1ZBByKpfQ','62G34gtC2yLto5QavUF6dA']),
               dict(key='cauti-daily',title='留置导尿管每日照护与记录',original='降低導尿管相關泌尿道感染組合式每日照護措施',file='uGoJjEyPLmV31zj4KLyyEg')]),
 dict(key='critical-care-en',name='重症床旁基础｜评估、交班与通气（英语补充）',cover='ventilation',
      description='爱丁堡大学开放课程精选：结构化SBAR交班、A–E评估、有创通气问题排查。英语原声，配中文学习导读；未制作中文字幕。',
      source=ED,license=CC,credit='University of Edinburgh / NHS Lothian；原课程 COVID-19 Critical Care: Understanding and Application',year='2020课程；2022媒体库发布',language='英语原声，中文导读，无中文字幕',
      lessons=[dict(key='sbar',title='结构化 SBAR 交班',original='Structured SBAR Handover',entry='1_jkc5wiov',flavor='1_cey54424'),
               dict(key='assessment',title='危重患者 A–E 评估导论',original='Daily Assessment 1',entry='1_um1frpdl',flavor='1_dsupmcdo'),
               dict(key='ventilation',title='有创通气：问题排查与调整思路',original='Troubleshooting and Making Changes to Invasive Ventilation',entry='1_o2zg8cie',flavor='1_pinqylx0')])
]
