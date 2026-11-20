# rustdesk-api-server

<p align="center">
  <i>API server for self-hosted RustDesk (hbbs/hbbr): accounts, address books, devices, audit logs and an admin console</i>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Version-1.0.0-blueviolet.svg" />
  <img src="https://img.shields.io/badge/Python-3.12-blue.svg" />
  <img src="https://img.shields.io/badge/Django-6.1-0C4B33.svg" />
  <img src="https://img.shields.io/badge/RustDesk-1.5.x-0A5BE0.svg" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg" />
</p>

A Django implementation of the RustDesk API server, aligned with the 37 API endpoints used by
RustDesk 1.5.x clients, plus a multi-tenant admin console built with Tencent TDesign (Vue 3 + Vite).

- **Client API**: login, address books (legacy + multi-address-book), device lists, heartbeat/sysinfo,
  connection/file audit, switch grants, device deployment.
- **Admin console**: devices and ownership, address books and colored tags, device groups, users and a
  registration switch, connection/file logs, per-user data isolation.
- **Deployment**: SQLite out of the box, optional PostgreSQL / MySQL, Docker image and production guide.

## Quick start

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:21114
```

Open `http://127.0.0.1:21114/console/`; the first visit creates the initial administrator.
Point the RustDesk client's API server to `http://<host>:21114` (ID/relay servers still use hbbs/hbbr).

## Docker

```bash
cp .env.example .env
docker compose -f deploy/docker-compose.prod.yaml up -d          # pull prebuilt image
# or build locally:
docker compose -f deploy/docker-compose.prod.yaml up -d --build
```

Prebuilt multi-arch images (`linux/amd64`, `linux/arm64`):

- GHCR: `ghcr.io/yunxilyf/rustdesk-api:latest`
- Docker Hub: `yunxi666/rustdesk-api:latest`

Set `image` in `deploy/docker-compose.prod.yaml` to either one.

## Documentation

- [Client API contract](docs/client_api_contract.md)
- [Console API](docs/console_api.md)
- [Deployment guide](docs/deployment.md)
- [Testing matrix](docs/testing.md)

## Testing

```bash
python manage.py test api.tests -v 1   # unit / integration tests
node e2e/console_e2e.js               # optional browser E2E (Chrome/Chromium)
```

## Credits

- [RustDesk](https://github.com/rustdesk/rustdesk) for the open-source client and server. The API
  contracts in this project were derived from observing the behaviour of its client source code.
- The RustDesk community.

This is an independent implementation: the API service, admin console and deployment scripts were
written from scratch against the RustDesk 1.5.x client behaviour and contain no third-party
API-server code.

## License

Released under the [MIT License](LICENSE).
