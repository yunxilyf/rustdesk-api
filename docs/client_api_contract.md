# RustDesk 客户端 API 契约（1.5.3）

基线：客户端 `91de8e8e2b36b0e4045858a43b492c75141821b4`（RustDesk 1.5.3，Flutter 1.5.3+71）。
本文是 api-server 的兼容性依据：**方法、路径、成功响应的字节形态**都必须与客户端源码一致，否则客户端会静默判失败。

## 三个最容易踩的坑

1. **成功正文有字节级要求**
   - `POST /api/sysinfo` 只能返回纯文本 `SYSINFO_UPDATED`（无引号、无换行）；`ID_NOT_FOUND` 表示设备未登记，客户端下次心跳重试。
   - 新版地址簿的所有写操作（`/api/ab/peer/*`、`/api/ab/tag/*`）必须返回 **HTTP 200 + 空正文**；返回 `{}` 或 `{"code":0}` 会被判为失败。
   - `/api/audit/conn|file|alarm` 要求 **2xx + 空正文**，非空正文会触发最多 3 次重试。
   - `/api/device-group/accessible`、`/api/users`、`/api/peers` 必须返回 `{total, data}`；缺少 `total` 时客户端整页丢弃（列表静默为空）。
2. **路由方法按源码注册**：`login-options` 是 GET，`sysinfo_ver` 是 POST，新版地址簿 peers/tags 查询是 POST，更新是 PUT，删除是带 JSON 数组 body 的 DELETE。
3 代际差异：旧版地址簿 `GET/POST /api/ab` 里 `data`、`tag_colors` 是**嵌套 JSON 字符串**；新版是 `total`+`data` 数组。

## 组件与端口边界

本仓库只实现 **API server**（HTTP，默认 21114），不代理 RustDesk 的 rendezvous / relay 流量：

| 组件 | 端口 | 协议 | 作用 |
|---|---|---|---|
| API server | 21114/tcp | HTTP | 本仓库：登录、地址簿、心跳、审计、控制台 |
| hbbs | 21115/tcp | TCP | NAT 类型测试 |
| hbbs | 21116/tcp + udp | TCP/UDP | ID 注册与心跳（rendezvous） |
| hbbr | 21117/tcp | TCP | 中继转发 |
| hbbs | 21118/tcp | WebSocket | Web 客户端信令 |
| hbbr | 21119/tcp | WebSocket | Web 客户端中继 |

hbbs / hbbr 是二进制协议和 WebSocket 服务，**不提供 HTTP API**，客户端也不会向它们发送 `/api/*` 请求；因此客户端 API 契约只需覆盖 21114 上的端点。

## 认证

| 方法 | 路径 | 请求 | 成功响应 |
|---|---|---|---|
| POST | `/api/login` | `username,password,id,uuid,autoLogin,type,verificationCode?,tfaCode?,secret?,deviceInfo` | `{access_token,type:"access_token",user:{name,display_name,avatar,email,note,verifier,status,is_admin}}` |
| POST | `/api/logout` | Bearer，`{id,uuid}` | 任意 JSON（客户端忽略正文） |
| POST | `/api/currentUser` | Bearer，`{id,uuid}` | 顶层 User 对象（`name` 必需）；400/401 清空本地登录 |
| GET | `/api/login-options` | 无认证 | **JSON 字符串数组**；没有启用的第三方登录时返回 `[]`；否则首项为 `common-oidc/<json>`（完整按钮列表 `[{"name":"<按钮名称>"}, ...]`），其后每个 `oidc/<op>` 兼容旧客户端 |
| HEAD | `/api/login-options` | 无认证 | 仅用于 TLS 连通性探测 |
| POST | `/api/oidc/auth` | `{op,id,uuid,deviceInfo,apiDomain}` | `{code,url}`；`op` 为按钮名称或提供方标识，`code` 为待轮询的 state，`url` 为提供方授权地址（OIDC/Google 含 PKCE）。未配置/未知 op/配置不全时返回 200 + `{error}` |
| GET | `/api/oidc/auth-query?code&id&uuid` | 无认证 | 未完成时 `{"error":"No authed oidc is found"}`（客户端靠该子串继续轮询）；成功后返回 AuthBody `{access_token,type,user{...info:{}}}`，且只可领取一次 |

**Token 生命周期**：`access_token` 默认 30 天（`TOKEN_TTL_SECONDS`），服务端记在 `expires_at`；过期后访问受保护接口一律 401。旧库中 `expires_at IS NULL` 的 token 会在首次使用时补写有效期（平滑升级），不会永久有效；在线客户端的心跳在剩余不足 24 小时（`HEARTBEAT_TOKEN_REFRESH_SECONDS`）时自动续满，因此正常使用的客户端不会掉登录，只有连续离线超过 30 天才需要重新登录。

## 地址簿（两代协议）

### 旧版（≤1.4.x / Sciter）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/ab` | `{updated_at, data:"<json 字符串>"}`，内层 `{tags:[],peers:[{id,username,hostname,alias,platform,tags,hash}],tag_colors:"<json 字符串>"}`；`data` 原文为 `null` 时清空列表 |
| POST | `/api/ab` | `{data:"<完整快照 json>"}`；200 + 空正文/`null`/无 `error` 的 JSON 均算成功 |
| POST | `/api/ab/get` | Sciter 专用，等价 GET |

### 新版（1.5.x 多地址簿）

| 方法 | 路径 | 请求 | 成功响应 |
|---|---|---|---|
| POST | `/api/ab/personal` | Bearer，空 body | `{guid}`；**404 时客户端回退旧版协议** |
| POST | `/api/ab/settings` | Bearer，空 body | `{max_peer_one_ab:int}`（0=不限；404 表示无共享地址簿） |
| POST | `/api/ab/shared/profiles?current&pageSize` | Bearer | `{total,data:[{guid,name,owner,note,info,rule}]}`，rule: 1 只读 / 2 读写 / 3 完全控制；包含 `rule>0` 的共享簿 + **本人拥有的非个人簿**（本人 rule 最低下发 2，便于客户端写入） |
| POST | `/api/ab/peers?current&pageSize&ab=<guid>` | Bearer | `{total,data:[Peer]}` |
| POST | `/api/ab/tags/<guid>` | Bearer | **顶层数组** `[{name,color:int}]`（color 必须是 int） |
| POST | `/api/ab/peer/add/<guid>` | 单个 Peer 对象 | 200 空正文 |
| PUT | `/api/ab/peer/update/<guid>` | `{id, tags/alias/note/hash/password/...}` | 200 空正文 |
| DELETE | `/api/ab/peer/<guid>` | `["id1","id2"]` | 200 空正文 |
| POST | `/api/ab/tag/add/<guid>` | `{name,color}` | 200 空正文 |
| PUT | `/api/ab/tag/rename/<guid>` | `{old,new}` | 200 空正文 |
| PUT | `/api/ab/tag/update/<guid>` | `{name,color}` | 200 空正文 |
| DELETE | `/api/ab/tag/<guid>` | `["tag1"]` | 200 空正文 |

Peer 字段：`id,hash,password,username,hostname,platform,alias,tags[],note,loginName,device_group_name,forceAlwaysRelay("true"/"false"),rdpPort,rdpUsername,same_server`。

注意：`GET /api/peers` 里的 `loginName` 必须是 **API 账号名**（客户端设备分组页 `peers_view.dart:591` 用 `peer.loginName == 选中用户` 过滤，为空会导致选中用户后设备列表空白）；同一 rid 出现在多个地址簿时只返回一条；非管理员不返回未归属设备。
别名兼容：客户端 `PeerPayload.toPeer()`（hbbs.dart:93）不映射 `alias`，卡片标题只拼 `info.username@info.device_name`。因此当联系人设置了别名时，本接口把 `info.username` 置空、`info.device_name` 填别名，让设备分组页直接显示别名；无别名时仍为「用户名@主机名」。

图标：客户端 `getPlatformImage(peer.platform)` 只认 `Windows/Linux/Mac OS/Android`，`platform` 为空时不画系统图标。旧版地址簿只上报 `hash`，`platform/hostname` 常为空，服务端会用最近一次 sysinfo 的 `os/hostname/username` 兜底：`Windows*→Windows`、`*mac*/darwin→Mac OS`、`*linux*/ubuntu/debian/centos/...→Linux`、`*android*→Android`。

## 用户 / 设备 / 分组

| 方法 | 路径 | 成功响应 |
|---|---|---|
| GET | `/api/users?current&pageSize&accessible&status=1` | `{total,data:[User]}` |
| GET | `/api/peers?current&pageSize&accessible&status=1` | `{total,data:[PeerPayload]}`，组页面读 `info.{username,device_name,os}` |
| GET | `/api/device-group/accessible?current&pageSize` | `{total,data:[{name}]}` |

## 系统信息与心跳

| 方法 | 路径 | 请求 | 成功响应 |
|---|---|---|---|
| POST | `/api/sysinfo` | `id,uuid,version,cpu,memory,os,hostname,username` 及 `preset-*` 可选字段 | 纯文本 `SYSINFO_UPDATED`；标识无效时返回 `ID_NOT_FOUND`。更换已登记设备的 UUID 需要管理员开启重新登记窗口，窗口内上报的新 UUID 只记为待确认，管理员在后台确认后才生效 |
| POST | `/api/sysinfo_ver` | 空 body | 任意文本（不透明版本号，与本地不同则重传 sysinfo） |
| POST | `/api/heartbeat` | `{id,uuid,ver:i64,conns?:[i32],modified_at:i64}` | JSON map，可选 `sysinfo`（仅键存在就重传，禁止乱给）/`disconnect:[i32]`/`strategy{config_options,extra}`/`modified_at` |

心跳仅更新已登记且 UUID 匹配的设备。新设备或 UUID 不匹配时返回 `sysinfo` 键，提示客户端提交设备信息。更换已登记设备的 UUID：管理员在设备列表执行「允许重新登记（10 分钟）」，设备再次上报时只登记待确认 UUID，管理员确认后才原子切换；也可以由带有效令牌且具备设备管理权限的请求直接完成。已登记的设备标识用于兼容原生遥测协议，采集端应部署在可信网络。

## 审计

| 方法 | 路径 | 请求 | 成功响应 |
|---|---|---|---|
| POST | `/api/audit/conn` | `{id,uuid,conn_id,session_id,nonce, action:"new"/"close"/..., ip, peer:[id,name], type}` | 2xx 空正文 |
| POST | `/api/audit/file` | `{id,uuid,peer_id,conn_id,type,path,is_file,info:"<json 字符串>",nonce}` | 2xx 空正文 |
| POST | `/api/audit/alarm` | `{id,uuid,typ,info:"<json 字符串>",conn_id,nonce}` | 2xx 空正文 |
| PUT | `/api/audit` | Bearer，`{guid,note}`，仅可修改有权访问的记录 | 200；记录不可见时返回 404 |
| GET | `/api/audit/conn/active?id&session_id&conn_type` | Bearer | **顶层 JSON 字符串**（ConnLog.id）；无可见活动连接时返回空字符串 `""`（不能是 `null`） |

连接、文件和告警上报要求设备 ID 与登记的 UUID 匹配。连接更新按设备与连接编号限定。

## 其他

| 方法 | 路径 | 请求 | 成功响应 |
|---|---|---|---|
| POST | `/api/switch-grant` | `{id,switch_code_verifier,timestamp,signature}` | `{accepted:false,server_time:<unix 秒>}`，当前服务尚未实现签名验证 |
| POST | `/api/record` | 历史录像上传 | 410，服务端上传已停用 |
| POST | `/api/devices/cli` | Bearer，`{id,uuid,user_name?,address_book_name?,device_group_name?,...}` | 空正文（CLI 打印 `Done!`） |
| POST | `/api/devices/deploy` | Bearer，`{id,uuid,pk}`；普通用户仅登记当前令牌对应设备 | `{result:"OK"}` / `ID_TAKEN` / `INVALID_INPUT` / `NOT_ENABLED` |

## 本仓库实现状态

- 控制台与客户端共享设备归属和地址簿规则。共享规则 1 允许客户端读取，规则 2 和 3 允许客户端修改联系人和标签。
- 未实现（需要额外数据模型/管理界面，客户端会静默降级）：`strategy` 策略下发（`/api/heartbeat` 响应中的可选字段）、`switch-grant` 的设备签名校验、共享地址簿的细粒度授权（当前按 `rule>0` 对全体用户共享 + 属主可见自己的簿）。
- OIDC 登录已实现（授权码 + PKCE），浏览器回调地址为 `/api/oidc/callback`，配置见 `docs/oidc.md`。
- 回归测试由维护者本地保留（逐条模拟客户端请求），不随仓库分发。
