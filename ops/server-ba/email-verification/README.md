# server-ba 邮箱验证定制

LearnHouse 自托管实例可通过独立开关要求新注册账号验证邮箱。部署模式仍是自托管，沿用原有验证页面、Redis 单次令牌、重发限流和 SMTP 服务。

## 行为

- `LEARNHOUSE_REQUIRE_EMAIL_VERIFICATION=true`：邮箱密码注册后发送验证邮件，验证前拒绝密码登录及申请邮件登录链接。
- `LEARNHOUSE_EMAIL_VERIFICATION_REQUIRED_SINCE`：UTC ISO 时间。仅该时间及之后创建的账号要求验证，保留已有管理员的登录能力；不会把旧账号标记为已经验证。
- SaaS 原有行为保持不变；OAuth 已验证账号继续沿用原有流程。
- 验证令牌有效期一小时。验证后按原有规则签发会话，原有 MFA 检查保留。

## 当前部署

- 主机：server-ba，WSL Ubuntu-26.10 原生 Docker。
- Portainer：`learnhouse` Stack，ID 17，Endpoint 1。
- 网站：`https://syyedu.toofun.fun`。
- 发信地址：`noreply@toofun.fun`；腾讯企业邮 SMTP，`smtp.exmail.qq.com:465`，TLS。
- 内容挂载：`D:\deploy\LearnHouse\content` → `/app/api/content`。
- 镜像：`local/learnhouse:20261105-email-verification-v1`。

SMTP 密码、JWT、数据库连接和 Portainer 凭据留在部署目录的私有配置中。Git 中只记录源码、无密钥的 Compose 模板和部署工具。`compose.yaml` 的环境变量需要由 Portainer Stack 环境变量提供。

## 发信域名认证

腾讯企业邮的收信 MX 记录只解决收信路由。发往 Gmail 等外部邮箱前，需要在域名的公网 DNS 中配置发信认证。当前腾讯企业邮 SPF 记录为：

| 域名 | 主机记录 | 类型 | 线路 | 记录值 |
| --- | --- | --- | --- | --- |
| `toofun.fun` | `@` | `TXT` | 默认 | `v=spf1 include:spf.mail.qq.com ~all` |

保留现有 MX 记录；同一个域名只维护一条 `v=spf1` 策略。若以后增加其他发信服务，应合并授权来源，避免添加相互冲突的多条 SPF。DKIM 的选择器和公钥以腾讯企业邮管理后台给出的域名配置为准。

保存 DNS 后先查询公网 TXT，确认 SPF 已生效，再通过注册页或登录页重发验证邮件。若 Gmail 仍收不到，检查垃圾邮件、发件邮箱中的退信及服务商投递日志。腾讯 SMTP 接受邮件、注册接口返回成功和 Gmail 收件箱实际收到邮件是不同的验收步骤。

参考：[DNSPod TXT 设置](https://docs.dnspod.cn/dns/help-txt/)、[腾讯 SPF 示例](https://intl.cloud.tencent.com/document/product/1097/44886)、[Gmail 发件人要求](https://support.google.com/mail/answer/81126?hl=zh-Hans)。

## 构建

当前运行的官方镜像与 Git 基线在部分无关接口上存在版本差异。`build.py` 从准确的官方镜像摘要提取两个目标文件，核对 SHA-256，再应用 `runtime.patch` 并复制策略模块，避免顺带升级其他接口。构建需要 Python 3、Git 和 Docker；无需发信凭据。

在服务器上的本仓库根目录执行：

```sh
python3 ops/server-ba/email-verification/build.py --check
python3 ops/server-ba/email-verification/build.py
```

`--check` 只准备和校验构建内容。部署时使用原先运行的镜像摘要：

```text
ghcr.io/learnhouse/app@sha256:9dd05e16fe1aecf5b668dc4d415c38bf1fd20274a927b50bc51a98388b3639bb
```

## 部署与回退

macOS 部署工作目录为 `/Users/svipba/Documents/Codex/2026-11-04/learnhouse-deploy`。目录中已有私有 `portainer.py`、凭据、`config/` 和备份。部署工具通过 Portainer 更新 Stack，保留已有环境变量，不拉取其他镜像。

```sh
python3 ops/server-ba/email-verification/deploy.py --deployment-dir /Users/svipba/Documents/Codex/2026-11-04/learnhouse-deploy
python3 ops/server-ba/email-verification/rollback.py --deployment-dir /Users/svipba/Documents/Codex/2026-11-04/learnhouse-deploy
```

首次启用前，数据库备份及 Stack 快照保存在部署目录 `email-verification/`。回退恢复之前的镜像、Compose 和环境变量；本变更无数据库结构迁移。新建未验证账号在回退后会恢复官方自托管版本原有的登录行为。

## 验证

本次在无网络隔离容器中运行注册、验证服务和认证相关测试：原有相关测试 93 项及新增策略测试 14 项通过。原有测试夹具有 18 条异步调用警告。

线上通过实际 `/api/signup` 和 `/api/auth/*` 路径检查：注册账号保持未验证、注册发信、验证邮件重发、未验证登录拒绝、错误令牌拒绝、有效令牌验证、Cookie 自动登录、令牌不可重复使用、验证后密码登录、旧管理员登录。测试仅向自己的发信邮箱投递，测试账号已删除。SMTP 接受邮件不等于已确认收件箱投递。

## 同步 LearnHouse 更新

保留官方仓库为 `upstream`，个人 fork 为 `origin`，定制位于 `codex/selfhost-email-verification` 分支。不要直接在运行容器里修改文件。

```sh
git fetch upstream
git switch codex/selfhost-email-verification
git merge upstream/dev
```

初始仓库是浅克隆；需要完整历史时执行 `git fetch --unshallow upstream`。有冲突时集中检查注册、密码登录、邮件登录和验证接口。先更新构建基线、`runtime.patch` 和 SHA-256 清单，再构建、测试和部署；更新镜像标签后保留旧镜像及 Stack 快照。每次同步都应检查官方是否已原生支持自托管邮箱验证，若已支持，可移除本地补丁并改用官方配置。
