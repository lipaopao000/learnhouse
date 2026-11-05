# 用户名账号、后续绑定邮箱与管理员重置密码

## 管理员使用

入口仍是 <https://syyedu.toofun.fun/dash/users/import>。

- CSV 填写姓名、用户名、角色、分组；**邮箱可以留空**。不填邮箱时用户名必填，且必须唯一。角色支持学员、讲师，管理员权限单独授予。
- 创建后下载每人的独立随机初始密码，分别交付。用户使用**用户名 + 密码**登录；绑定邮箱后也可以使用邮箱登录。
- 账号直接启用，不发送开通邮件。用户首次登录后自行修改初始密码，目前不强制改密。
- 页面下方“管理员重置密码”：按姓名、用户名或邮箱查找，核实本人身份，输入管理员自己的当前密码确认，下载本次新密码并单独交付。
- 重置不发送邮件，结束目标用户所有旧登录会话，清除该账号的密码错误锁定；保留学习记录、角色、分组和 MFA 双重验证。
- 只有当前组织的管理员/维护者可以进入。普通组织管理员不能重置超级管理员、Admin/Maintainer 或跨组织共享账号；超级管理员在目标属于当前组织时可管理这些账号。自己的密码在账号设置修改。

## 用户使用

登录：<https://syyedu.toofun.fun/login>；账号设置：<https://syyedu.toofun.fun/account/general>。

不绑定邮箱也能正常登录、学习。需要邮箱时，在账号设置中填写自己的邮箱和当前密码，接收并输入 6 位验证码；验证成功才写入账号，之后重新登录。验证码 10 分钟有效，发送和尝试次数有限制。换绑已有邮箱还会向原地址发出变更通知。

忘记密码：未绑定邮箱的账号请联系教学管理员核实后重置；已绑定邮箱的账号也可走原有邮件找回流程。MFA 仍按原生流程要求验证，管理员重置登录密码不会清除 MFA。

公开自助注册继续要求邮箱并沿用原有邮箱验证策略。本变更只允许**管理员预建**无邮箱账号；没有开放匿名用户名注册。

姓名、姓氏（选填）、简介及头像在同一账号页编辑，沿用原生资料与头像接口；无邮箱和未填写姓氏不会阻止保存。个人主页布局与原生其他登录方式仍可通过页面链接访问。新增页面沿用同域 HttpOnly Cookie，禁止第三方脚本及页面缓存；密码不保存到 localStorage。

## 页面设计

新增页面沿用现有 LearnHouse 的 Wix Madefor Text 字体、黑白灰配色、黑色主按钮、浅灰边框及轻阴影；复用当前组织 ICU Logo。登录页保持原有左右分栏与黑色品牌面板；账号设置保持顶部学习导航和左侧账户菜单；批量导入与重置页保持后台黑色侧栏、面包屑和用户管理标签页。手机端收起侧栏并调整表单、表格滚动，不另设品牌色。

页面公开资源位于 `ops/admin-handover/web`；`branding.js` 从当前组织读取 Logo 与名称，`publish_ui.py` 备份后单独更新静态文件，无需重启应用。字体引用固定前端中的原有字体资产，上游前端重建后应核对该资产路径。

## 实现

- `src/db/users.py`：仅数据库 User 接受空字符串邮箱；公开 `UserCreate` 仍使用 `EmailStr` 验证。数据库列仍为原有非空字符串，没有用虚构邮箱替代。
- `src/security/account_identity.py`：登录凭据可按用户名解析；未绑定邮箱的会话使用稳定的 `user_uuid` 作为 JWT subject。旧邮箱 subject 继续有效；Token 解析不会把用户名当作签名身份。
- `src/routers/orgs/user_import.py`：允许邮箱留空；按非空邮箱和唯一用户名识别重复，避免多个空邮箱账号混淆。未绑定邮箱保持 `email_verified=false`；自托管验证策略只豁免有管理员创建标记的无邮箱账号。
- `src/routers/account_access.py`：本人改密、请求/验证邮箱绑定、管理员查找和重置。本人操作要当前密码，管理员操作要管理员当前密码；同源校验、权限校验、敏感错误脱敏和 Redis 限流。
- 邮箱只在验证码通过后更新，Redis 中只存验证码散列、随机盐、目标邮箱和密码版本，不存验证码明文。改密后旧的待绑定验证码失效。
- 密码变更切点设为下一整秒，提交后等待跨过切点再响应，保证同一秒内签发的旧 Token 也被撤销，立即使用新密码登录则正常。已开始的旧 MFA challenge 同样检查密码版本。
- 新密码仅由浏览器生成、后端散列；管理员重置的操作 ID 支持重试恢复，审计只存操作者、操作 ID、时间。
- `send_email` 对空收件地址直接跳过，避免对无邮箱账号触发通知投递。
- 首页账号菜单指向的 `/account/general` 现在是新账号页面；`/account/details` 重定向到同一账号页的资料区域，避免原生表单必填邮箱/姓氏造成阻塞，`/account/security` 保留原生 MFA，`/email-login` 保留原生其他登录方式。

## 部署与升级

当前镜像 `local/learnhouse:20261105-username-accounts-v4`；基于已部署的 v3，保留 SMTP、邮箱验证、ICU 草稿、视频缓存及 Tinybird。仅更新 Portainer Stack 17 的应用、网页和 nginx 配置，不升级上游其他接口。

开关 `LEARNHOUSE_USERNAME_ACCOUNTS_ENABLED=true`，同时保留 `LEARNHOUSE_ADMIN_USER_IMPORT_ENABLED=true`。

新增两个 PostgreSQL 唯一索引：`lh_selfhost_user_email_ci`（仅非空邮箱，大小写不敏感）和 `lh_selfhost_user_username`（仅非空用户名）。先备份，已有重复时索引创建失败并停止部署。多个空邮箱可共存；邮箱绑定和原生注册的并发冲突不能创建重复身份。

`patch_runtime.py` 对实际 v3 的 9 个文件做窄范围补丁，`runtime-hashes.json` 固定输入和输出 SHA-256；其余新增文件从 checkout 复制。官方镜像与 checkout 原本存在部分版本差异，构建不会用 checkout 的整份旧文件覆盖镜像。

```sh
# server-ba WSL，准备好的 checkout 根目录
python3 ops/username-accounts/build.py

# 本机，首次从 v3 升级
python3 ops/username-accounts/deploy.py --deployment-dir /path/to/private/deployment

# 后续经测试的 v4 重建，保持现有数据与配置
python3 ops/username-accounts/redeploy.py --deployment-dir /path/to/private/deployment
```

备份位于服务器 `D:\deploy\LearnHouse\backups\username-accounts-v4`，本机私有部署目录 `handover/releases/20261105-username-accounts-v4`。保存原数据库、nginx、静态网页及 Stack/环境快照。

`rollback.py` 恢复 v3 应用与网页并保留数据、索引。**v3 无法登录新增的无邮箱账号**；这些账号需恢复 v4 后才能继续使用。不要为回退而删除人员或把未验证邮箱标为已验证。

同步上游时需重新核对 User 模型、身份解析、MFA、注册/验证策略和新迁移。上游如果增加邮箱全量唯一约束，需要保留对空邮箱的正确处理。不要直接切换上游 `latest`。

## 验证

隔离容器中运行 13 项账号/导入测试，另有 75 项原生与用户名失败登录回归；覆盖旧邮箱登录、公开邮箱验证、MFA、Token 类型、无邮箱身份与密码错误计数。使用 `--asyncio-mode=auto`，数据库为内存 SQLite，网络关闭。

在线脚本 `verify-browser.cjs DEPLOYMENT_DIR` 仅创建两个带严格测试前缀的账号，在真实网页检查 CSV、用户名登录、独立身份、刷新、管理员重置下载、旧密码及会话失效、本人改密、MFA 和已验证绑定邮箱登录，最后用 `fixture.py` 清理。初次绑定的邮件发送在隔离测试用替身验证，线上确认使用私有测试夹具；**不向真实或测试邮箱发信**。结果见 `verification.json`。

兼容性补查：原生资料表单原本要求邮箱和姓氏，已改为统一资料入口，并实测空邮箱、空姓氏下姓名/简介保存和头像上传；用户 ID 保持不变。验证脚本的私有夹具通过临时文件传输，避开 Windows 命令行长度限制；清理时同时删除测试账号头像文件。
