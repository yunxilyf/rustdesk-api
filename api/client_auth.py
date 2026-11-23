"""Bearer authentication for the RustDesk client API."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models_user import UserProfile
from .models_work import RustDeskToken

# token_urlsafe(32) produces 43 characters. Legacy 32-character md5 tokens are
# intentionally rejected: they were predictable and are deleted by migration.
TOKEN_LENGTH = 43


def generate_token():
    return secrets.token_urlsafe(32)


def _bearer_value(request):
    header = request.headers.get("Authorization", "").strip()
    if not header:
        return ""
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()


def issue_token(user, rid, uuid):
    """为已认证用户签发/复用客户端令牌（登录与 OIDC 共用）。"""
    now = timezone.now()
    token = RustDeskToken.objects.filter(uid=user.id, rid=rid).first()
    if token is None:
        token = RustDeskToken(uid=user.id, rid=rid)
    if len(token.access_token) != TOKEN_LENGTH or token.uuid != uuid or (token.expires_at and token.expires_at <= now):
        token.access_token = generate_token()
    token.username = user.username[: RustDeskToken._meta.get_field("username").max_length]
    token.uuid = uuid
    token.expires_at = now + timedelta(seconds=settings.TOKEN_TTL_SECONDS)
    token.save()
    return token


def authenticate_client(request, *, renew=True):
    value = _bearer_value(request)
    if len(value) != TOKEN_LENGTH:
        return None, None

    now = timezone.now()
    valid = Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    token = RustDeskToken.objects.filter(valid, access_token=value).first()
    if token is None:
        return None, None

    user = UserProfile.objects.filter(pk=token.uid, is_active=True).first()
    if user is None:
        return None, None

    renew_before = now + timedelta(seconds=settings.HEARTBEAT_TOKEN_REFRESH_SECONDS)
    if renew and (token.expires_at is None or token.expires_at < renew_before):
        # 绑定读取时的 expires_at，避免管理员在两步之间把令牌改为过期后被续回。
        RustDeskToken.objects.filter(pk=token.pk, expires_at=token.expires_at).update(
            expires_at=now + timedelta(seconds=settings.TOKEN_TTL_SECONDS)
        )
    return token, user
