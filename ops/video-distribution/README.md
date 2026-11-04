# LearnHouse 视频分发测试部署

部署于 2026-11-05。应用、数据库、登录、上传仍由 server-ba（100.64.0.6）提供；没有修改 LearnHouse 应用源码或镜像。

浏览器 → `syyedu.toofun.fun` / 腾讯云 Lucky → 本机视频网关 → 100.64.0.4 缓存 → server-ba 原文件。

实际播放命中腾讯云缓存时，不再从家庭网络传输视频正文。网关在每次请求读取缓存前，仍向原应用发 HEAD 请求校验课程、课时和用户权限；不会缓存权限结果。应用离线时校验失败，视频也不能访问。

- 腾讯云：独立 systemd 服务 `learnhouse-video-edge`，只监听 `127.0.0.1:18887`；配置和日志位于 `/opt/learnhouse-video-edge/`，缓存最多 3GB。复用现有 nginx 二进制，不修改系统 nginx 监听。
- 100.64.0.4：原生 nginx/Windows 1.31.8；`D:\deploy\LearnHouseVideo\`，缓存最多 30GB；只监听 `100.64.0.4:18887`。防火墙和 nginx 仅允许腾讯云 Tailnet IP，另需独立随机请求密钥。未安装 Docker，也未暴露现有共享目录。
- 计划任务 `LearnHouseVideo-Origin` 以 SYSTEM 运行 nginx，配置开机启动和每两分钟重试；正在运行时忽略重复启动。Tailscale 地址尚未出现时启动可能失败，后续自动重试。Windows 整机重启后的恢复尚未实测。
- 两级缓存都按 URI 和 4MB Range 分片保存，忽略原响应的浏览器缓存指令。它们是受保护的服务器缓存，公网始终先经过原生 RBAC。浏览器收到 `private, no-store`。只缓存 `/api/v1/stream/video/`、`/api/v1/stream/block/`，其他请求直接透传。
- 文件 UUID 变化会自然产生新缓存；删除、取消发布或收紧权限后，原生 HEAD 校验会阻止访问已有缓存。不要原地覆盖同名视频文件；应使用正常上传生成新 UUID。
- `.4` 暂时不可用时，腾讯云已有缓存仍可用；新的缓存缺失请求可回退到 server-ba。回退意味着再次占用家庭带宽。缓存不是备份，原始文件仍在 `D:\deploy\LearnHouse\content`。

## 维护和预热

私密配置只在部署工作目录 `video-distribution/` 中，不提交 Git。请求密钥由 `render.py` 创建或复用，渲染后的 `*.private.conf` 仅供部署。Windows 压缩包来源为 [nginx 官方下载](https://nginx.org/en/download.html)，SHA-256 固定在安装脚本中。Windows 版本属于测试适用方案，参见[官方限制](https://nginx.org/en/docs/windows.html)。

新上传的视频首次播放仍需从家庭网络回源。集体上课前应先预热；预热脚本逐段校验长度、范围并重试，最后比较源站和腾讯云的完整 SHA-256：

```bash
python3 ops/video-distribution/warm.py --deployment-dir "$DEPLOY_DIR" \
  --path /api/v1/stream/video/ORG/COURSE/ACTIVITY/FILENAME.mp4
```

私有课程增加 `--private`，脚本从现有本机私密环境读取管理员账号，临时登录。JWT 仅通过 SSH 标准输入传递，不保存到云端，也不出现在参数和日志中。已知原文件哈希时增加 `--expected-sha256 HASH`。

云端运维：`systemctl status|reload|restart learnhouse-video-edge`。先执行 `nginx -t -p /opt/learnhouse-video-edge/ -c nginx.conf` 再 reload。专用日志已配置轮转。

Windows 修改配置后，以管理员执行 `origin-control.ps1 -Action reload`。它通过一次性 SYSTEM 计划任务发送信号；直接从 SSH 用户运行 `nginx -s reload` 无权操作 SYSTEM 的控制事件。停止用 `-Action stop`，启动用 `Start-ScheduledTask -TaskName LearnHouseVideo-Origin`。永久停用前先禁用此计划任务，避免下一次周期重新启动。日志位于 `nginx\logs`；长期使用需定期归档这些日志。

## 初次安装或迁移到 100.64.0.8

1. 确认新主机在线、D 盘空间和有效带宽，原主机继续服务。
2. `render.py --deployment-dir "$DEPLOY_DIR" --origin-ip 100.64.0.8` 复用密钥并渲染新 IP。它只生成本地文件，不改变在线路由。
3. 将官方 ZIP、渲染的 `origin.nginx.private.conf`、`install-origin.ps1`、`origin-control.ps1` 放入新主机全新 `D:\deploy\LearnHouseVideo\`，运行安装脚本。ZIP 应仍为脚本固定的 1.31.8；更新版本前需重新核验散列。
4. 新主机按需重新缓存即可；如需复制旧缓存，只复制已经完成写入的缓存文件并保持目录结构。原文件无需迁移，仍由 server-ba 提供。不要复制业务共享目录。
5. 先执行 `warm.py --origin-ip 100.64.0.8 ...` 验证新源站。将渲染的 edge 配置送到云端，测试配置并 reload。已有腾讯云缓存无需清空，公网域名和 Lucky 路由无需变更。
6. 验证播放和 Range，再停用旧主机的任务。回退只需将网关配置中的源站 IP 改回 `.4` 后 reload，旧缓存保留。

## 回退为原家庭服务器直供

先建立 SSH 隧道，将本机 `19888` 转发到云端 `127.0.0.1:16601`，然后：

```bash
python3 ops/video-distribution/route.py --deployment-dir "$DEPLOY_DIR" \
  --target home --tunnel-port 19888
```

恢复分发则用 `--target edge`。脚本每次读取最新完整 Lucky 规则，使用 `ExpectedVersion`，只改变 LearnHouse 子规则的 `Locations`，保留其他站点、WAF 和超时配置。每次变更前后均保存私密快照。公共管理入口的 WAF 无需放宽。

## 已完成的验收

- 277,382,743 字节视频：原文件、`.4` 返回正文、腾讯云返回正文的 SHA-256 一致。
- 原生 Edge 浏览器实际播放，元数据 1920×882、2597.714 秒；播放推进到 2 秒以上，跳到 1800 秒后继续播放；媒体请求 206 且缓存 HIT。
- 公网文件头部、尾部 Range 206、HEAD 200，均命中缓存。
- 临时私有课程：匿名拒绝、管理员填充及命中缓存、Cookie 播放 Range、缓存后匿名仍拒绝；删除课程后管理员也不能再读缓存。测试课程已删除。
- 原生登录/创建/上传/删除接口、应用健康和 Headscale 健康正常。未更改其他 Lucky 子规则。
- `.4` 的专用 nginx 进程停止并通过计划任务重新启动后，源站和公网视频仍命中磁盘缓存；没有重启 Windows 整机。
- 未进行 200 人并发观看测试，现有 300Mbps 公网规格仍依据用户提供的信息。缓存空间也会影响多课程同时观看时的回源量。

证据保存在部署工作目录的 `video-distribution/`，包括 `warm-verification.json`、`browser-verification.json`、`public-verification.json`、`acl-verification.json` 和页面截图。缓存依赖 [nginx 分片模块](https://nginx.org/en/docs/http/ngx_http_slice_module.html)，权限校验使用 [auth_request 模块](https://nginx.org/en/docs/http/ngx_http_auth_request_module.html)。
