# 测试与验收

测试分为两层，随仓库分发；CI 在每次推送时执行。

| 层 | 内容 | 入口 | 用例数 |
| --- | --- | --- | --- |
| L1 单元/集成 | Django test runner：客户端契约、控制台 API、权限隔离、安全边界、CSRF、生产配置 | `manage.py test api.tests` | 117 |
| L2 浏览器 E2E | Playwright：初始化/登录 → 8 个菜单 → 退出，零 JS 错误 | `e2e/console_e2e.js` | 24 |

## 运行

```bash
# L1
./.venv-audit/Scripts/python.exe manage.py test api.tests -v 2

# L2（需先启动服务）
./.venv-audit/Scripts/python.exe manage.py runserver 127.0.0.1:21114 --noreload
npm i playwright-core                 # 若未安装
SMOKE_BASE=http://127.0.0.1:21114 NODE_PATH=./node_modules node e2e/console_e2e.js
```

E2E 默认使用本机 Chrome：`%LOCALAPPDATA%\\ms-playwright\\chromium-1248\\chrome-win64\\chrome.exe`，可用 `CHROME_PATH` 覆盖；账号默认 `admin / Admin@2026`，可用 `E2E_USER` / `E2E_PWD` 覆盖。

## CI

`ruff check` → `manage.py check` → `migrate` → `ensure_admin` → `doctor` → `api.tests` → 启动服务并请求 `/api/health`。

## 性能基线

```bash
# 需先启动服务；命令会自建临时账号并清理
python manage.py bench_api --threads 16 --seconds 8
```

当前基线（单进程 + SQLite）：`currentUser` 约 800+ req/s，`heartbeat` 优化后约 880 req/s
（优化前只有 8 req/s，瓶颈是每次心跳 2 条 UPDATE + SQLite 写锁）。
容量规划与调参见 `docs/deployment.md` 第 12 节。

## 覆盖矩阵

| 领域 | 关键断言 |
| --- | --- |
| 认证 | 登录成功/失败、当前用户、退出失效、坏 token 401、非法 JSON 400 |
| 登录节流 | 连续失败触发 429「尝试次数过多」，成功登录清零；客户端与控制台两套 scope |
| 未授权矩阵 | 8 个控制台读接口 + 3 个写接口匿名访问全部 401，且不返回数据 |
| 旧版地址簿 | `/api/ab` GET/POST 往返、无 token 401、空列表不误删 |
| 新版地址簿 | personal/settings/shared profiles、peers/tags 形状、peer+tag CRUD 全部 200 空正文 |
| 客户端用户/设备 | `/api/users`、`/api/peers`、`/api/device-group/accessible` 的 `total + data`，`info.{username,device_name,os}` |
| 设备上报 | sysinfo 首次/重复上报、preset-* 键、SYINFO_UPDATED 纯文本、sysinfo_ver、heartbeat 不返回 sysinfo 键 |
| 审计 | conn/file/alarm 空正文、`/api/audit/conn/active` 顶层字符串、PUT 备注、非法 guid 400 |
| 录像上传 | 分片 new/part/tail/remove、按 offset 续写、文件内容校验、路径穿越清洗、超 8MB 413 |
| 切换授权 | switch-grant 落库并返回 `accepted` |
| 控制台多用户 | 管理员看全部；普通用户只看自己设备/地址簿；越权改他人地址簿 403；不能改自己管理员位/删除自己 |
| 控制台 CRUD | 用户/设备归属/地址簿联系人/标签/分组/成员/日志/统计 |
| 前端 | 初始化或登录、8 个菜单可达、页面渲染、面包屑、退出登录、无 JS 异常、无控制台错误 |
| CSRF | 客户端 API 无 token 可调用（豁免）；控制台写接口缺 token 403；`/console/` 下发 csrftoken 后带 token 可登录 |
| 生产配置 | `DEBUG=False/"False"` 解析、ALLOWED_HOSTS/CACHE_URL 列表与整数解析、`.env` 加载、节流键哈希、`/api/health` 的 db/cache 组合状态、安全响应头 |

## 安全基线（随测试固化）

- 密码策略：`AUTH_PASSWORD_VALIDATORS` 在控制台建用户/改密、注册页生效；最少 8 位；`PASSWORD_VALIDATION=0` 可关闭。
- 登录节流：`LOGIN_MAX_ATTEMPTS=8`、`LOGIN_LOCK_SECONDS=300`，客户端与控制台分别计数；缓存键为 SHA1 摘要，不落明文 IP/用户名。默认 LocMem，多进程请配 `CACHE_URL=redis://...`。
- CSRF：`CsrfViewMiddleware` 已启用；客户端/旧版接口在 `api/urls.py` 统一 `csrf_exempt`，控制台 `/api/console/*` 强制校验 token（前端自动带 `X-CSRFToken`）。
- 响应头：`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: same-origin`；`HTTPS=1` 时叠加 HSTS、Secure Cookie 与 SSL 跳转。
- 上传：文件名 basename + 白名单字符清洗，单块 8MB 上限（同时设置 `DATA_UPLOAD_MAX_MEMORY_SIZE=10MB`）。
- 健康检查：`GET /api/health` 返回数据库/缓存状态，数据库故障 503、缓存故障 `degraded`。
- `python manage.py check --deploy` 提示默认 `SECRET_KEY` 与 `ALLOWED_HOSTS=*`（api.W001/api.W002），生产必须用环境变量覆盖。

## 已知限制

- 数据库为 SQLite：单写者，适合中小规模；高并发请换 MySQL/PostgreSQL（`mysqlclient` 已在 requirements）。
- 节流默认进程内缓存；多进程/多机部署需按 `docs/deployment.md` 配置 Redis（`CACHE_URL`），否则各进程独立计数。
- E2E 依赖本机 Chrome/Chromium，可用 `CHROME_PATH` 指定可执行文件。
- 共享地址簿 `rule>0` 的语义是「共享给所有登录用户」，测试用 `rule=0` 验证严格隔离。
