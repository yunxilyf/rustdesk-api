#!/bin/sh
set -e

cd /app
mkdir -p /app/db /app/records /app/logs

echo "[entrypoint] applying database migrations ..."
python manage.py migrate --noinput

echo "[entrypoint] starting gunicorn on 0.0.0.0:${PORT:-21114}"
exec gunicorn rustdesk_server_api.wsgi:application \
    --bind "0.0.0.0:${PORT:-21114}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --threads "${WEB_THREADS:-4}" \
    --worker-class gthread \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
