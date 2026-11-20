# 生产镜像：python:3.12-slim + gunicorn；静态控制台使用仓库内已构建的 static/console
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

WORKDIR /app

COPY deploy/requirements-docker.txt /app/requirements-docker.txt
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements-docker.txt

COPY . /app
RUN chmod +x /app/deploy/entrypoint.sh \
    && mkdir -p /app/db /app/records /app/logs \
    && python manage.py collectstatic --noinput >/dev/null

EXPOSE 21114

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
