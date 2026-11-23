# -*- coding: utf-8 -*-
"""第三方登录（GitHub / Google / 通用 OIDC）的多 provider 编排。

客户端 `GET /api/login-options` 取到的是字符串数组：第一项
`common-oidc/<json>` 携带完整按钮列表 `[{"name": "<op>"}, ...]`；其后每个
`oidc/<op>` 是给老客户端兜底的单项表示（与 lejianwen/rustdesk-api 一致）。
`POST /api/oidc/auth` 的 `op` 决定走哪个 provider，回调时按 state 反查。

账号与第三方身份的对应关系放在 api.models_pro.UserOauth（op + openid 唯一），
不再依赖 UserProfile.oidc_subject 这个单值字段；后者仅用于把历史单 IdP
部署里已绑定的账号迁移过来。
"""

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.utils import timezone

from api import oidc
from api.models_pro import OauthProvider, UserOauth
from api.models_user import UserProfile

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
GOOGLE_ISSUER = "https://accounts.google.com"
DEFAULT_SCOPES = {
    "github": "read:user user:email",
    "google": "openid profile email",
    "oidc": "openid profile email",
}
SUPPORTED_TYPES = ("github", "google", "oidc")


def _json_request(url, data=None, headers=None):
    """GET/POST 并解析 JSON；失败统一转成 oidc.OidcError 便于回调页展示。"""
    body = None
    request_headers = {"Accept": "application/json", "User-Agent": "rustdesk-api-server"}
    request_headers.update(headers or {})
    method = "GET"
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        method = "POST"
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=oidc.HTTP_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise oidc.OidcError("第三方登录请求失败：HTTP {} {}".format(exc.code, detail)) from exc
    except Exception as exc:  # noqa: BLE001 - 网络层错误对用户统一口径
        raise oidc.OidcError("第三方登录请求失败：{}".format(exc)) from exc
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise oidc.OidcError("第三方登录返回内容不是 JSON") from exc


def _legacy_provider():
    """没有数据库 provider 时，把旧的单份 OIDC 配置映射成一个 provider。"""
    cfg = oidc.config()
    if cfg is None:
        return None
    return OauthProvider(
        op=cfg["label"][:32],
        name=cfg["label"],
        oauth_type="oidc",
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        issuer=cfg["issuer"],
        scopes=cfg["scopes"],
        auto_register=bool(getattr(settings, "OIDC_AUTO_CREATE", True)),
        pkce_enable=True,
        sort=0,
        enabled=True,
    )


def providers():
    """已启用的 provider 列表。

    只有数据库里一条记录都没有时才回退到旧的单 IdP 环境变量配置：管理员在控制台
    把所有登录方式停用（或删光）后，不应该被遗留的 OIDC_* 环境变量悄悄复活。
    """
    rows = list(OauthProvider.objects.filter(enabled=True).order_by("sort", "id"))
    if rows:
        return rows
    if OauthProvider.objects.exists():
        return []
    legacy = _legacy_provider()
    return [legacy] if legacy else []


def provider_for(op):
    """按 op 取 provider；op 为空且只有一个候选时取该候选。

    客户端按钮文字取自 `login_options()` 的 `name`（默认是 `OauthProvider.name`），
    点下去会把该文字当作 `op` 回传，所以这里先按 op 精确匹配，再按显示名兜底。
    """
    rows = providers()
    if not rows:
        return None
    wanted = (op or "").strip()
    if not wanted:
        return rows[0] if len(rows) == 1 else None
    for row in rows:
        if row.op == wanted:
            return row
    matches = [row for row in rows if row.label() == wanted]
    return matches[0] if len(matches) == 1 else None


def as_config(provider):
    """把 provider 转成 oidc 模块认识的 cfg 字典。"""
    issuer = (provider.issuer or "").strip().rstrip("/")
    if not issuer and provider.oauth_type == "google":
        issuer = GOOGLE_ISSUER
    scopes = (provider.scopes or "").strip() or DEFAULT_SCOPES.get(provider.oauth_type, "")
    return {
        "issuer": issuer,
        "client_id": (provider.client_id or "").strip(),
        "client_secret": (provider.client_secret or "").strip(),
        "label": provider.label(),
        "scopes": scopes,
    }


def is_ready(provider):
    """配置是否足以发起登录（缺项时不要给用户显示按钮）。"""
    if provider.oauth_type not in SUPPORTED_TYPES:
        return False
    cfg = as_config(provider)
    if provider.oauth_type in ("oidc", "google") and not cfg["issuer"]:
        return False
    return bool(cfg["client_id"] and cfg["client_secret"])


def login_options():
    """`/api/login-options` 的响应体（数组，元素是字符串）。"""
    rows = providers()
    if not rows:
        return []
    items = [{"name": row.label()} for row in rows]
    common = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    return ["common-oidc/" + common] + ["oidc/" + row.op for row in rows]


def console_options():
    """控制台登录页可见的第三方登录方式（只暴露 op/类型/显示名，不含任何密钥）。

    `type` 供前端挑品牌图标与配色（github / google / oidc）；未配置完整的 provider
    不返回，避免用户点了按钮才看到「缺少 client_secret」的错误页。
    """
    return [{"op": row.op, "name": row.label(), "type": row.oauth_type} for row in providers() if is_ready(row)]


def _require_ready(provider):
    cfg = as_config(provider)
    if provider.oauth_type not in SUPPORTED_TYPES:
        raise oidc.OidcError("该登录方式的类型不受支持")
    if provider.oauth_type in ("oidc", "google") and not cfg["issuer"]:
        raise oidc.OidcError("该登录方式缺少 issuer 配置")
    if not cfg["client_id"] or not cfg["client_secret"]:
        raise oidc.OidcError("该登录方式缺少 client_id 或 client_secret")
    return cfg


def begin_auth(provider, api_domain):
    """生成一次登录的 state/verifier 与跳转地址。"""
    cfg = _require_ready(provider)
    callback = oidc.redirect_uri(cfg, api_domain)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64) if provider.pkce_enable else ""
    if provider.oauth_type == "github":
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": callback,
            "scope": cfg["scopes"],
            "state": state,
            "allow_signup": "true",
        }
        return state, verifier, GITHUB_AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)
    return state, verifier, oidc.authorization_url(cfg, callback, state, verifier)


def _github_profile(provider, code, callback):
    cfg = as_config(provider)
    tokens = _json_request(
        GITHUB_TOKEN_URL,
        data={
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "code": code,
            "redirect_uri": callback,
        },
    )
    access_token = tokens.get("access_token") or ""
    if not access_token:
        raise oidc.OidcError("GitHub 未返回 access_token")
    headers = {"Authorization": "Bearer {}".format(access_token)}
    profile = _json_request(GITHUB_USER_URL, headers=headers)
    openid = str(profile.get("id") or "").strip()
    if not openid:
        raise oidc.OidcError("GitHub 未返回用户 ID")
    email = (profile.get("email") or "").strip()
    # GitHub 的公开邮箱必须先通过验证才能设为 public，这里可视为已验证。
    verified = bool(email)
    if not email:
        emails = _json_request(GITHUB_EMAILS_URL, headers=headers)
        if isinstance(emails, list):
            primary = next((item for item in emails if item.get("primary")), None)
            chosen = primary or next((item for item in emails if item.get("verified")), None)
            if chosen:
                email = (chosen.get("email") or "").strip()
                verified = bool(chosen.get("verified"))
    return {
        "sub": openid,
        "email": email,
        "email_verified": verified,
        "preferred_username": (profile.get("login") or "").strip(),
        "name": (profile.get("name") or "").strip(),
        "picture": (profile.get("avatar_url") or "").strip(),
    }


def fetch_claims(provider, code, callback, verifier):
    """用授权码换回统一格式的用户信息。"""
    if provider.oauth_type == "github":
        return _github_profile(provider, code, callback)
    cfg = _require_ready(provider)
    tokens = oidc.exchange_code(cfg, code, callback, verifier)
    return oidc.fetch_claims(cfg, tokens)


def _touch_profile(user, claims):
    display = (claims.get("name") or "").strip()[:64]
    email = (claims.get("email") or "").strip()
    email_verified = oidc._claim_flag(claims, "email_verified")
    updates = []
    if display and not user.display_name:
        user.display_name = display
        updates.append("display_name")
    if email and email_verified and not user.email:
        user.email = email[:128]
        updates.append("email")
    if updates:
        user.save(update_fields=updates)


def _bind_subject(user, provider, openid):
    """把 OIDC 主体写回账号；已绑定其他主体时拒绝，避免静默改绑。"""
    if provider.oauth_type not in ("oidc", "google"):
        return
    current = (user.oidc_subject or "").strip()
    if current and current != openid:
        raise oidc.OidcError("该账号已绑定其他 OIDC 身份，请联系管理员处理。")
    if not current:
        user.oidc_subject = openid[:255]
        user.save(update_fields=["oidc_subject"])


def _create_user(provider, claims, openid):
    username = oidc._unique_username(oidc.username_from_claims(claims))
    user = UserProfile.objects.create_user(
        username=username,
        password=None,
        display_name=(claims.get("name") or "")[:64],
        email=((claims.get("email") or "").strip()[:128] if oidc._claim_flag(claims, "email_verified") else ""),
    )
    user.set_unusable_password()
    if provider.oauth_type in ("oidc", "google"):
        user.oidc_subject = openid[:255]
    user.status = 1
    user.save()
    return user


def resolve_user(provider, claims):
    """把第三方身份解析成本地账号（必要时建号）；不合法一律抛 OidcError。"""
    openid = str(claims.get("sub") or "").strip()
    if not openid:
        raise oidc.OidcError("第三方账号未返回主体标识，无法建立登录")
    link = UserOauth.objects.select_related("user").filter(op=provider.op, openid=openid).first()
    if link is not None:
        user = link.user
        if not user.is_active:
            raise oidc.OidcError("该账号已被禁用")
        _touch_profile(user, claims)
        return user

    # 历史单 IdP 部署：账号上可能已写有 oidc_subject，命中后补一条绑定记录。
    legacy = UserProfile.objects.filter(oidc_subject=openid).first() if openid else None
    if legacy is not None:
        if not legacy.is_active:
            raise oidc.OidcError("该账号已被禁用")
        UserOauth.objects.get_or_create(user=legacy, op=provider.op, openid=openid)
        _touch_profile(legacy, claims)
        return legacy

    email = (claims.get("email") or "").strip()
    email_verified = oidc._claim_flag(claims, "email_verified")
    allow_link = bool(getattr(settings, "OIDC_ALLOW_EMAIL_LINK", False))
    if email and allow_link:
        # 只有「邮箱确实命中本地账号」时才要求身份提供方已验证邮箱；否则照常走
        # 自动注册（GitHub 不保证 /user 返回的邮箱一定 verified，直接拒绝会让
        # 这类用户既不能关联也不能注册）。
        existing = UserProfile.objects.filter(email__iexact=email).order_by("id").first()
        if existing is not None:
            if not email_verified:
                raise oidc.OidcError("身份提供方未确认该邮箱归属，无法关联本地账号。")
            if not existing.is_active:
                raise oidc.OidcError("该账号已被禁用")
            if UserOauth.objects.filter(user=existing, op=provider.op).exists():
                raise oidc.OidcError("该账号已绑定其他第三方身份，请联系管理员处理。")
            _bind_subject(existing, provider, openid)
            UserOauth.objects.get_or_create(user=existing, op=provider.op, openid=openid)
            _touch_profile(existing, claims)
            return existing

    if not provider.auto_register:
        raise oidc.OidcError("该第三方账号尚未注册，请联系管理员开通。")
    from api import settings_store

    if not settings_store.allow_registration():
        # 管理员关闭自助注册后，第三方登录也不能绕过这个开关建号
        raise oidc.OidcError("管理员已关闭自助注册，无法通过第三方登录创建账号，请联系管理员开通。")
    user = _create_user(provider, claims, openid)
    UserOauth.objects.get_or_create(user=user, op=provider.op, openid=openid)
    return user


def complete_login(provider, row, code):
    """回调收尾：换 token、解析账号、签发客户端令牌。"""
    from api import client_auth

    callback = oidc.redirect_uri(as_config(provider), row.api_domain)
    claims = fetch_claims(provider, code, callback, row.code_verifier)
    user = resolve_user(provider, claims)
    token = client_auth.issue_token(user, row.rid, row.uuid)
    row.completed_at = timezone.now()
    row.access_token = token.access_token
    row.user = user
    row.save(update_fields=["completed_at", "access_token", "user"])
    return user, token


def complete_console_login(provider, row, code):
    """控制台回调收尾：换 token、解析账号；不签发客户端令牌，由视图建立会话。"""
    callback = oidc.redirect_uri(as_config(provider), row.api_domain)
    claims = fetch_claims(provider, code, callback, row.code_verifier)
    user = resolve_user(provider, claims)
    row.completed_at = timezone.now()
    row.user = user
    row.save(update_fields=["completed_at", "user"])
    return user


def public_provider(provider):
    """控制台展示用：不回传密钥。"""
    return {
        "op": provider.op,
        "name": provider.name,
        "type": provider.oauth_type,
        "issuer": provider.issuer,
        "client_id": provider.client_id,
        "scopes": provider.scopes,
        "auto_register": provider.auto_register,
        "pkce_enable": provider.pkce_enable,
        "enabled": provider.enabled,
        "sort": provider.sort,
        "has_secret": bool((provider.client_secret or "").strip()),
    }
