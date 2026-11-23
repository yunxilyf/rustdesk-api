"""OIDC（Authorization Code + PKCE）登录支持。

RustDesk 客户端的登录链路：

1. ``GET /api/login-options`` 返回 ``["oidc/<按钮名称>"]``；
2. 用户点击后客户端 ``POST /api/oidc/auth``，服务端创建 state 并返回 ``{code, url}``；
3. 浏览器打开 ``url`` 完成 IdP 认证，IdP 回调 ``/api/oidc/callback``；
4. 服务端换取 token、建立本地账号，客户端轮询 ``GET /api/oidc/auth-query`` 取回
   ``access_token`` 与用户信息。

配置全部来自环境变量（见 ``docs/oidc.md``）；未配置 issuer/client_id/client_secret
时登录选项返回空数组，客户端不会显示 OIDC 按钮。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models_pro import OidcLogin
from .models_user import UserProfile
from .settings_store import get_setting

logger = logging.getLogger(__name__)

DISCOVERY_CACHE_SECONDS = 3600
LOGIN_TTL_SECONDS = 300
HTTP_TIMEOUT_SECONDS = 8
# 客户端轮询时靠这个子串判断“还没完成”，文案不能改。
PENDING_ERROR = "No authed oidc is found"


class OidcError(Exception):
    """OIDC 配置错误或与 IdP 交互失败。"""


def _runtime(key):
    """控制台保存的运行时配置；读取失败时退回空串。"""
    try:
        return (get_setting("oidc_" + key, "") or "").strip()
    except Exception:  # noqa: BLE001 - 数据库未就绪时退回环境变量
        return ""


def config():
    """返回当前 OIDC 配置（控制台设置优先，环境变量兜底）；未配置时返回 None。"""
    issuer = (_runtime("issuer") or getattr(settings, "OIDC_ISSUER", "") or "").strip().rstrip("/")
    client_id = (_runtime("client_id") or getattr(settings, "OIDC_CLIENT_ID", "") or "").strip()
    client_secret = (_runtime("client_secret") or getattr(settings, "OIDC_CLIENT_SECRET", "") or "").strip()
    if not (issuer and client_id and client_secret):
        return None
    label = (_runtime("label") or getattr(settings, "OIDC_BUTTON_LABEL", "") or "OIDC").strip() or "OIDC"
    scopes = (getattr(settings, "OIDC_SCOPES", "") or "openid profile email").strip()
    return {
        "issuer": issuer,
        "client_id": client_id,
        "client_secret": client_secret,
        "label": label[:32],
        "scopes": scopes,
    }


def _http_json(url, data=None, headers=None):
    body = None
    request_headers = dict(headers or {})
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise OidcError("OIDC 请求失败：HTTP {} {}".format(exc.code, detail)) from exc
    except Exception as exc:  # noqa: BLE001 - 网络错误统一转成可展示的 OidcError
        raise OidcError("OIDC 请求失败：{}".format(exc)) from exc
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise OidcError("OIDC 返回内容不是 JSON") from exc


def discovery(cfg):
    """读取并缓存 OIDC discovery 文档。"""
    cache_key = "oidc:discovery:{}".format(cfg["issuer"])
    cached = cache.get(cache_key)
    if cached:
        return cached
    meta = _http_json(cfg["issuer"] + "/.well-known/openid-configuration")
    if not meta.get("authorization_endpoint") or not meta.get("token_endpoint"):
        raise OidcError("OIDC discovery 缺少 authorization_endpoint 或 token_endpoint")
    cache.set(cache_key, meta, DISCOVERY_CACHE_SECONDS)
    return meta


def redirect_uri(cfg, api_domain=""):
    """回调地址：优先 OIDC_REDIRECT_URI，否则用客户端上报的 API 域名拼接。"""
    configured = (getattr(settings, "OIDC_REDIRECT_URI", "") or "").strip()
    if configured:
        return configured
    base = (api_domain or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise OidcError("无法确定 OIDC 回调地址，请设置 OIDC_REDIRECT_URI")
    return base + "/api/oidc/callback"


def _pkce_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def authorization_url(cfg, callback, state, verifier):
    meta = discovery(cfg)
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": callback,
        "scope": cfg["scopes"],
        "state": state,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    endpoint = meta["authorization_endpoint"]
    separator = "&" if "?" in endpoint else "?"
    return endpoint + separator + urllib.parse.urlencode(params)


def exchange_code(cfg, code, callback, verifier):
    meta = discovery(cfg)
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": callback,
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
    }
    if verifier:
        payload["code_verifier"] = verifier
    return _http_json(meta["token_endpoint"], data=payload)


def _id_token_claims(token):
    """解析 id_token 的 payload；签名已由 TLS + token endpoint 保证，这里只取声明。"""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except Exception:  # noqa: BLE001 - 解析失败按无声明处理
        return {}


def fetch_claims(cfg, tokens):
    meta = discovery(cfg)
    claims = {}
    endpoint = meta.get("userinfo_endpoint")
    access_token = tokens.get("access_token") or ""
    if endpoint and access_token:
        claims.update(_http_json(endpoint, headers={"Authorization": "Bearer {}".format(access_token)}))
    if not claims.get("sub") and tokens.get("id_token"):
        claims = {**_id_token_claims(tokens["id_token"]), **claims}
    if not claims.get("sub"):
        raise OidcError("OIDC 未返回 sub 声明，无法建立账号")
    return claims


def username_from_claims(claims):
    configured = (getattr(settings, "OIDC_USERNAME_CLAIM", "") or "preferred_username").strip()
    keys = [configured, "preferred_username", "email", "name", "sub"]
    raw = ""
    for key in keys:
        if not key:
            continue
        value = claims.get(key)
        if value:
            raw = str(value)
            break
    if "@" in raw:
        raw = raw.split("@", 1)[0]
    raw = re.sub(r"[^0-9A-Za-z._-]", "", raw).strip("._-")[:40]
    return raw or "oidc-" + secrets.token_hex(3)


def _unique_username(base):
    candidate = base[:50]
    index = 1
    while UserProfile.objects.filter(username=candidate).exists():
        suffix = "-{}".format(index)
        candidate = base[: 50 - len(suffix)] + suffix
        index += 1
    return candidate


def _claim_flag(claims, key):
    """把 IdP 的布尔类 claim（true/false 或字符串）解析为 bool；缺失即 False。"""
    value = claims.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return False


def user_payload(user):
    """客户端 AuthBody.user 要求的字段；info 必须存在（Rust 侧无默认值）。"""
    return {
        "name": user.username,
        "display_name": user.display_name or user.username,
        "avatar": user.avatar or "",
        "email": user.email or "",
        "note": user.note or "",
        "status": 1 if user.status is None else int(user.status),
        "info": {},
        "is_admin": bool(user.is_admin),
        "third_auth_type": "oidc",
    }


def cleanup_expired():
    cutoff = timezone.now() - timedelta(seconds=LOGIN_TTL_SECONDS * 2)
    OidcLogin.objects.filter(created_at__lt=cutoff).delete()


def render_page(title, message, status=200):
    """回调页：给浏览器看的极简结果页。"""
    from django.http import HttpResponse
    from django.utils.html import escape

    html = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{title}</title>
<style>
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#0b1220;color:#e6edf7;font:16px/1.6 -apple-system,"Segoe UI",sans-serif}}
.card{{max-width:420px;padding:32px 36px;border-radius:16px;background:#131c2e;
box-shadow:0 18px 40px rgba(0,0,0,.35);text-align:center}}
h1{{margin:0 0 12px;font-size:20px}}p{{margin:0;color:#9fb0c9}}
</style></head><body><div class="card"><h1>{title}</h1><p>{message}</p></div></body></html>"""
    return HttpResponse(
        html.format(title=escape(title), message=escape(message)),
        status=status,
        content_type="text/html; charset=utf-8",
    )
