#!/usr/bin/env bash
# 安装预构建 Web 客户端：备份旧目录并解压到 <webroot>/web
set -euo pipefail

WEBROOT="${1:-/opt/rustdesk-api/webroot}"
PKG="${2:-$(cd "$(dirname "$0")" && pwd)/web/rustdesk-web-1.5.3.tar.gz}"

[[ -f "$PKG" ]] || { echo "找不到安装包：$PKG" >&2; exit 1; }
mkdir -p "$WEBROOT"

if [[ -d "$WEBROOT/web" ]]; then
  BACKUP="$WEBROOT/web.bak-$(date +%Y%m%d%H%M%S)"
  mv "$WEBROOT/web" "$BACKUP"
  echo "已备份旧站点到 $BACKUP"
fi

mkdir -p "$WEBROOT/web"
tar --no-same-owner --no-same-permissions -xzf "$PKG" -C "$WEBROOT/web"
chmod -R u=rwX,go=rX "$WEBROOT/web"
echo "已安装到 $WEBROOT/web"
