# ICU 视频课堂：首批资源

面向医师，兼顾护士。首批三门独立课程、八段完整视频：中文五段，英语三段。新课程为已发布、仅登录组织成员可观看；不改变既有十一门临床草稿。课程均有中文导读、学习任务、原片题名、版本、来源和署名，以及既有 ICU 系列封面。

| 课程 | 视频 | 原始提供者 | 版本与用途 |
| --- | --- | --- | --- |
| 中心静脉导管 | 置入、每日照护 | 台湾卫生福利部疾病管制署 | 2015 年原片，历史示范与带教讨论 |
| 导尿管安全 | 女性置入、男性置入、每日照护 | 同上 | 2017 年资源页更新版，历史示范与带教讨论 |
| 重症床旁基础 | SBAR、A–E 评估、有创通气排查 | University of Edinburgh / NHS Lothian | 2020 年课程、2022 年媒体库发布；英语原声，中文导读，未制作中文字幕 |

历史材料不等于本院现行规范，也不授予独立操作资质。导读要求带教/感控团队复核指征、耗材、消毒方式和具体参数，并提供 CDC 原始指南及更新入口。没有选用疫情早期治疗方案或旧版含 CHG 口腔护理的 VAP 示范。

## 来源与许可

- 中文视频来自[官方资源共享页](https://www.cdc.gov.tw/Category/MPage/K20wqCzSTz_eSz3Yyk0m9w)的直接下载附件。页面说明这些为本署录制的教学影片，并欢迎利用；[政府网站资料开放宣告](https://www.cdc.gov.tw/Category/Fpage/TxkBIR9agw_IBRRmvn9TcQ)允许署名重制、编辑及公开传输，另行声明限制的材料除外。本次未使用仅供观看/禁止转载的第三方素材。保留原片所有署名和画面，仅作全长格式转换。
- 英语视频来源及许可见[爱丁堡大学 Open.Ed](https://open.ed.ac.uk/covid-19-critical-care-application-and-understanding/)。该页将此系列视频明确列为 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)，并提供 Media Hopper 下载入口。采用公开匿名播放器提供的原片下载接口，无个人登录、付费资源或访问限制绕过。视频仅重封装为 fast-start MP4，仍适用 CC BY-SA 4.0；本站课程编排不表示来源机构认可本站。
- `catalog.py` 保存单片原题及原始文件标识。实际下载文件、原始网页快照、下载散列、转换日志与私有部署状态放在部署工作目录 `handover/icu-video-courses/`，不提交大型媒体或播放器会话参数。

## 重现与恢复

依赖 Python requests、FFmpeg/FFprobe、unar。`unar` 用于多卷 RAR，不能把单个分卷当成独立视频。脚本不执行下载包中的 HTML、脚本或可执行程序。

```bash
python3 ops/icu-video-courses/download.py --work-dir "$DEPLOY_DIR/handover/icu-video-courses"
python3 ops/icu-video-courses/prepare.py --work-dir "$DEPLOY_DIR/handover/icu-video-courses"
python3 ops/icu-video-courses/seed.py --deployment-dir "$DEPLOY_DIR"
node ops/icu-video-courses/verify.cjs "$DEPLOY_DIR"
```

`prepare.py` 检查转换前后时长，完整解码输出文件并记录 H.264/AAC、分辨率、大小、SHA-256。旧 WMV 的源解码可能产生少量告警；转换后 MP4 单独完整解码检查，格式转换没有人工剪辑或裁切。

`seed.py` 使用原生课程、章节、视频、缩略图和 Library API，并逐次保存 `state.json`。大文件通过现有 Tailnet HTTP 路径流式上传，Host/Origin 保持主域名，Tailnet 负责链路加密；不放宽 WAF。每个视频完成上传并发布后，最后发布课程。状态文件存在时只继续未完成步骤。

若 POST 上传时连接中断，先用课程 meta 的 `with_unpublished_activities=true` 查询服务端，按题名、文件大小和 SHA-256 核对；把已成功结果补入状态后继续。不能因为客户端未收到响应就重复 POST。不要删除状态文件后重跑，否则会创建重复课程。

视频沿用宿主机持久化内容目录及现有 `.4` 自动预热。等待 `.4` 定时任务发现并完成新文件后，再执行浏览器验收，避免把手动播放触发的缓存误报为自动预热。腾讯云 3GB 限额、`.4` 无人为容量上限的策略均保持。

验收使用无分组临时学员，检查全部八段的原生播放器、起播、跳转、头尾 Range 字节、匿名拒绝和 Maintainer 读取；临时账号在 finally 中清理。缓存清单与源文件哈希另存报告。`verification.json` 记录本次最终可审计结果。

回退内容只需在后台取消发布这三门课程；视频原文件和缓存保留便于恢复。需要删除时按 `state.json` 的精确 UUID 操作，不能清空整个内容目录或缓存。
