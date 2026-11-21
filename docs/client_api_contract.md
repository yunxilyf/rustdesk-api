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

## 认证

| 方法 | 路径 | 请求 | 成功响应 |
|---|---|---|---|
| POST | `/api/login` | `username,password,id,uuid,autoLogin,type,verificationCode?,tfaCode?,secret?,deviceInfo` | `{access_token,type:"access_token",user:{name,display_name,avatar,email,note,verifier,status,is_admin}}` |
| POST | `/api/logout` | Bearer，`{id,uuid}` | 任意 JSON（客户端忽略正文） |
| POST | `/api/currentUser` | Bearer，`{id,uuid}` | 顶层 User 对象（`name` 必需）；400/401 清空本地登录 |
| GET | `/api/login-options` | 无认证 | **JSON 字符串数组**，`[]` 表示不支持 OIDC；`common-oidc/<json>` 或 `oidc/<name>` |
| HEAD | `/api/login-options` | 无认证 | 仅用于 TLS 连通性探测 |
| POST | `/api/oidc/auth` | `{op,id,uuid,deviceInfo,apiDomain}` | `{code,url}` 或 `{error}` |
| GET | `/api/oidc/auth-query?code&id&uuid` | 无认证 | `{access_token,type,user{name,info{...},...}}`；`user.info` 为 Rust 侧必填对象 |

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
| POST | `/api/sysinfo` | `id,uuid,version,cpu,memory,os,hostname,username` + `preset-address-book-{name,tag,alias,password,note}`、`preset-device-name`、`preset-device-username`、`preset-note` | 纯文本 `SYSINFO_UPDATED`（缺失 id/uuid → `ID_NOT_FOUND`） |
| POST | `/api/sysinfo_ver` | 空 body | 任意文本（不透明版本号，与本地不同则重传 sysinfo） |
| POST | `/api/heartbeat` | `{id,uuid,ver:i64,conns?:[i32],modified_at:i64}` | JSON map，可选 `sysinfo`（仅键存在就重传，禁止乱给）/`disconnect:[i32]`/`strategy{config_options,extra}`/`modified_at` |

## 审计

| 方法 | 路径 | 请求 | 成功响应 |
|---|---|---|---|
| POST | `/api/audit/conn` | `{id,uuid,conn_id,session_id,nonce, action:"new"/"close"/..., ip, peer:[id,name], type}` | 2xx 空正文 |
| POST | `/api/audit/file` | `{id,uuid,peer_id,conn_id,type,path,is_file,info:"<json 字符串>",nonce}` | 2xx 空正文 |
| POST | `/api/audit/alarm` | `{id,uuid,typ,info:"<json 字符串>",conn_id,nonce}` | 2xx 空正文 |
| PUT | `/api/audit` | Bearer，`{guid,note}` | 任意（200） |
| GET | `/api/audit/conn/active?id&session_id&conn_type` | Bearer | **顶层 JSON 字符串**（ConnLog.id）；`null` = 稍后再查 |

## 其他

| 方法 | 路径 | 请求 | 成功响应 |
|---|---|---|---|
| POST | `/api/switch-grant` | `{id,switch_code_verifier,timestamp,signature}` | `{accepted:true}`；拒绝时 `{accepted:false,server_time:<unix 秒>}` 供客户端重签一次 |
| POST | `/api/record?type=new\|part\|tail\|remove&file&offset&length` | 原始字节 body，无认证（客户端协议如此）；目录受 `RECORD_MAX_TOTAL_MB` 配额保护，超额返回 507 | JSON map 且不含 `error` |
| POST | `/api/devices/cli` | Bearer，`{id,uuid,user_name?,address_book_name?,device_group_name?,...}` | 空正文（CLI 打印 `Done!`） |
| POST | `/api/devices/deploy` | Bearer，`{id,uuid,pk}` | `{result:"OK"}` / `ID_TAKEN` / `INVALID_INPUT` / `NOT_ENABLED` |

## 本仓库实现状态

- 已实现：上表全部 37 个方法与路径。
- 未实现（需要额外数据模型/管理界面，客户端会静默降级）：`strategy` 策略下发（`/api/heartbeat` 响应中的可选字段）、OIDC 真实登录（`login-options` 返回空数组，客户端不显示 OIDC 入口）、共享地址簿的细粒度授权（当前按 `rule>0` 对全体用户共享 + 属主可见自己的簿）。
- 回归测试：`api/tests/test_client_api.py`（26 项契约断言，逐条模拟客户端请求）。
