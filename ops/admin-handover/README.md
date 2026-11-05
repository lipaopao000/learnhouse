# ICU 教学平台管理员交接

当前已升级为用户名账号与管理员重置版本 v4，完整说明见 [用户名账号说明](../username-accounts/README.md)。

## 网页批量预建账号

入口：<https://syyedu.toofun.fun/dash/users/import>。需要先登录管理员或维护者账号。

1. 下载空白模板，用 Excel 填写人员信息，另存为 **CSV UTF-8（逗号分隔）**。当前不直接读取 `.xlsx`。
2. 上传 CSV，点击“检查并预览”。检查邮箱、角色、分组以及重复和错误项。
3. 核对后勾选确认，点击“确认创建账号”。每次最多 500 人，页面按 25 人一批依次提交。
4. 下载“账号与初始密码 CSV”，分别向本人交付用户名（或已绑定邮箱）和初始密码。请在关闭或刷新页面前下载。
5. 通知本人首次登录后修改密码。当前平台**不强制首次改密**。

CSV 列：

| 姓名 | 邮箱 | 用户名 | 角色 | 分组 |
| --- | --- | --- | --- | --- |
| 必填 | 选填；以后可自愿绑定 | 无邮箱时必填；有邮箱时可留空 | 学员或讲师；留空为学员 | 可留空；多个组用 `;` 分隔 |

可用分组：本院医师、进修医师、住培医师、轮转医师、护理人员、带教老师、教学管理员。

已有本组织账号会跳过，不覆盖密码、角色和分组。已有其他组织账号需要通过原生邀请加入。表格内重复、无效邮箱、未知分组会报错，修正后重新上传。

管理员角色请在原生用户管理中单独授予；“教学管理员”只是分组名称。仅向需要接手管理的人授予管理员权限。账号支持用户名或已绑定邮箱登录。邮箱留空时，必须填写唯一用户名。

此入口是自托管定制功能。LearnHouse 原生网页仍提供批量邮件邀请和成员管理，原生文档见 [Members & Invites](https://docs.learnhouse.app/platform/users/members-and-invites)。

## 密码和启用方式

- 管理员预建的账号直接启用，不发送邀请、欢迎或验证邮件；无邮箱账号保持未绑定状态，公共自主注册仍遵循现有邮箱验证策略。
- 浏览器用 Web Crypto 为每人生成独立 24 位随机初始密码，通过 HTTPS 交给后端散列存储。密码只在本页内存和管理员主动下载的交付表中保留，不写入 localStorage 或服务器明文文件。
- 网络中断时保持当前页面并使用重试。导入批次 ID 可恢复同批已创建结果，不会重置已有账号密码。刷新后无法恢复页面中的明文密码，可由管理员重置密码，或在已绑定邮箱后使用邮件找回。
- 下载表含敏感密码，应逐人分发、限制保存范围。页面没有自动发送消息功能。

## 已准备的资源

已创建 **11 门私有、未发布课程，44 个章节和 44 个文字课时草稿**，以及 ICU 教学资源库及 5 个子目录。面向医师，兼顾护理配合：

1. 平台使用与培训须知
2. ICU 入科与规范交接班
3. 气道管理与机械通气
4. 休克与血流动力学
5. 感染与脓毒症
6. 镇痛镇静、谵妄与早期康复
7. AKI、CRRT 与内环境
8. 营养与常见系统问题
9. 抢救技能与护理配合
10. 病例讨论与教学考核
11. 管理员工作台与交接手册

这些是教学提纲、资料收集和审核框架，**不是完整讲义或已审核的诊疗规程**。每节有目标、资料清单、讨论与考核提示及审核人/版本占位。由科室指定讲师补充 PPT、视频、脱敏病例和本院 SOP，经审核后再发布课程与课时，并核对观看范围。

现有公开 `test` 课程和原视频保留。没有代建真实人员账号；验收用临时账号已删除。

## 实现与运维

- API 源码：`apps/api/src/routers/orgs/user_import.py`；在 `src/router.py` 注册。
- 静态管理界面：本目录 `web/`，通过 home nginx 同域提供，不依赖 Next.js 重建。
- API：`GET /api/v1/orgs/{id}/users/import/meta`，`POST .../preview`，`POST .../create`。
- 默认关闭，环境变量 `LEARNHOUSE_ADMIN_USER_IMPORT_ENABLED=true` 开启。仅人工登录管理员/维护者，拒绝 API Token；POST 检查同源 Origin，沿用组织权限、会话政策、原生密码及资料校验、成员与管理员席位限额。
- Redis 串行导入锁；按人员提交事务；同批重试幂等。输入校验错误不回显含密码的请求体，日志只写组织、操作者和新用户 ID。
- 首次导入功能部署镜像 `local/learnhouse:20261105-admin-import-v3`（当前已由 v4 取代），基于现有 `local/learnhouse:20261105-email-verification-v2` 叠加两个 API 文件，保留既有 SMTP/邮箱验证功能。
- Portainer Stack 17 更新应用镜像、开关和 nginx 静态只读挂载；数据库没有迁移。视频 exporter Stack 19 继续使用原镜像。没有修改 Lucky/WAF、视频缓存或其他 Stack。
- 静态文件：`D:\deploy\LearnHouse\admin-tools-ui`，挂载 `/srv/admin-tools:ro`。只放网页公开文件，切勿把人员表或交付密码表放进此目录。
- 备份：服务器 `D:\deploy\LearnHouse\backups\admin-import-v3`；本机部署目录 `handover/releases/20261105-admin-import-v3` 保存私有 Stack/环境快照。
- 账号审计：新建用户 `extra_metadata.admin_import` 仅保存操作者 ID、批次 ID、时间，不保存初始密码。

构建需在 server-ba WSL 的源文件目录运行 `python3 ops/admin-handover/build.py`。脚本从 v2 提取实际运行的 router，再追加注册，避免覆盖镜像与 checkout 之间不相同的其他代码。

部署与回滚（在本机 checkout 中运行）：

```sh
python3 ops/admin-handover/deploy.py --deployment-dir /path/to/private/deployment
python3 ops/admin-handover/rollback.py --deployment-dir /path/to/private/deployment
```

回滚恢复原镜像、环境变量、nginx 配置，不删除新建账号和课程。只停用功能可将 Stack 环境变量开关设为 `false` 后重建应用。

## 升级与验证

后续同步 LearnHouse 更新时保留独立 router、注册入口和本目录，再针对新基础镜像构建与运行测试；不要直接使用上游 `latest` 覆盖自定义功能。原生角色和权限接口发生变化时应重新适配。

API 镜像中执行：

```sh
PYTHONPATH=/app/api /app/api/.venv/bin/python -m pytest -q /tmp/test_import.py
```

`test_import.py` 测试输入规范化、管理员与同源限制、幂等恢复和密码防回显。`verify-browser.cjs DEPLOYMENT_DIR` 使用真实网页创建一个随机临时学员，验证下载、登录、分组、权限、重复导入后删除；需要部署目录既有 Playwright 安装及 Edge。`--courses-only` 单独检查课程草稿渲染，避免重复创建测试账号。

在线验证结果见 `verification.json`。临时账号删除后，原有 3 名组织成员保持不变。导入接口不发送邮件。初次验收清理沿用原生删除接口，会尝试向合成测试地址发送账号删除通知；后续改用严格核对测试地址、标记和 ID 的 `cleanup-test-user.py` 直接清理测试数据，避免该自动通知。
