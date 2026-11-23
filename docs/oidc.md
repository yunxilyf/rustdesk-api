# 第三方登录（OIDC / Google / GitHub）

服务端支持**多种第三方登录方式并存**：可以是任意标准 OIDC 提供方（Keycloak、Authentik、
Microsoft Entra ID、Okta、Auth0 等），也可以直接接 Google 或 GitHub。客户端登录页会把
所有启用的方式渲染成并列按钮；点击后浏览器打开提供方的登录页，认证完成后自动回到客户端。

| 类型 | 协议 | 需要 Issuer | 说明 |
|---|---|---|---|
| `oidc` | OIDC 授权码 + PKCE | 是 | 任意兼容 OIDC 的 IdP，走 discovery |
| `google` | OIDC 授权码 + PKCE | 否（默认 `https://accounts.google.com`） | Google Workspace / 个人 Google 账号 |
| `github` | OAuth2 授权码 | 否 | GitHub 不是标准 OIDC，服务端直接调 GitHub API 取用户信息 |

## 1. 在提供方创建客户端

所有类型都使用同一个回调地址（Redirect URI / Authorization callback URL）：

```text
https://<你的 API 域名>/api/oidc/callback
```

本地调试可以是 `http://127.0.0.1:21114/api/oidc/callback`。

各类型需要的 scope（留空即用默认值）：

| 类型 | 默认 scope |
|---|---|
| `oidc` | `openid profile email` |
| `google` | `openid profile email` |
| `github` | `read:user user:email` |

> 对 `oidc`，Issuer 是 discovery 文档的根地址，例如 Keycloak 的
> `https://id.example.com/realms/main`，服务端会请求
> `<issuer>/.well-known/openid-configuration`。

## 2. 在控制台配置

仅**管理员**可见、可修改（普通用户读取 `/api/console/settings` 不会返回任何登录方式配置，写入返回 403）。

以管理员登录 `/console/` → 「个人设置」→「第三方登录」，点「添加登录方式」，每个方式包含：

| 字段 | 说明 |
|---|---|
| 类型 | 通用 OIDC / Google / GitHub |
| 标识（op） | 服务端内部标识，1–32 字符（字母、数字、下划线、短横线），不可重复；保存后不可修改（它参与账号绑定，改标识等于换一个登录方式） |
| 按钮名称 | 客户端登录页显示的按钮文字，默认为标识 |
| 排序 | 数字，小的排前面 |
| Issuer | 仅 `oidc` 必填，必须是 http(s) URL，末尾不带 `/` |
| Client ID | 提供方分配的客户端 ID |
| Client Secret | 提供方分配的密钥；已保存时留空表示不修改 |
| Scopes | 可选，留空用默认值 |
| 自动注册 / PKCE | 默认开启；GitHub 无 PKCE，可忽略 |

保存是**整表同步**：提交列表里没有的登录方式会被删除；每张卡片右上角的开关控制该方式是否启用。

保存后立即生效，客户端重新打开登录框时 `GET /api/login-options` 返回：

```json
["common-oidc/[{\"name\":\"公司 SSO\"},{\"name\":\"GitHub\"}]", "oidc/company", "oidc/github"]
```

- 第一项是完整按钮列表，新客户端（RustDesk 1.5.x）据此一次性渲染全部按钮，并把这些
  `name` 原样作为 `op` 回传给 `/api/oidc/auth`；
- 其后的 `oidc/<op>` 只用于兼容只认单元素的旧客户端。

> 服务端解析 `op` 时先按标识精确匹配，再按**按钮名称**唯一匹配，所以按钮名称可以起中文名。

回调地址优先读 `OIDC_REDIRECT_URI`；未设置时按客户端上报的 API 域名拼接。生产环境建议显式设置，
避免反向代理改写 Host 导致控制台提示与实际回调不一致。

### 用环境变量配置单一 IdP（兼容旧部署）

数据库里没有任何登录方式时，服务端会回退到下面这组环境变量（控制台配置优先）：

```dotenv
OIDC_ISSUER=https://id.example.com/realms/main
OIDC_CLIENT_ID=rustdesk-api
OIDC_CLIENT_SECRET=your-client-secret
OIDC_BUTTON_LABEL=公司 SSO
OIDC_SCOPES=openid profile email
# 固定回调地址（不填则用客户端上报的 API 域名拼接）
# OIDC_REDIRECT_URI=https://rustdeskapi.example.com/api/oidc/callback
# 是否自动创建本地账号（默认 true）
# OIDC_AUTO_CREATE=1
# 是否允许按邮箱关联已有账号（默认 false，开启前请确认 IdP 会校验邮箱）
# OIDC_ALLOW_EMAIL_LINK=0
```

## 3. 账号映射

- 每个第三方身份记录在 `UserOauth`（`op` + `openid` 唯一），一个本地账号可绑定多个提供方；
- `openid` 取提供方的稳定主体标识：OIDC/Google 是 `sub`，GitHub 是用户数字 `id`；
- 用户名依次取 `OIDC_USERNAME_CLAIM`（默认 `preferred_username`）、`email`、`name`、`sub`，
  去掉邮箱域名并过滤非法字符；重复时自动加 `-1`、`-2` 后缀；
- 首次登录默认创建普通账号（自动注册开启时）；管理员可在「用户」页调整角色；
  自动建号需要同时满足两个条件：该登录方式开了 `auto_register`，且控制台「允许注册」开关为开；
  管理员关闭注册后，任何第三方授权都只能登录已绑定/已存在的账号；
- 不会自动把第三方账号关联到同邮箱的本地账号，除非显式开启 `OIDC_ALLOW_EMAIL_LINK`，
  且提供方明确声明邮箱已通过验证（`email_verified`）；
- 邮箱**未**通过验证时只是不能关联到已有账号，若该身份还没有本地账号，仍按上面的规则自动建号，
  且不会把该邮箱写进账号资料；
- 历史单 IdP 部署里写在 `UserProfile.oidc_subject` 的主体仍可命中并自动补一条绑定记录；
  已绑定其他主体时会拒绝登录而不是静默改绑。

### 控制台登录

配置好登录方式后，控制台登录页会自动出现「或使用第三方账号」按钮（数据来自
`GET /api/console/login-options`），点击后跳 `GET /api/oidc/console/auth?op=<op>`：

1. 服务端生成 state（+PKCE），把这次握手记成 `OidcLogin(flow=console)`，同时给浏览器种一个
   HttpOnly 的短效 `oidc_console_state` cookie，然后 302 到提供方；
2. 提供方回调 `/api/oidc/callback`，服务端先核对 state 与 cookie 是否同源同浏览器，
   再换 token、解析账号（不一致直接 400，避免有人把自己的登录链接发给别人）；
3. 成功后**建立控制台 Session** 并 302 回 `/console/`（当入口带白名单参数 `next=/web/` 时直接 302 回 `/web/`），删掉这条 `OidcLogin` 并清除 cookie；
   失败则显示原因（未验证邮箱、账号被禁用、未注册等）。

与客户端流程共用同一份登录方式配置；控制台流程不签发 RustDesk 客户端令牌，
也不会把 token 回传给浏览器。

## 4. 安全说明

- 登录方式配置仅管理员可读写；`client_secret` 保存在数据库（明文），请限制数据库与备份的访问权限；
  更严格的环境建议只用环境变量配置，不在控制台填写 secret；
- `POST /api/oidc/auth` 有按 IP 的每小时限流（`OIDC_MAX_PER_HOUR`，默认 60）；登录 state 5 分钟过期且一次性使用；
- 使用 PKCE（S256）+ state（GitHub 分支只用 state，GitHub 不支持 PKCE）；
- 生产必须使用 HTTPS；回调地址必须与提供方登记值完全一致；
- 邮箱归属未经提供方确认时不会关联本地账号；已停用账号无法通过第三方登录；
- 登录成功后签发与密码登录相同的 30 天滑动 token，改密/禁用账号会删除其 token；
- 控制台登录用 IDP 回调建立 Django Session（`auth_login`），会话 cookie 与其他登录方式一致；
  state 还额外绑定一个 HttpOnly cookie，回调时校验，防止登录 CSRF（把攻击者的账号登进受害者浏览器）；
  关闭「允许注册」后第三方授权无法新建账号，只能登录已存在的账号；
- 登录方式全部停用后，服务端不会回退到 `OIDC_*` 环境变量（只有数据库里一条配置都没有时才回退），
  避免管理员停用后按钮又「复活」。

## 5. 排查

| 现象 | 原因 |
|---|---|
| 客户端没有第三方按钮 | `login-options` 返回 `[]`：没有任何启用的登录方式，或 `oidc` 缺 issuer / client_id / client_secret |
| 控制台登录页没有第三方按钮 | 同上；另外确认浏览器能访问 `/api/console/login-options`（它匿名可读，401/403 说明被反向代理拦了） |
| 提示「登录方式不存在或已停用」 | 客户端回传的 `op` 与标识、按钮名称都不匹配，或该方式被停用/删除 |
| 浏览器报 `redirect_uri_mismatch` | 提供方登记的回调地址与 `/api/oidc/callback` 不一致（协议/域名/端口都要一致） |
| 客户端一直等待 | 浏览器没有完成回调，或 `/api/oidc/callback` 无法从公网访问 |
| 回调页提示「无法完成登录」 | 查看服务端日志：token 交换失败、userinfo 缺 `sub`、或关闭了自动注册 |
| 提示「管理员已关闭自助注册」 | 该第三方身份还没有本地账号，需管理员在「用户」页建号并绑定，或临时打开「允许注册」 |
| 提示「未确认该邮箱归属」 | 开启了邮箱关联，且该邮箱已属于某个本地账号，但提供方未返回 `email_verified=true`；换个未注册过的邮箱则可以直接建号 |
| 提示「登录请求与当前浏览器不匹配」 | 回调不是在发起登录的那个浏览器里打开的（或 cookie 被清掉），回控制台登录页重新点一次 |
| 提示「已绑定其他 OIDC 身份」 | 该本地账号已绑定另一个主体，需管理员先解绑 |
| 登录后没有账号 | 自动注册关闭，且该第三方身份未绑定任何本地账号 |

服务端日志会记录 `OIDC auth start failed` / `OIDC callback rejected` / `OIDC callback failed`
及具体原因（不含 secret）。
