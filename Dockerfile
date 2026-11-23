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

COPY deploy/requirements-docker.txt ./requirements-docker.txt
ARG PIP_INDEX_URL=https://pypi.org/simple/
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements-docker.txt

COPY manage.py version.py ./
COPY api/ ./api/
COPY rustdesk_server_api/ ./rustdesk_server_api/
COPY --from=console /build/static/console ./static/console/
COPY --chmod=755 deploy/entrypoint.sh ./deploy/entrypoint.sh
RUN mkdir -p db records logs \
    && SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')" \
       python manage.py collectstatic --noinput

EXPOSE 21114

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
