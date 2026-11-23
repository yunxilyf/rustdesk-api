FROM node:22-bookworm-slim AS console

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 容器内置 nginx：一个 21114 端口同时提供 API/控制台/网页远控/WS 代理
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/requirements-docker.txt ./requirements-docker.txt
ARG PIP_INDEX_URL=https://pypi.org/simple/
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements-docker.txt

COPY manage.py version.py ./
COPY api/ ./api/
COPY rustdesk_server_api/ ./rustdesk_server_api/
COPY --from=console /build/static/console ./static/console/
COPY deploy/ ./deploy/
# Windows 工作区可能把 shell 脚本写成 CRLF，Linux 容器会报 “no such file or directory”；
# 构建时统一去掉 \r，脚本在 Git 中也由 .gitattributes 固定为 LF。
RUN sed -i 's/\r$//' /app/deploy/entrypoint.sh /app/deploy/install-web.sh \
    && chmod +x /app/deploy/entrypoint.sh /app/deploy/install-web.sh
RUN mkdir -p db records logs \
    && SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')" \
       python manage.py collectstatic --noinput

EXPOSE 21114

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
