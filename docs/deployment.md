# 生产部署指南

面向商业化部署的最小可用方案：单机 + WSGI + 反向代理，或直接容器化。
文中命令以 Linux 为例，Windows 差异单独标注。

## 1. 组件与端口

| 组件 | 说明 |
|---|---|
| Django 应用 | API（`/api/*`）、TDesign 控制台（`/console/`）、网页远控（`/web/`）、Django Admin（`/admin/`） |
| 数据库 | 默认 SQLite（自动 WAL）；生产推荐 Postgres，其次 MySQL |
| 缓存 | 默认进程内；多进程可用数据库缓存或 Redis |
| 历史录像目录 | 默认 `records/`，可用 `RECORD_ROOT` 指定 |
| 端口 | 默认 `21114`（RustDesk API 默认端口），建议由 nginx 暴露 443 |

将客户端的 `api-server` 配为客户端所在网络可达的 HTTPS 地址，例如 `https://rd.example.com`。

## 2. 安装

```bash
cd /opt/rustdesk-api
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-prod.txt      # gunicorn + redis 等生产依赖
```

Windows：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-prod.txt      # 会装 waitress
```

## 2.1 免安装可执行包（Linux / Windows）

GitHub Releases 提供 PyInstaller 免安装包（目录形式，内含可执行文件与运行库），无需 Python、Docker 或数据库：

| 平台 | 文件 | 运行 |
| --- | --- | --- |
| Linux x86_64 | `rustdesk-api-server-<版本>-linux-x86_64.tar.gz` | `tar -xzf ... && cd rustdesk-api-server && ./rustdesk-api-server` |
| Windows x64 | `rustdesk-api-server-<版本>-windows-x64.zip` | 解压后进入目录，双击 `rustdesk-api-server.exe` |

- 数据目录：可执行文件旁的 `data/`（`db/db.sqlite3`、`records/`、`logs/`），可用 `DATA_DIR` 覆盖。
- 首次启动自动生成 `data/secret_key`；默认监听 `0.0.0.0:21114`，可用 `PORT` 覆盖。
- 默认 `ALLOWED_HOSTS=*`，可通过同目录 `.env` 收紧；修改配置参考[配置](#3-配置)。
- 升级：替换可执行文件，保留 `data/`，启动时自动迁移。
- 构建：打 `v*` tag 触发 `.github/workflows/standalone.yml`；也可在 Actions 页面手动运行。

## 3. 配置

复制模板并修改：

```bash
cp .env.example .env
python -c "import secrets;print('SECRET_KEY='+secrets.token_urlsafe(50))"
```

应用启动时会自动读取项目根目录的 `.env`（已存在的系统环境变量优先）。
完整变量见 `.env.example`，常用项：

| 变量 | 生产建议 | 说明 |
|---|---|---|
| `DEBUG` | `0` | 关闭调试，避免泄露堆栈 |
| `SECRET_KEY` | 至少 50 个随机字符 | `DEBUG=0` 时启动必填，缺失或使用旧默认值会直接拒绝启动 |
| `ALLOWED_HOSTS` | `rd.example.com,127.0.0.1` | 允许的域名与本机健康探测地址 |
| `CSRF_TRUSTED_ORIGINS` | `https://rd.example.com` | 控制台/后台的来源 |
| `HTTPS` | `1` | 开启 Secure Cookie、HSTS、SSL 跳转 |
| `BEHIND_PROXY` | `1` | 信任外层 nginx 的 `X-Forwarded-Proto` 与 `X-Forwarded-For`（限流与健康检查按可信代理跳数取真实客户端 IP） |
| `TRUSTED_PROXY_COUNT` | 留空 | 可选：多层代理（如 CDN + nginx）时显式指定可信代理跳数；留空自动推导 |
| `ID_SERVER` | 留空或域名 | 网页远控信令服务器；Docker 内置 nginx 下留空自动按请求地址推导（纯 IP/非默认端口走同源 `ws(s)://<host>/ws/id`） |
| `RELAY_SERVER` | 留空 | 网页远控中继服务器；通常留空由 hbbs 下发 |
| `API_SERVER` | 留空 | 网页远控调用的 API 地址；留空默认当前访问地址 |
| `RUSTDESK_KEY` | hbbs 公钥 | `id_ed25519.pub` 内容，网页远控连接必填 |
| `WEBCLIENT_ROOT` | `/app/webroot/web` | 免安装包 / 直连模式由 Django 提供 `/web/` 时的静态目录；Docker 内置 nginx 使用 `WEBROOT` |
| `WEBCLIENT_AUTO_INSTALL` | `1` | 容器启动时自动解压内置网页远控包到 `WEBROOT`；升级用 `WEBCLIENT_FORCE_UPDATE=1` |
| `HBBS_WS` / `HBBR_WS` | `host.docker.internal:21118/21119` | 容器内置 nginx 代理 `/ws/id` 与 `/ws/relay` 的上游地址 |
| `CACHE_URL` | `redis://127.0.0.1:6379/0` | 多进程时限流需要（有 Redis 时） |
| `CACHE_BACKEND` | `db` | 没有 Redis 时的共享缓存；Docker 入口脚本会自动建 `rustdesk_cache` 表，裸机部署请手动执行 `python manage.py createcachetable`（免安装包已内置） |
| `HEALTH_TOKEN` | 随机串 | 远端监控读取健康检查详情时带的 `X-Health-Token` |
| `ALLOW_REGISTRATION` | `0` | 关闭自助注册，由管理员建号 |
| `WEB_SETUP_TOKEN` | 留空 | 如需网页初始化，单独生成至少 32 字符的随机密钥，完成后清除 |
| `LOGIN_MAX_ATTEMPTS` | `8` | 窗口内失败次数上限 |
| `LOGIN_LOCK_SECONDS` | `300` | 锁定时长（秒） |
| `TOKEN_TTL_SECONDS` | `2592000` | 客户端令牌有效期（30 天）；有效令牌随认证请求续期 |
| `REGISTER_MAX_PER_HOUR` | `10` | 每个 IP 每小时注册上限（开启注册时生效） |
| `SETUP_MAX_PER_HOUR` | `10` | 每个 IP 每小时初始化尝试上限 |
| `HEARTBEAT_TOKEN_REFRESH_SECONDS` | `86400` | 剩余不足该秒数时续期，避免频繁写库 |
| `DATABASE_TYPE` | `SQLITE`/`MYSQL`/`POSTGRES` | 连接信息用 `DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT`（兼容旧 `MYSQL_*`） |
| `RECORD_ROOT` | `/var/lib/rustdesk-api/records` | 历史录像归档目录 |
| `LOG_DIR` | `/var/log/rustdesk-api` | 日志目录，10MB 轮转保留 5 份 |

> 数据库驱动：Docker 镜像已内置 `psycopg[binary]`，PostgreSQL 开箱即用。MySQL 需要 `mysqlclient`，
> 依赖 `default-libmysqlclient-dev`、`pkg-config`、`build-essential` 编译，当前镜像未内置；
> 用 MySQL 时请基于 `deploy/requirements-docker.txt` 自行扩展镜像。

在 `.env` 写入生成的密钥。可通过 `python manage.py check --deploy` 检查 Django 配置、通配域名和网页初始化开关。

## 4. 初始化

```bash
python manage.py migrate
python manage.py ensure_admin
npm --prefix frontend ci
npm --prefix frontend run build
python manage.py collectstatic --noinput
```

`ensure_admin` 在交互终端读取密码；非交互运行（Docker、CI）会生成随机密码并打印一次，部署者登录后应立即修改。自动化部署也可通过 `SMOKE_ADMIN_USER`、`SMOKE_ADMIN_PASSWORD` 注入专用凭据。
裸机运行时需要 Node.js 22 生成 `static/console/`。容器镜像在构建时完成这一步。

## 5. 启动

### Linux（gunicorn + systemd）

```bash
gunicorn rustdesk_server_api.wsgi:application \
  --bind 127.0.0.1:21114 --workers 4 --timeout 60 --access-logfile -
```

`/etc/systemd/system/rustdesk-api.service`：

```ini
[Unit]
Description=RustDesk API Server
After=network.target redis-server.service

[Service]
Type=simple
User=rustdesk
WorkingDirectory=/opt/rustdesk-api
EnvironmentFile=/opt/rustdesk-api/.env
ExecStart=/opt/rustdesk-api/.venv/bin/gunicorn rustdesk_server_api.wsgi:application \
  --bind 127.0.0.1:21114 --workers 4 --timeout 60
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### Windows（waitress）

```powershell
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:21114 --threads=8 rustdesk_server_api.wsgi:application
```

长期运行建议用 NSSM 注册为服务，或使用任务计划程序开机启动；
`RECORD_ROOT`、`LOG_DIR` 指向有写权限的目录。

### Docker

容器方式见根目录 README。镜像内置 nginx，`21114` 一个端口同时提供 API、控制台、静态文件和网页远控；外部访问仍建议由宿主机 HTTPS 反向代理转发。

镜像默认以 root 运行，bind mount 的 `data/` 目录无需额外 `chown`。如果你自行在编排里改为非 root 用户，需要先把 `data/` 交给对应的 uid，否则迁移会因无写权限失败。

用本仓库 `Dockerfile` 构建的镜像已内置 nginx 和网页远控预构建包（`deploy/web/rustdesk-web-1.5.3.tar.gz`）：`entrypoint.sh` 首次启动解压到 `/app/webroot`，容器内 nginx 直接用 `21114` 提供 `/console/`、`/web/`、`/api/` 与 `/ws/*`，并通过 `auth_request /_web_auth` 校验控制台会话（共享登录、双向退出与实时断连）。宿主机只需要把 `21114` 反代到 443，不必再单独配置 `/web/` 静态站点。`HBBS_WS`/`HBBR_WS` 指向 hbbs/hbbr（compose 默认 `host.docker.internal:21118/21119`）。升级网页包时设 `WEBCLIENT_FORCE_UPDATE=1` 重启一次；详细配置见 [webclient.md](webclient.md)。

设备重装或系统重装后 UUID 会变化。所有已登记设备更换 UUID 都需要管理员确认，普通后台上报不会直接改写身份：

1. 在 Django 后台「设备」列表选中该设备，执行「允许所选设备重新登记（10 分钟）」。
2. 客户端再次上报系统信息时，服务端只把新 UUID 记为“待确认”，仍返回 `ID_NOT_FOUND`，原身份和在线状态保持不变。
3. 刷新设备列表，核对「待确认的新 UUID」与设备实际身份一致后，点击「待确认身份」列的「核对并确认…」，在确认页提交。
4. 设备随后重新上报即可恢复 `SYSINFO_UPDATED` 与在线状态；确认成功时窗口和待确认状态会一并清除。

如果确认页打开后候选又被其他请求替换，提交会被拒绝，需要刷新后重新核对。带有效 Bearer 且有设备管理权限的请求可以直接完成 UUID 更新，不需要走窗口。


## 6. Nginx 反向代理

```nginx
server {
    listen 443 ssl http2;
    server_name rd.example.com;

    ssl_certificate     /etc/letsencrypt/live/rd.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/rd.example.com/privkey.pem;

    client_max_body_size 12m;

    location /static/ {
        alias /opt/rustdesk-api/static/;
        expires 7d;
    }

    location ^~ /ws/ {
        proxy_pass         http://127.0.0.1:21114;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade           $http_upgrade;
        proxy_set_header   Connection        "upgrade";
        proxy_set_header   Host              $http_host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering    off;
    }

    location / {
        proxy_pass         http://127.0.0.1:21114;
        proxy_set_header   Host              $http_host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;  # BEHIND_PROXY=1 时按可信代理跳数从右侧取真实客户端 IP
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

`/console/` 是 hash 路由的单页应用，不需要额外的 `try_files` 规则；
如果改成了 history 路由，再加 `try_files $uri /console/index.html`。

## 7. 健康检查与监控

```bash
# 公网只返回 {"status":"ok"}；本机或带 HEALTH_TOKEN 才返回版本/数据库/缓存详情
curl -fsS https://rd.example.com/api/health
# {"status":"ok","version":"v1.2.0","database":"ok","cache":"ok",
#  "cache_backend":"redis","debug":false}
```

- 数据库异常 → HTTP 503，`status=error`，应触发告警；
- 缓存异常 → HTTP 200，`status=degraded`，提示 Redis 掉线但不摘流量；
- 建议负载均衡每 30 秒探活一次，并监控 `logs/app.log` 的 5xx 与登录 429。

### 部署自检

```bash
python manage.py doctor          # 密钥/域名/DEBUG/缓存/数据库/目录/控制台/账号逐项检查
python manage.py doctor --json   # 机器可读，适合接监控或发布流水线
```

任一项 FAIL 时退出码为 1，可直接作为发布门禁；WARN 只提示不阻断。

## 8. 备份与恢复

| 数据 | 方式 |
|---|---|
| SQLite | 停机或 `sqlite3 db/db.sqlite3 ".backup '/backup/db-$(date +%F).sqlite3'"` |
| MySQL | `mysqldump --single-transaction rustdesk > backup.sql` |
| 录像 | 备份 `RECORD_ROOT`（可按保留期清理） |
| 配置 | `.env`、nginx 配置、证书 |

恢复：先恢复数据库，再 `migrate`，最后放回录像目录；跨版本恢复前先读升级说明。

## 9. 升级流程

```bash
git pull
. .venv/bin/activate && pip install -r requirements.txt -r requirements-prod.txt
python manage.py migrate
npm --prefix frontend ci
npm --prefix frontend run build
python manage.py collectstatic --noinput
python manage.py doctor          # 升级后自检，FAIL 则不重启
systemctl restart rustdesk-api
curl -fsS https://rd.example.com/api/health
```

升级前先备份数据库并检查 `SECRET_KEY`。迁移会删除所有旧版 32 位令牌，所有客户端需要重新登录一次；使用过旧版初始密码的管理员需轮换密码。

## 10. 安全清单

- [ ] `SECRET_KEY` 已替换，且不进入版本库
- [ ] `DEBUG=0`，`ALLOWED_HOSTS` 为真实域名
- [ ] 全站 HTTPS，`HTTPS=1`、`BEHIND_PROXY=1`
- [ ] 多进程部署已配共享缓存（`CACHE_URL` 或 `CACHE_BACKEND=db`）
- [ ] 关闭自助注册（`ALLOW_REGISTRATION=0`），管理员用强密码
- [ ] `/admin/`、`/console/` 限制来源 IP 或加 VPN
- [ ] 录像目录磁盘配额与保留策略
- [ ] 日志接入集中采集，保留 ≥30 天
- [ ] 定期备份数据库与录像，做过恢复演练
- [ ] 依赖定期升级（`pip list --outdated`、`npm audit`）

## 11. 多进程 / 多实例注意事项

- 登录节流依赖缓存：LocMem 只在单进程内有效，**gunicorn 多 worker 必须配 Redis**，
  否则每个 worker 各算各的，等于没有节流。
- SQLite 只适合单机单写者；高并发或需要多实例时切 MySQL。
- 录像写入本地磁盘，多实例部署需要共享存储（NFS/对象存储）或按设备固定路由。
- 会话存数据库（默认），多实例共享同一数据库即可。

## 12. 常见问题

| 现象 | 原因与处理 |
|---|---|
| `DEBUG=0` 后页面无样式 | 没跑 `collectstatic`，或 nginx 没配 `/static/` |
| 控制台刷新 404 | 只支持 `/console/`，不要直接访问 `/console/index.html` |
| 登录一直 429 | 触发了节流，等待 `LOGIN_LOCK_SECONDS`；确认 `CACHE_URL` 正常 |
| 上传录像 413 | 单块超过 8MB 或 nginx `client_max_body_size` 太小 |
| 健康检查 degraded | Redis 不可用，检查 `CACHE_URL` 与 redis 服务 |
| CSRF 403 | `CSRF_TRUSTED_ORIGINS` 没包含实际访问地址（含协议与端口） |
| 客户端心跳 404/500 | `api-server` 地址要指向本服务根路径，且公网可达 |

## 13. 容量与压测

### 压测方法

服务启动后执行（会创建临时账号，跑完自动删除）：

```bash
python manage.py bench_api --threads 16 --seconds 8 --base http://127.0.0.1:21114
```

### 本机实测（单进程 runserver + SQLite，16 并发；不同机器约 700–900 req/s）

| 场景 | 吞吐 | p50 | p95 |
|---|---|---|---|
| `/api/currentUser`（纯读） | 765–826 req/s | 19–20ms | 24–26ms |
| 心跳（优化前，每次 2 条 UPDATE） | 8.2 req/s | 238ms | 8.3s，9 个 500 |
| 心跳（优化后，常态零写入） | 806–882 req/s | 18–19ms | 22–24ms |

### 心跳写放大控制

- 设备在线时间戳：最多每 `HEARTBEAT_DEVICE_TOUCH_SECONDS`（默认 120 秒）写一次；
  「在线」判定用 `DEVICE_ONLINE_SECONDS`（默认 300 秒），必须明显大于写库间隔，否则设备会在两次写库之间闪成离线；
- token 续期：剩余有效期不足 `HEARTBEAT_TOKEN_REFRESH_SECONDS`（默认 86400 秒，即 1 天）才写；
- 综合下来单台设备约 **10 分钟 1 次写库**，而不是每次心跳 2 次；
- SQLite 自动开启 WAL + busy_timeout（`api/db_pragmas.py`），没有 WAL 时写锁会让心跳直接雪崩。

### 容量估算（按客户端 15 秒心跳）

| 设备数 | 心跳 QPS | 建议部署 |
|---|---|---|
| 1,000 | 67 | 单机 SQLite 足够 |
| 10,000 | 667 | Postgres + gunicorn 2–4 worker（gthread） |
| 100,000 | 6,670 | 4–8 个 API 实例 + Postgres（PgBouncer）+ Redis |

### 扩展顺序（按性价比）

1. `DATABASE_TYPE=POSTGRES`（推荐）或 `MYSQL`，连接池交给 `DB_CONN_MAX_AGE` / PgBouncer；
2. `gunicorn -c deploy/gunicorn.conf.py`（默认 gthread，worker=CPU/2、每 worker 4 线程，压测后调整）；
3. 多进程/多实例配置共享缓存：`CACHE_BACKEND=db`（零依赖）或 `CACHE_URL=redis://...`；
4. nginx upstream 挂多个实例（会话在数据库里，天然无状态）；
5. 只有在单实例 CPU 打满、且数据库已不是瓶颈时，才考虑把心跳/审计拆成 Go 服务。
