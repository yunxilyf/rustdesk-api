# 网页远控（Web 客户端）

控制台侧栏的「网页远控」会在新标签页打开一个浏览器版 RustDesk 客户端，可直接连接本服务器的设备。
它复用本项目的客户端 API（`/api/*`）与 hbbs/hbbr 的 WebSocket 信令，不改变任何服务端契约。

## 组成

- 静态站点：`/web/`，默认安装在 `/opt/rustdesk-api/webroot/web`。
- WebSocket 代理：`/ws/id` → `127.0.0.1:21118`（hbbs），`/ws/relay` → `127.0.0.1:21119`（hbbr）。
- 会话鉴权与共享登录：`/web/`、`/web/rd-config.js`、`/ws/id`、`/ws/relay` 均直接校验控制台的 Django Session（Docker 模式下由内置 nginx 通过 `auth_request` 调用 `/api/webclient/auth`，免安装版由 Django 校验）。登录控制台后点侧栏「网页远控」即可打开 `/web/`，服务端通过 `/web/rd-config.js` 自动下发当前会话绑定的 RustDesk 客户端令牌与用户信息，**无需在网页端再次登录**；未登录直接访问 `/web/` 会跳到控制台并显示「访问网页远控需要先登录」提示。
- 双向退出与实时断连：在控制台或网页远控任一侧退出登录时，会同步注销控制台会话与 Web 令牌，并通过跨标签页通知（`BroadcastChannel` + `storage`）立即关闭正在进行的远控连接并跳回登录页；网页端同时每 15 秒及切回前台时探测 `/api/webclient/auth`，管理员禁用账号、修改密码或切换账号时也会自动断开活跃连接。
- 静态资源基线来自 [temandroid/rustdesk-web](https://github.com/temandroid/rustdesk-web)（AGPL-3.0）。**预构建站点包随本仓库分发**（`deploy/web/rustdesk-web-1.5.3.tar.gz`），其源码不随本仓库分发；页面左下角保留 Source 链接以符合许可证要求。当前包已按 RustDesk **1.5.3** 源码重新编译（见下节）。

## 安装

1. 使用仓库自带的预构建包 `deploy/web/rustdesk-web-1.5.3.tar.gz`，执行：

   ```bash
   ./deploy/install-web.sh /opt/rustdesk-api/webroot
   ```

   脚本会把已有的 `web` 目录备份为 `web.bak-<时间>`，再解压新包到
   `/opt/rustdesk-api/webroot/web`。也可以手工解压：

   ```bash
   mkdir -p /opt/rustdesk-api/webroot/web
   tar --no-same-owner --no-same-permissions -xzf deploy/web/rustdesk-web-1.5.3.tar.gz -C /opt/rustdesk-api/webroot/web
   chmod -R u=rwX,go=rX /opt/rustdesk-api/webroot/web
   ```

2. 无需手工维护 `rd-config.js`：API 服务会在 `/api/webclient/config.js` 校验控制台会话后动态生成
   （`idServer`/`apiServer` 取请求域名，`key` 取环境变量 `RUSTDESK_KEY`，并下发当前用户的共享登录令牌），nginx 用精确
   location 覆盖包内静态文件：

   ```nginx
   location = /web/rd-config.js {
       proxy_pass http://127.0.0.1:21114/api/webclient/config.js;
       proxy_set_header Host $http_host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
   }
   ```

   需要在 API 服务的 `.env` 中设置（均可选）：`ID_SERVER`（默认取访问域名）、`API_SERVER`
   （默认 `https://<访问域名>`）、`RUSTDESK_KEY`（hbbs 公钥，`docker logs hbbs` 首行的 Key）。

3. 在 nginx 站点配置中引入 `deploy/nginx-webclient.conf.example`（按实际路径修改），并确保
   `hbbs` 的 21118/tcp 与 `hbbr` 的 21119/tcp 已发布到宿主机。配置使用 `auth_request /_web_auth`
   逐请求校验控制台 Session（不再需要手工维护静态 Cookie）；若宿主 nginx 缺少 `auth_request` 模块，
   直接将 `/web/` 代理到后端 `127.0.0.1:21114`（容器内置 nginx 或 Django 会完成鉴权）。

## Docker 部署

使用仓库根目录的 `Dockerfile` 构建的镜像**内置 nginx 和 `deploy/web/` 预构建包**，一个 `21114` 端口同时提供 API、控制台、网页远控和 WebSocket 代理，`docker compose up -d` 起来即可用，不再需要在宿主机单独配 `/web/` 目录：

- `entrypoint.sh` 默认 `WEBCLIENT_AUTO_INSTALL=1`，首次启动把包解压到 `WEBROOT`（默认 `/app/webroot`）；已有 `web/index.html` 时跳过，升级用 `WEBCLIENT_FORCE_UPDATE=1` 重启一次，旧目录保留为 `.web.old`；
- 容器内 nginx 监听 `PORT`（默认 `21114`），gunicorn 只监听 `127.0.0.1:21115`，所以对外仍然只有一个端口；
- `/ws/id`、`/ws/relay` 分别由 `HBBS_WS`、`HBBR_WS` 指定（默认 `host.docker.internal:21118`、`:21119`）；`docker-compose.prod.yaml` 已加 `host.docker.internal:host-gateway`，Linux 上也能解析到宿主机；
- 浏览器直接访问 `http://<宿主机>:21114/console/`；未登录访问 `/web/` 会 302 回控制台，登录后点侧栏「网页远控」即可；
- 如果外层还有宿主 nginx / 宝塔做 HTTPS，照常反代到 `21114` 即可，不需要再为 `/web/` 单独写静态站点配置（容器内 nginx 已处理）；
- 不想自动安装可设 `WEBCLIENT_AUTO_INSTALL=0`，再按上一节手工安装。

如果不用 compose、直接 `docker run`，挂载 `-v /opt/rustdesk-api/webroot:/app/webroot`，设置 `SECRET_KEY`，并用 `-e HBBS_WS=<宿主机IP>:21118 -e HBBR_WS=<宿主机IP>:21119` 指向 hbbs/hbbr 即可。

## 免安装包（Windows / Linux）

`deploy/rustdesk-api.spec` 会把 `deploy/web/` 一起打进 PyInstaller 包；首次运行自动解压到
`data/webroot/web`，由 Django 直接提供 `/web/`（免安装版没有 nginx），控制台会话校验、
共享登录与 `/web/rd-config.js` 都由 API 服务自己处理。

因为 Django/waitress 不代理 WebSocket，浏览器需要**直连 hbbs/hbbr 的 WS 端口（`21118`/`21119`）**。
在可执行文件旁的 `.env` 中配置：

```ini
# Web 核心对纯 IP 会自动把基础端口 +2（21116 -> 21118、21117 -> 21119），
# 因此填裸 IP（或 :21116 / :21117），不要写成 :21118 / :21119；
# 若 hbbs/hbbr 与本程序同机且使用默认端口，ID_SERVER/RELAY_SERVER 可留空。
ID_SERVER=192.168.1.20
RELAY_SERVER=192.168.1.20
RUSTDESK_KEY=<hbbs 的 id_ed25519.pub 内容>
```

- 用局域网 IP，不要写 `127.0.0.1`（其他电脑的浏览器连不到）；如果使用非标准 WS 端口，直接写显式地址（例如 `ws://192.168.1.20:21118/ws/id`）。
- 页面是 `http://` 时浏览器可以直接连 `ws://`；如果要上 HTTPS，请在前面加 nginx，按上一节代理
  `/ws/id`、`/ws/relay`，并把 `ID_SERVER` 改成域名，`RELAY_SERVER` 留空。
- 升级时覆盖可执行文件即可；`data/webroot/web` 不会动，需要换网页包时删除该目录后重启。

## 使用

1. 打开 `https://<你的域名>/console/` 并登录（直接打开 `/web/` 也会提示登录，完成后自动跳回 `/web/`）。
2. 侧栏点击「网页远控」，新标签页会打开 `/web/` 并自动复用当前控制台账号的登录态（地址簿与设备分组直接可见，无需再次登录）。
3. 个人地址簿中已保存连接密码的设备（如通过桌面端记住并同步到地址簿）在网页端首次连接即可免输密码（哈希仅驻留页面内存，不写入 `localStorage`，退出登录即清空）；手动输入密码时，按需勾选「记住密码」才会保存哈希并同步回写到个人地址簿。

## 限制与注意

- 浏览器需要 WebGL；无 GPU 的无头浏览器需 `--enable-unsafe-swiftshader` 才能渲染，正常桌面浏览器不受影响。
- RustDesk 1.5 的 WebRTC 直连需要服务端支持（Server Pro 1.8.7+ 或自行给 OSS 补协议并重编 hbbs/hbbr）；
  当前 OSS 1.1.16 会走 hbbr 中继或 TCP/UDP 打洞，Web 端通常表现为中继连接。
- 该页面是第三方 AGPL 前端，升级时替换 `/opt/rustdesk-api/webroot/web` 即可；如需完全自定义，
  可自行构建同类 Web 客户端并保持相同的 `rd-config.js` 与 `/ws/*` 约定。
- 不建议把 `/web/` 直接暴露为匿名站点；访问控制直接依赖控制台 Django Session，注销或禁用账号立即失效。
- 在线状态由网页核心调用 `POST /api/peers/online`（Bearer）判断，服务端按设备心跳时间与
  `DEVICE_ONLINE_SECONDS`（默认 300 秒）计算，与桌面端、控制台保持一致。hbbs 的 WebSocket
  桥只处理注册/打洞，不接受 `OnlineRequest`（桌面版走 TCP 21115），因此不要改回 WS 查询。

## 使用预构建包

网页端源码不随本仓库分发；编译好的站点包随仓库放在 `deploy/web/`：

1. 下载后解压覆盖 `/opt/rustdesk-api/webroot/web`（保留上一版目录便于回滚）。
2. `rd-config.js` 由 API 服务动态下发，不需要改包内文件；只需在 `.env` 配好 `RUSTDESK_KEY`。
3. 包内已包含 1.5.3 的 Flutter 壳、Web 核心、字体与图标；升级时整体替换即可，会话鉴权与 nginx 配置不变。
4. 校验包完整性：部署前可执行 `sha256sum deploy/web/rustdesk-web-1.5.3.tar.gz` 并记录，便于回滚时核对。

> 该组件基于 AGPL-3.0 的 temandroid/rustdesk-web；网页页脚保留 “Source (AGPL-3.0)” 入口。
> 如对外再分发本站点包，请同时提供对应源码（或书面 offer），以满足 AGPL 要求。

## 常见问题

### 页面报 `Failed to connect to wss://<域名>/ws/relay`

hbbs 通过打洞响应下发中继地址；如果 hbbs 启动参数 `-r` 指向的域名没有对应的 443 站点和证书，浏览器就连不上中继。请让中继域名与网页同域，例如：

```bash
docker run -d --name hbbs --restart unless-stopped \
  --network <rustdesk-net> \
  -p 21115:21115 -p 21116:21116 -p 21116:21116/udp -p 21118:21118 \
  -v <data-dir>:/root \
  rustdesk/rustdesk-server:latest hbbs -r rustdeskapi.example.com:21117
```

这样 hbbs 日志会显示 `relay-servers=["rustdeskapi.example.com:21117"]`，网页端的 `wss://rustdeskapi.example.com/ws/relay` 就能走本文的 nginx 反代。

### 仍显示旧的 ID 服务器

`rd-config.js` 中的 `force: true` 会覆盖浏览器 `localStorage` 里的旧值；修改后请强制刷新（Ctrl+F5）并重新打开网页远控。

## 控制台日志说明

- `Manifest: Line 1, column 1, Syntax error`：旧 `index.html` 引用了 `/web/manifest.json`，而该请求不带会话 Cookie，被 302 成控制台 HTML。现已移除 manifest 引用；若仍出现，请强制刷新。
- `prepareServiceWorker took more than 4000ms`：Flutter loader 首次注册 Service Worker 的警告，弱网下常见，SW 激活后不再出现，可忽略。
- `content_main.js ... Cannot read properties of null (reading 'classList')`：`content_main.js` 不是本站资源，来自浏览器扩展（指纹浏览器、广告拦截等）。用无痕窗口可验证。
- `AbortError: signal is aborted`：客户端切换标签时取消上一轮地址簿请求，属正常噪声；若持续出现，清除该站点的 localStorage 与 Service Worker 后重试。
- `/api/console/me 401`：控制台未登录时的探测请求，登录后消失。