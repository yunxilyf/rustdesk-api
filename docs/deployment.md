# 生产部署指南

面向商业化部署的最小可用方案：单机 + WSGI + 反向代理，或直接容器化。
文中命令以 Linux 为例，Windows 差异单独标注。

## 1. 组件与端口

| 组件 | 说明 |
|---|---|
| Django 应用 | API（`/api/*`）、TDesign 控制台（`/console/`）、Django Admin（`/admin/`） |
| 数据库 | 默认 SQLite（自动 WAL）；生产推荐 Postgres，其次 MySQL |
| 缓存 | 默认进程内；多进程/多实例请用 Redis |
| 录像目录 | 默认 `records/`，可用 `RECORD_ROOT` 指定（仅当客户端支持上传时才会写入；1.5.x 客户端不上传，目录通常为空） |
| 端口 | 默认 `21114`（RustDesk API 默认端口），建议由 nginx 暴露 443 |

RustDesk 客户端会把 `api-server` 配成 `https://rd.example.com`，客户端用
`/api/heartbeat`、`/api/sysinfo`、`/api/audit/*` 等接口，**必须能从公网访问**；
控制台只给管理员/运维使用，建议加 IP 白名单或二次认证。

## 2. 安装

```bash
cd /opt/rustdesk-api-server
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
| `SECRET_KEY` | 随机 50 字符 | 必须替换默认值 |
| `ALLOWED_HOSTS` | `rd.example.com` | 逗号分隔，不要用 `*` |
| `CSRF_TRUSTED_ORIGINS` | `https://rd.example.com` | 控制台/后台的来源 |
| `HTTPS` | `1` | 开启 Secure Cookie、HSTS、SSL 跳转 |
| `BEHIND_PROXY` | `1` | 信任 nginx 的 `X-Forwarded-Proto` |
| `CACHE_URL` | `redis://127.0.0.1:6379/0` | 多进程时限流需要 |
| `ALLOW_REGISTRATION` | `0` | 关闭自助注册，由管理员建号 |
| `LOGIN_MAX_ATTEMPTS` | `8` | 窗口内失败次数上限 |
| `LOGIN_LOCK_SECONDS` | `300` | 锁定时长（秒） |
| `DATABASE_TYPE` | `SQLITE`/`MYSQL`/`POSTGRES` | 连接信息用 `DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT`（兼容旧 `MYSQL_*`） |
| `RECORD_ROOT` | `/var/lib/rustdesk-api/records` | 录像落盘目录；1.5.x 客户端不上传，可留空卷 |
| `LOG_DIR` | `/var/log/rustdesk-api` | 日志目录，10MB 轮转保留 5 份 |

`DEBUG=0` 时 `manage.py check` 会对默认 `SECRET_KEY`、`ALLOWED_HOSTS=*`
给出 `api.W001/W002` 告警，部署前应消除。

## 4. 初始化

```bash
python manage.py migrate
python manage.py ensure_admin                 # 默认 admin/Admin@2026
# 或自定义：SMOKE_ADMIN_USER=ops SMOKE_ADMIN_PASSWORD='...' python manage.py ensure_admin
python manage.py collectstatic --noinput      # 静态资源归集到 static/
```

控制台首次打开 `/console/` 时，如果库里没有用户，会显示「初始化控制台」，
也可以在这里创建第一个管理员（等价于 `ensure_admin`）。

前端已随仓库提供构建产物（`static/console/`）；修改前端后需重新构建：

```bash
cd frontend && npm ci && npm run build
rm -rf ../static/console && cp -r dist ../static/console
```

## 5. 启动

### Linux（gunicorn + systemd）

```bash
gunicorn rustdesk_server_api.wsgi:application \
  --bind 127.0.0.1:21114 --workers 4 --timeout 60 --access-logfile -
```

`/etc/systemd/system/rustdesk-api.service`：

```ini
[Unit]
Description=rustdesk-api-server
After=network.target redis-server.service

[Service]
Type=simple
User=rustdesk
WorkingDirectory=/opt/rustdesk-api-server
EnvironmentFile=/opt/rustdesk-api-server/.env
ExecStart=/opt/rustdesk-api-server/.venv/bin/gunicorn rustdesk_server_api.wsgi:application \
  --bind 127.0.0.1:21114 --workers 4 --timeout 60
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### Windows（waitress）

```powershell
.\.venv\Scripts\waitress-serve.exe --listen=0.0.0.0:21114 --threads=8 rustdesk_server_api.wsgi:application
```

长期运行建议用 NSSM 注册为服务，或使用任务计划程序开机启动；
`RECORD_ROOT`、`LOG_DIR` 指向有写权限的目录。

### Docker

仓库自带的 `Dockerfile`/`docker-compose.yml` 可直接构建，把 `.env` 里的变量
通过 `environment:` 注入即可；录像目录建议挂载卷持久化。

## 6. Nginx 反向代理

```nginx
server {
    listen 443 ssl http2;
    server_name rd.example.com;

    ssl_certificate     /etc/letsencrypt/live/rd.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/rd.example.com/privkey.pem;

    client_max_body_size 12m;          # 录像分片 8MB，留余量

    location /static/ {
        alias /opt/rustdesk-api-server/static/;
        expires 7d;
    }

    location / {
        proxy_pass         http://127.0.0.1:21114;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

`/console/` 是 hash 路由的单页应用，不需要额外的 `try_files` 规则；
如果改成了 history 路由，再加 `try_files $uri /console/index.html`。

## 7. 健康检查与监控

```bash
curl -fsS https://rd.example.com/api/health
# {"status":"ok","version":"v1.0.0","database":"ok","cache":"ok",
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
python manage.py collectstatic --noinput
python manage.py doctor          # 升级后自检，FAIL 则不重启
# 前端有改动时重新构建并替换 static/console
systemctl restart rustdesk-api
curl -fsS https://rd.example.com/api/health
```

升级前先备份数据库；`migrate` 只做增量，回滚需用备份。

## 10. 安全清单

- [ ] `SECRET_KEY` 已替换，且不进入版本库
- [ ] `DEBUG=0`，`ALLOWED_HOSTS` 为真实域名
- [ ] 全站 HTTPS，`HTTPS=1`、`BEHIND_PROXY=1`
- [ ] 多进程部署已配 `CACHE_URL`（Redis）
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

## 12. 容量与压测

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
- token 续期：剩余有效期不足 `HEARTBEAT_TOKEN_REFRESH_SECONDS`（默认 600 秒）才写；
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
3. `CACHE_URL=redis://...`，多进程/多实例下限流才全局准确；
4. nginx upstream 挂多个实例（会话在数据库里，天然无状态）；
5. 只有在单实例 CPU 打满、且数据库已不是瓶颈时，才考虑把心跳/审计拆成 Go 服务。
