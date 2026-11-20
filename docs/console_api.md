# 控制台 API 契约（/api/console）

前端：Vue 3 + Vite + TDesign Vue Next，产物部署在 `/console/`。
认证：Django Session Cookie（`sessionid`），所有请求 `credentials: 'include'`，JSON body。
未登录统一返回 **401** `{"ok": false, "msg": "未登录"}`。
权限：`is_admin=true` 为管理员；普通用户只能看自己的数据（后端按 rids 过滤：`RustDeskPeer.uid` 绑定 + 个人地址簿联系人 + `rule>0` 共享地址簿联系人），访问管理接口返回 **403** `{"ok": false, "msg": "无权限"}`。

通用列表响应：`{"total": <int>, "list": [ ... ]}`；分页参数 `current`（从 1 开始）、`pageSize`（默认 20）。
时间格式：`YYYY-MM-DD HH:MM:SS`；布尔字段用 true/false。

## 认证

| 方法 | 路径 | 请求 | 响应 |
|---|---|---|---|
| PATCH | `/api/console/me` | 本人修改 `display_name` / `email`（邮箱仅备注） |
| POST | `/api/console/login` | `{username, password}` | `{ok:true, user:User}`；失败 400 `{ok:false,msg}` |
| POST | `/api/console/logout` | — | `{ok:true}` |
| GET | `/api/console/me` | — | `{user:User}` |
| PUT | `/api/console/me/password` | `{old, password}` | `{ok:true}` / 400 |
| GET | `/api/console/setup` | — | `{ok:true, needs_setup:bool, allow_registration:bool}`（库中无用户时 needs_setup 为 true） |
| POST | `/api/console/setup` | `{username, password}` | 仅库中无用户时创建首个管理员并登录；已初始化返回 403 |
| POST | `/api/console/register` | `{username, password}` | 自助注册；受「允许注册」开关控制，关闭时返回 `{ok:false}`；用户名 3~50、密码≥8 |
| GET | `/api/console/settings` | — | `{ok, allow_registration, is_admin}`（登录用户可读） |
| PUT | `/api/console/settings` | `{allow_registration: bool}` | 管理员开关注册；非管理员 403 |

`User` = `{id, username, display_name, email, avatar, note, is_admin, is_active, status}`

## 用户（仅管理员）

| 方法 | 路径 | 请求 |
|---|---|---|
| GET | `/api/console/users?current&pageSize&keyword` | → `{total,list:[User & {device_count}]}` |
| POST | `/api/console/users` | `{username, password, display_name?, email?, note?, is_admin?, is_active?}` |
| PUT | `/api/console/users/<id>` | 同上字段（`password` 可选，空则不改） |
| DELETE | `/api/console/users/<id>` | 禁止删除自己；返回 `{ok:true}` |

## 设备

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/console/devices?current&pageSize&keyword&status&user_id` | `status`: `online`/`offline`/空；→ `{total,list:[Device]}` |
| PUT | `/api/console/devices/<rid>/owner` | 管理员：`{user_id}` 绑定设备归属；`user_id=null` 解除 |
| DELETE | `/api/console/devices/<rid>` | 管理员：解除归属（不删遥测数据） |

`Device` = `{rid, hostname, username, os, cpu, memory, version, update_time, online:bool, owner, owner_id}`
在线判定：`update_time` 在 120 秒内。

## 地址簿

| 方法 | 路径 | 请求/说明 |
|---|---|---|
| GET | `/api/console/addressbooks` | → `{total,list:[Ab]}`（普通用户只看自己拥有的 + rule>0 共享的） |
| POST | `/api/console/addressbooks` | `{name, note?, rule?}` 管理员可带 `owner_id` |
| PUT | `/api/console/addressbooks/<guid>` | `{name?, note?, rule?}` |
| DELETE | `/api/console/addressbooks/<guid>` | — |
| GET | `/api/console/addressbooks/<guid>/peers?keyword` | → `{total,list:[AbPeer]}` |
| POST | `/api/console/addressbooks/<guid>/peers` | `{id, alias?, username?, hostname?, platform?, tags?:[], note?}` |
| PUT | `/api/console/addressbooks/<guid>/peers/<rid>` | 同上（不含 id） |
| DELETE | `/api/console/addressbooks/<guid>/peers` | `{ids:[rid,...]}` |
| GET | `/api/console/addressbooks/<guid>/tags` | → `{total,list:[{name,color}]}` |
| POST | `/api/console/addressbooks/<guid>/tags` | `{name,color}` |
| PUT | `/api/console/addressbooks/<guid>/tags/<name>` | `{new_name?, color?}` |
| DELETE | `/api/console/addressbooks/<guid>/tags` | `{names:[...]}` |

`Ab` = `{guid, name, owner, owner_id, rule, is_personal, note, peer_count, updated_at}`
`AbPeer` = `{id, alias, username, hostname, platform, tags:[], note}`
`rule` 语义（同时决定客户端可见性）：`0` 私有（只有属主在客户端可见，且按可读写下发）、`1` 只读共享、`2` 读写共享、`3` 完全控制。控制台里属主自己创建的地址簿即使 `rule=0` 也会出现在客户端的地址簿下拉列表里（接口 `/api/ab/shared/profiles` 会包含 `owner=当前用户` 的非个人地址簿，并把 return 的 rule 提升为 2，客户端据此允许增删联系人）；其他人的地址簿只有 `rule>0` 才可见。地址簿 `name` 全局唯一（重名返回 400），因为客户端按名称合并地址簿。

`color` 为 **32 位 ARGB 整数**（与客户端 Flutter `Color.value` 一致，例如青色 `0xFF00BCD4`）。控制台只接受 ARGB 或 0–11 旧调色板下标，后端会自动归一化；前端色板与客户端 `str2color2` 的 12 色一致。

## 设备分组

| 方法 | 路径 | 请求/说明 |
|---|---|---|
| GET | `/api/console/groups` | → `{total,list:[{guid,name,owner,owner_id,member_count,note}]}` |
| POST | `/api/console/groups` | `{name, note?}` |
| PUT | `/api/console/groups/<guid>` | `{name?, note?}` |
| DELETE | `/api/console/groups/<guid>` | — |
| GET | `/api/console/groups/<guid>/members` | → `{total,list:[{rid,alias,hostname}]}` |
| POST | `/api/console/groups/<guid>/members` | `{rids:[...]}` |
| DELETE | `/api/console/groups/<guid>/members` | `{rids:[...]}` |

## 日志

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/console/logs/conn?current&pageSize&keyword&start&end` | → `{total,list:[{id,from_ip,from_id,from_alias,rid,alias,conn_start,conn_end,duration,note}]}` |
| GET | `/api/console/logs/file?current&pageSize&keyword` | → `{total,list:[{id,file,remote_id,user_id,user_ip,filesize,direction,logged_at}]}` |

`start`/`end` 为 `YYYY-MM-DD`。

## 概览

`GET /api/console/stats` → 
```json
{"devices":{"total":12,"online":3},"users":{"total":4,"active":4},
 "addressbooks":{"total":5,"peers":20},
 "logs":{"conn_today":8,"file_today":1}}
```

## 前端工程约定

- 目录：`frontend/`（Vite 项目），`npm run build` 产物 `frontend/dist`
- 依赖：`vue@3`、`vue-router@4`、`tdesign-vue-next`、`tdesign-icons-vue-next`、`vite`、`@vitejs/plugin-vue`
- 开发代理：`/api` → `http://127.0.0.1:21114`
- 路由：`/console/` 用 hash 路由（`createWebHashHistory`），避免 Django 端 404
- 页面：登录、概览、设备、地址簿（主从：左列表右联系人+标签）、分组、用户、连接日志、文件日志、个人设置
- 统一处理 401 → 跳登录页；403 → `MessagePlugin.error('无权限')`
