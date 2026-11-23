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

echo "[entrypoint] starting gunicorn on 0.0.0.0:${PORT:-21114}"
exec gunicorn rustdesk_server_api.wsgi:application \
    --bind "0.0.0.0:${PORT:-21114}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --threads "${WEB_THREADS:-4}" \
    --worker-class gthread \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
