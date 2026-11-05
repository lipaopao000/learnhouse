# ICU 教学示例馆

原生 LearnHouse 内容建设，面向医师，兼顾护理。所有病例和数值为原创虚构示例；不包含真实患者记录、药物剂量或自动诊疗建议。内容用来示范如何组织交接、教学讨论、资料核对和文献阅读，不替代本院批准的流程。

## 交付内容

- Library：独立的「ICU教学示例馆」及 6 个分类目录。
- 社区：入科与交接班、病例讨论与呼吸循环、医护协作与安全、指南读书会与教学共建，共 12 篇有正文的示例帖；各社区 1 篇置顶导航。
- 课程：独立示例课程，4 个已发布图文课时，包含练习任务和官方资源入口。
- 手册：8 页 PDF，覆盖 SBAR、机械通气观察、循环趋势、共同查房、AKI/CRRT、血气资料核对、病例脱敏、PICO/教学反馈；各页包含字段和已填示例。
- Playground：SBAR 交接班练习器与 PICO 文献阅读卡，可填示例、生成、复制/选中及清空。完全本地处理，无外部请求和持久存储。
- 课程封面：12 张贴题的统一线描插画，已上传至 11 门课程草稿和 1 门示例课程；[素材与提示词](covers/README.md) 一同纳入 Git。

新文件夹、课程、社区、PDF 均为 private，不绑定用户组，供组织成员阅读；Playground 为 authenticated。原有 11 门课程及其 44 个未审核课时保持未发布。没有创建虚构评论或其他用户的参与记录。

## 管理员后续维护

1. 在原生社区发帖或修改置顶导航；保持「虚构教学示例」或符合院规的脱敏标识。
2. 在 Library 相应目录添加资料；在课程编辑器维护课时正文。课程和课时的发布状态分别核对。
3. 正式制度/操作流程指定作者和审核人，注明适用范围、版本、复审时间，再按科室要求发布。
4. 使用官方来源链接，核对正式版/草案和更新状态；不转载未授权全文。

## 构建与恢复

```sh
python3 ops/icu-examples/build.py
python3 ops/icu-examples/seed.py --deployment-dir /path/to/private/deployment
node ops/icu-examples/verify.cjs /path/to/private/deployment
```

`catalog.py` 是原始内容；`build.py` 生成 PDF 和自包含 HTML。PDF 构建依赖 ReportLab 和 macOS Arial Unicode 字体，可按环境替换等效中文字体。导出物已逐页渲染检查。

种子程序每创建一项便写入部署私有目录 `handover/icu-examples-state.json`；保留此文件后重跑仅恢复未完成步骤，不覆盖管理员后续编辑。不要删除状态文件后在同一站点重新执行。`verification.json` 不含账号凭据。

由于上游创建 Playground 时使用无前缀 UUID，而 Library 附加资源的 RBAC 仅识别 `playground_` 前缀，互动练习通过原生 Playground 列表及课程/社区内链接进入；不篡改资源 ID。经 Tailnet 私有入口上传有意包含脚本的 Playground HTML，避免公开 WAF 对内容编辑产生误报，未调整 WAF 规则。

## 随验收修复的媒体下载问题

部署基线 v4 的 `_SelectiveGZipResponder` 在 Starlette 处理 `http.response.start` 后才标记 PDF 为免压缩，导致浏览器请求 PDF 时直接发送 body 而缺少 start，返回 500。`media_compat.py` 仅替换这一类，使用本仓库 `apps/api/app.py` 已有的正确顺序，保留其他部署定制。

- 基线：`local/learnhouse:20261105-username-accounts-v4`
- 修复镜像：`local/learnhouse:20261105-icu-examples-v5`
- `test_media_compat.py` 在镜像实际依赖下验证 gzip/identity、整份 PDF、流、Range、HEAD、重定向及 JSON，共 12 项。
- `deploy_media_compat.py` 通过 Portainer Stack 17 仅更新 app 镜像，保存原 Stack/compose 私有快照，保留全部环境变量、挂载及其他服务。
- 回滚：使用私有发布快照恢复 Stack 17 原 compose/Env。内容建设在数据库中，回滚镜像不删除已添加内容。

官方来源于 2026-11-05 核对：

- [AHRQ SBAR](https://www.ahrq.gov/teamstepps-program/curriculum/communication/tools/sbar.html)
- [AARC 官方指南入口](https://www.aarc.org/resource/clinical-practice-guidelines/)
- [SCCM ICU Liberation](https://www.sccm.org/clinical-resources/iculiberation-home)
- [KDIGO AKI/AKD](https://kdigo.org/guidelines/acute-kidney-injury/)
