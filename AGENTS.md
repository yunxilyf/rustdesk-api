# AGENTS.md — 项目规范（开发者 / AI 代理 / PR 提交者）

本文件是本仓库的**唯一规范入口**。任何人（包括 AI 代理）在改动代码前必须先读本文件；与本文冲突的临时约定一律以本文为准。

- 项目：RustDesk 1.5.x 兼容的 API 服务端 + 多用户管理控制台
- 后端：Python 3.12+ / Django 6.1 / SQLite（可切 PostgreSQL、MySQL 8.4+）
- 前端：Vue 3 + TDesign Vue Next + Vite，构建产物由服务端以静态文件提供
- 客户端契约：37 个「方法 + 路径」组合，**不得破坏**（见 `docs/client_api_contract.md`）

---

## 1. 目录结构

```text
.
├── AGENTS.md                   # 本项目规范（本文件）
├── Dockerfile                  # 镜像构建入口（多阶段：前端构建 + Python 运行时）
├── manage.py
├── version.py                  # APP_VERSION，唯一版本号来源
├── requirements.txt            # 运行时依赖（开发/生产共用）
├── requirements-prod.txt       # 生产额外依赖（gunicorn/waitress/redis）
├── pyproject.toml              # ruff 配置（格式与静态检查）
├── .env.example                # 环境变量样例（不得写入真实密钥）
├── api/                        # 业务应用
│   ├── models.py               # 聚合导出：models_work + models_user + models_pro
│   ├── models_user.py          # 账号（UserProfile）
│   ├── models_work.py          # 设备、令牌、旧版地址簿、连接/文件日志、重登记
│   ├── models_pro.py           # 新版地址簿、分组、系统设置、切换授权、录像记录
│   ├── views.py                # 仅 re-export，禁止写业务逻辑
│   ├── views_api.py            # RustDesk 客户端 API（登录/心跳/sysinfo/审计/旧版地址簿）
│   ├── views_pro.py            # 新版地址簿、分组、设备部署、CLI 等
│   ├── console_api.py          # 控制台 JSON API（Session 登录 + CSRF）
│   ├── views_front.py          # 首页跳转、注册/登出、旧版 action 兼容
│   ├── webclient.py            # 网页远控 Session 鉴权、共享令牌绑定、免安装版 /web/ 静态托管
│   ├── client_auth.py          # 客户端 Bearer 认证与令牌续期
│   ├── throttle.py             # 登录/注册限流（缓存实现，可切 Redis）
│   ├── settings_store.py       # 运行时系统设置（DB + 缓存）
│   ├── tag_colors.py           # 标签颜色 ARGB 归一化
│   ├── checks.py               # check --deploy 安全自检
│   ├── admin.py / admin_user.py / admin_pro.py
│   ├── migrations/             # 只允许新增，不修改已发布迁移
│   ├── templates/              # 仅 Django admin 模板
│   └── tests/                  # 单元测试（本地保留，不入库）
├── rustdesk_server_api/        # Django 工程
│   ├── settings.py             # 环境变量集中解析
│   ├── env.py                  # env_bool/env_int/env_list/SECRET_KEY 校验
│   ├── urls.py                 # 根路由（/api/、/console/、/web/、/web-login、/admin/、/static/）
│   └── wsgi.py
├── frontend/                   # Vue 3 控制台源码（构建到 static/console）
├── deploy/                     # compose、systemd、nginx 模板、entrypoint、install-web、standalone、web 预构建包
├── docs/                       # 契约与部署文档（对外）
├── images/                     # README 用截图（仅保留被引用的）
├── static/                     # 运行期静态文件（admin/ 与 console/ 均为生成物）
├── tests/                      # 本地测试脚本与产物（整个目录不入库）
├── e2e/                        # Playwright 端到端脚本（本地保留，不入库）
├── _dev/  _ops/  _migrate/     # 私人脚本/运维/迁移快照（全部忽略）
└── .github/                    # workflows（CI/镜像/免安装包）+ PR 模板
```

**必须在根目录之外的地方**：临时脚本、调试文件、日志、数据库副本、打包产物。仓库根只允许出现代码、配置、文档与 `manage.py`。

---

## 2. 分层与职责

| 层 | 文件 | 规则 |
| --- | --- | --- |
| 客户端 API | `views_api.py` / `views_pro.py` | 只服务 RustDesk 客户端，响应形态按契约，**不允许**依赖控制台 Session |
| 控制台 API | `console_api.py` | 只服务浏览器，Session + CSRF，返回 `{ok: ...}` JSON |
| 模型 | `models_*.py` | 一个领域一个文件；`models.py` 只做导出 |
| 认证 | `client_auth.py` | 唯一客户端鉴权入口，43 位 token，过期即拒绝 |
| 设置 | `settings_store.py` | 只放运行时可改的业务开关，不替代环境变量 |
| 管理后台 | `admin_*.py` | 只做运营操作，不写业务逻辑 |

新增接口时：先更新 `docs/client_api_contract.md`，再实现，再补测试。客户端接口一旦发布，**只能新增字段/端点，不能改已有语义**。

---

## 3. 客户端 API 契约（硬约束）

- `POST /api/sysinfo` 成功响应必须是**纯文本** `SYSINFO_UPDATED`；`ID_NOT_FOUND` 表示需要重登记流程。
- 新版地址簿的写操作（peer/tag 增删改）成功必须是 **200 空正文**，任何非空正文都会被客户端当成错误。
- 审计接口成功必须是 **2xx 空正文**；`/api/audit/conn/active` 必须返回 JSON 字符串（无记录返回 `""`，不能是 `null`）。
- `GET /api/login-options` 必须返回 JSON 数组（无 OIDC 时返回 `[]`）。
- 匿名可访问：`/api/login`、`/api/login-options`、`/api/oidc/*`、`/api/sysinfo`、`/api/sysinfo_ver`、`/api/heartbeat`、`/api/health`；其余客户端接口必须带 `Authorization: Bearer <43 位 token>`。
- 登录失败按旧客户端契约返回 200 + `{"error": "..."}`；仅限流时返回 429。
- 设备身份以 `rid` 为准；`uuid` 变化走「窗口 + 待确认 + 管理员确认」流程，不允许静默接管。
- 令牌有效期 30 天滑动：剩余不足 1 天时，带 Bearer 的请求或匹配 `rid+uuid` 的心跳会续期；已过期不复活。

详细字段、请求体与成功判据见 `docs/client_api_contract.md`。修改契约必须同步该文档与测试。

---

## 4. Python 规范

- 版本：Python 3.12+；Django 6.1（`requirements.txt` 固定主版本）。
- 格式：`ruff format`；检查：`ruff check`。配置见 `pyproject.toml`（行宽 120，忽略 E501）。
- 导入：标准库 → Django → 本项目；禁止 `from x import *`（`api/views.py` 的 re-export 除外）。
- 日志：使用 `logging.getLogger(__name__)`，**禁止 `print`**（CLI 脚本除外）。
- 时间：统一 `django.utils.timezone.now()`，禁止裸 `datetime.now()`。
- 查询：注意 N+1，必要时 `select_related` / `prefetch_related` / `only`；新增过滤字段要加索引（`db_index` 或 `Meta.indexes`）。
- 写操作：涉及多表一致性时使用 `transaction.atomic()`；并发敏感更新使用条件更新（CAS）。
- 错误：客户端接口返回 JSON + 400/401/403/429；控制台返回 `{ok: false, msg}`；不要抛裸 500。
- 注释：解释「为什么」而不是「做了什么」；公共函数写 docstring；不要保留注释掉的死代码。
- 用户可见文案：中文，必要时走 `gettext`；日志与代码标识用英文。

---

## 5. 前端规范

- Vue 3 `<script setup>` + Composition API；页面放 `frontend/src/views`，布局放 `frontend/src/layouts`（需要复用组件时新建 `frontend/src/components`）。
- UI 统一使用 TDesign 组件；自定义样式放 `styles.css`，避免行内魔法值。
- 所有请求必须走 `frontend/src/api.js` 的 `request()`，禁止组件内直接 `fetch`；统一处理 401/403。
- 页面必须处理空态、加载态、错误态；表格分页使用 `current/pageSize`。
- 修改后必须 `npm --prefix frontend run build`（vite 直接输出到 `static/console/`）并实际页面对照验证；`static/console` 是构建产物，不入库。
- 颜色、图标、文案改动要检查深色/浅色可读性；不得引入与 TDesign 冲突的全局样式。

---

## 6. 测试规范

| 层级 | 位置 | 内容 |
| --- | --- | --- |
| 单元/契约 | `api/tests/` | Django `TestCase`，覆盖客户端 API、控制台 API、安全 |
| 端到端 | `e2e/` | Playwright 浏览器流程 |
| 本地脚本 | `tests/local/` | `smoke.py`、`probe_v2.py`、`console_smoke.py`、`seed_demo.py`、`clean_db.py` |
| 产物 | `tests/.artifacts/` | 日志与报告，已忽略 |

规则：
- 测试文件**不提交到 git**（`.gitignore` 已忽略），由维护者在本地保留运行；CI 在检出目录存在 `api/tests/` 时才跑单测，干净 clone 会跳过；外部贡献者以 `ruff check` + `manage.py check` + 手工验证为准。
- 新增接口必须同时补：正常路径、未授权、参数非法三类用例。
- 跑测试需要 `SECRET_KEY` 环境变量：
  `SECRET_KEY=<随机长串> python manage.py test api.tests`（先激活虚拟环境并安装依赖）
- 提交前至少：`ruff check` + `manage.py check` + `api.tests` 全绿；大改动再跑 `smoke.py`。
- 测试数据使用临时账号/临时库，测完清理；不得写入生产库。

---

## 7. 临时文件与产物

- 禁止在仓库根创建 `pip-*`、`*.log`、`*.sqlite3`、`build/`、`dist/`、截图、压缩包；这些一律被忽略，也不应长期保留。
- 调试脚本放 `_dev/`；运维/服务器脚本放 `_ops/`；迁移快照放 `_migrate/`；测试脚本放 `tests/local/`。
- 打包产物放 `dist/` 并在验证后删除；镜像由 CI 构建，不在仓库存应用二进制（`deploy/web/rustdesk-web-*.tar.gz` 第三方预构建静态包除外）。
- 发现根目录垃圾文件时，先确认无进程占用，再删除并补 `.gitignore`。

---

## 8. Git 与 PR

- 分支：`feat/<topic>`、`fix/<topic>`、`docs/<topic>`、`chore/<topic>`。
- 提交信息：Conventional Commits，例如 `fix: reject expired client tokens`；一次提交只做一件事。
- **AI 代理**：不要在用户未明确要求时创建 commit；推送前必须得到明确确认。用户说「提交」时才提交，说「推送」时才推送。
- 不要提交：`.env`、数据库、日志、截图临时文件、`node_modules`、`static/console`、`api/tests`、`e2e`、`tests/`。
- 提交前检查：`git status` 无意外文件、无密钥、迁移文件齐全、文档同步。

### PR 检查清单

- [ ] 变更范围与描述一致，没有顺带重构无关代码
- [ ] 客户端 API 契约未破坏（`docs/client_api_contract.md` 已更新）
- [ ] 新增/修改逻辑有对应测试（本地），并已通过
- [ ] `ruff check`、`manage.py check` 通过
- [ ] 涉及数据库的改动包含迁移文件（只新增，不改历史迁移）
- [ ] 涉及配置的改动同步了 `.env.example`、`README`、`docs/deployment.md`
- [ ] 没有提交密钥、日志、数据库、构建产物、测试文件
- [ ] 前端改动已构建并人工确认页面可用

---

## 9. 安全要求

- `SECRET_KEY` 必须由环境变量提供，长度 ≥50、字符种类 ≥10；不配时服务拒绝启动。
- 生产必须设置 `DEBUG=0`、明确的 `ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS`；HTTPS 部署设 `HTTPS=1`、`BEHIND_PROXY=1`。
- 客户端令牌 43 位；禁止回退到 32 位旧 token；改密/禁用账号要删除其 token。
- 初始化管理员需要 `WEB_SETUP_TOKEN`（≥32 位，独立包首次启动会自动生成并打印到 `data/setup_token`）；初始化完成后接口返回 403。
- 上传文件必须限制大小与文件名；`/api/record` 默认停用（客户端不上传）。
- 不在日志、异常信息、截图中输出密码/token/手机号等敏感数据。

---

## 10. 部署与文档

- 版本号只改 `version.py` 的 `APP_VERSION`，并同步 Release tag（README 若带版本徽章需一并更新）。
- 镜像构建入口是根目录 `Dockerfile`（多阶段：Node 构建前端 + Python 运行时）；CI、compose 都引用它，直接 `docker build -t rustdesk-api-server:local .` 即可。
- 部署步骤、环境变量、容量建议见 `docs/deployment.md`；运维记录放 `_ops/`，不入库。
- 行为变更必须同步：`README.md`、`README_EN.md`、`docs/client_api_contract.md`、`docs/console_api.md`（涉及控制台时）。

---

## 11. AI 代理操作清单

1. 先读本文件与相关 `docs/`，再读代码；不要凭记忆改接口。
2. 改客户端 API 前先确认客户端调用点（RustDesk 官方 1.5.x 源码，或本地 checkout 的客户端仓库）。
3. 本地验证顺序：`ruff check` → `manage.py check` → `api.tests` → 需要时 `smoke.py`。
4. 未经允许不部署生产、不改生产数据库；部署前备份数据库。
5. 不自动 commit / push；报告变更摘要，等用户明确指令。
6. 完成后报告：改了什么、为什么、验证结果、剩余风险。
