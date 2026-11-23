#!/bin/sh
set -e

cd /app

case "$(printf '%s' "${DEBUG:-0}" | tr 'A-Z' 'a-z')" in
    1|true|yes|on) ;;
    *)
        if [ -z "${SECRET_KEY:-}" ]; then
            echo "[entrypoint] 缺少 SECRET_KEY：请在 .env 中设置至少 50 位的随机字符串。" >&2
            echo "[entrypoint] 生成：python -c \"import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(50))\"" >&2
            exit 1
        fi
        ;;
esac

mkdir -p /app/db /app/records /app/logs

echo "[entrypoint] applying database migrations ..."
python manage.py migrate --noinput

# 数据库缓存表（CACHE_BACKEND=db 时用于多 worker 共享限流计数）；已存在时命令会自动跳过。
python manage.py createcachetable

# 网页远控静态包：镜像内自带 deploy/web/rustdesk-web-*.tar.gz。
# 首次启动解压到挂载的 WEBROOT（默认 /app/webroot），已存在则跳过；
# WEBCLIENT_FORCE_UPDATE=1 可强制覆盖。
WEBROOT="${WEBROOT:-/app/webroot}"
if [ "${WEBCLIENT_AUTO_INSTALL:-1}" = "1" ]; then
    PKG="$(ls /app/deploy/web/rustdesk-web-*.tar.gz 2>/dev/null | head -n 1 || true)"
    if [ -n "$PKG" ]; then
        if [ "${WEBCLIENT_FORCE_UPDATE:-0}" = "1" ] || [ ! -f "$WEBROOT/web/index.html" ]; then
            echo "[entrypoint] installing web client from $PKG -> $WEBROOT/web"
            TMP="$WEBROOT/.web.new.$$"
            rm -rf "$TMP"
            mkdir -p "$TMP"
            tar --no-same-owner --no-same-permissions -xzf "$PKG" -C "$TMP"
            chmod -R u=rwX,go=rX "$TMP"
            rm -rf "$WEBROOT/.web.old"
            if [ -d "$WEBROOT/web" ]; then
                mv "$WEBROOT/web" "$WEBROOT/.web.old"
            fi
            mv "$TMP" "$WEBROOT/web"
        fi
    fi
fi

APP_PORT="${PORT:-21114}"
API_PORT="${API_PORT:-21115}"
export HBBS_WS="${HBBS_WS:-127.0.0.1:21118}"
export HBBR_WS="${HBBR_WS:-127.0.0.1:21119}"
# 告知 Django 前方有容器内置 nginx，使限流与 /api/health 按真实客户端 IP 判断。
export INTERNAL_PROXY=1

# 校验环境变量并渲染容器内置 nginx：对外一个端口同时提供 API、控制台、网页远控与 WebSocket 代理。
python - <<'PY'
import os
import re
import sys

def valid_port(name, val):
    if not re.fullmatch(r"[0-9]{1,5}", val) or not (1 <= int(val) <= 65535):
        sys.exit(f"[entrypoint] 非法的 {name}：{val!r}（需为 1~65535 整数）")
    return val

def valid_hostport(name, val):
    if not re.fullmatch(r"(?:[A-Za-z0-9._-]+|\[[0-9A-Fa-f:]+\])(?::[0-9]{1,5})?", val):
        sys.exit(f"[entrypoint] 非法的 {name}：{val!r}")
    return val

def valid_path(name, val):
    if not val.startswith("/") or not re.fullmatch(r"/[A-Za-z0-9._/-]*", val) or ".." in val.split("/"):
        sys.exit(f"[entrypoint] 非法的 {name}：{val!r}")
    return val

behind_proxy = os.environ.get("BEHIND_PROXY", "").strip().lower() in ("1", "true", "yes", "on")
tpl = open("/app/deploy/nginx.conf.template", encoding="utf-8").read()
values = {
    "__APP_PORT__": valid_port("PORT", os.environ.get("PORT", "21114").strip()),
    "__API_PORT__": valid_port("API_PORT", os.environ.get("API_PORT", "21115").strip()),
    "__WEBROOT__": valid_path("WEBROOT", os.environ.get("WEBROOT", "/app/webroot").strip()),
    "__HBBS_WS__": valid_hostport("HBBS_WS", os.environ.get("HBBS_WS", "127.0.0.1:21118").strip()),
    "__HBBR_WS__": valid_hostport("HBBR_WS", os.environ.get("HBBR_WS", "127.0.0.1:21119").strip()),
    "__XFF_VALUE__": "$proxy_add_x_forwarded_for" if behind_proxy else "$remote_addr",
    "__PROTO_DEFAULT__": "$http_x_forwarded_proto" if behind_proxy else "$scheme",
}
for key, value in values.items():
    tpl = tpl.replace(key, value)
with open("/etc/nginx/conf.d/default.conf", "w", encoding="utf-8") as fh:
    fh.write(tpl)
PY
rm -f /etc/nginx/sites-enabled/default
nginx -t
nginx
echo "[entrypoint] nginx on 0.0.0.0:${APP_PORT}, gunicorn on 127.0.0.1:${API_PORT}"

exec gunicorn rustdesk_server_api.wsgi:application \
    --bind "127.0.0.1:${API_PORT}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --threads "${WEB_THREADS:-4}" \
    --worker-class gthread \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
