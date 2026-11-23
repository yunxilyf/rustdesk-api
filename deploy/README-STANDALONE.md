# 独立运行版（Linux / Windows）

这是打包好的免安装服务端，不需要安装 Python、Docker 或数据库。

## 运行

**Linux**

```bash
tar -xzf rustdesk-api-server-linux-x86_64.tar.gz
cd rustdesk-api-server
chmod +x rustdesk-api-server
./rustdesk-api-server
```

**Windows**

解压 zip，进入 `rustdesk-api-server` 目录，双击 `rustdesk-api-server.exe`，或在命令行运行：

```bat
cd rustdesk-api-server
rustdesk-api-server.exe
```

启动后终端会打印访问地址，例如：

```
================================================================
  RustDesk API Server 已启动
  控制台（本机）：  http://127.0.0.1:21114/console/
  控制台（局域网）：http://192.168.1.20:21114/console/
  健康检查：        http://127.0.0.1:21114/api/health
  数据目录：        /path/to/rustdesk-api-server/data
  按 Ctrl+C 停止服务
================================================================
```

- 用浏览器打开上面的控制台地址（服务器无桌面环境时不会自动拉起浏览器，复制地址即可）。
- 客户端里把「API 服务器」填成 `http://<这台机器的IP>:21114`
- 首次启动会自动创建 `data/` 目录（数据库、录像、日志）并生成 `data/secret_key`，无需任何配置。

## 可选配置

在可执行文件旁新建 `.env`（参考包内的 `.env.example`），常用项：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `PORT` | 监听端口 | `21114` |
| `DATA_DIR` | 数据目录 | 可执行文件旁的 `data/` |
| `ALLOWED_HOSTS` | 允许的域名/IP，逗号分隔 | `*` |
| `SECRET_KEY` | 密钥，不填则自动生成并保存到 `data/secret_key` | 自动生成 |
| `ALLOW_REGISTRATION` | 是否允许自助注册 | `0` |
| `TOKEN_TTL_SECONDS` | 客户端令牌有效期（滑动） | 30 天 |
| `HTTPS` / `BEHIND_PROXY` | 放在 HTTPS 反向代理后时设为 `1` | `0` |

如需关闭自动打开浏览器，设置 `OPEN_BROWSER=0`。修改端口示例：

```bash
PORT=8080 ./rustdesk-api-server
```

## 安全提示

- 首次初始化控制台需要终端打印的「初始化密钥」；密钥保存在 `data/setup_token`（权限 0600），初始化完成后可以删除该文件。
- 程序默认监听 `0.0.0.0` 以便局域网客户端连接；如果要暴露到公网，请放在 HTTPS 反向代理之后，并设置 `HTTPS=1`、`BEHIND_PROXY=1`，把 `ALLOWED_HOSTS` 限制为实际域名。
- `data/` 目录包含数据库、日志与 `secret_key`，请限制目录权限并做好备份。
- 默认使用 SQLite，适合单机 / 小团队；多实例部署请改用 PostgreSQL（见 `docs/deployment.md`）。

## 备份与升级

- 备份：停止程序后复制整个 `data/` 目录即可。
- 升级：下载新版本可执行文件覆盖旧的，`data/` 保持不变；启动时会自动执行数据库迁移。

## 说明

- 打包版使用 SQLite，适合单机 / 小团队；设备规模较大时建议改用 Docker + PostgreSQL（见仓库 `docs/deployment.md`）。
- 如果需要开机自启，Linux 可用 systemd，Windows 可用「任务计划程序」触发这个可执行文件。
