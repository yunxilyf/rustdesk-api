# -*- coding: utf-8 -*-
"""登录失败节流。

默认使用 Django 缓存框架的 default 别名：
- 单进程部署：LocMem（Django 本地内存），开箱即用；
- 多进程/多实例部署：设置 CACHE_URL=redis://... 并安装 django-redis，
  节流才会全局生效（见 docs/deployment.md）。

缓存键做 SHA1 摘要，避免用户名/邮箱里的特殊字符与超长键，也不把明文 IP、
用户名写进 Redis 键空间。
"""

import hashlib

from django.conf import settings
from django.core.cache import cache

KEY = "login:fail:%s"
RATE_KEY = "rate:%s"


def _trusted_proxy_count():
    explicit = getattr(settings, "TRUSTED_PROXY_COUNT", None)
    if explicit is not None:
        return max(0, int(explicit))
    return (1 if getattr(settings, "BEHIND_PROXY", False) else 0) + (
        1 if getattr(settings, "INTERNAL_PROXY", False) else 0
    )


def _client_ip(request):
    """取客户端真实 IP；按可信代理层数从 X-Forwarded-For 右侧剥离。

    从右侧按可信代理跳数取值，避免客户端伪造左侧 X-Forwarded-For 绕过限流或冒充内网 IP：
    - hops=0（直连）：忽略 X-Forwarded-For，直接取 REMOTE_ADDR；
    - 仅容器内置 nginx（INTERNAL_PROXY=1, BEHIND_PROXY=0, hops=1）：仅在 REMOTE_ADDR 为本机回环时
      信任内置 nginx 以 $remote_addr 覆盖后的 X-Forwarded-For；
    - 外层代理（BEHIND_PROXY=1）：从右数第 hops 项即外层可信代理看到的客户端 IP。
    """
    remote = request.META.get("REMOTE_ADDR", "") or ""
    explicit = getattr(settings, "TRUSTED_PROXY_COUNT", None)
    hops = _trusted_proxy_count()
    if hops > 0:
        trust_xff = (
            explicit is not None or getattr(settings, "BEHIND_PROXY", False) or remote in ("127.0.0.1", "::1", "")
        )
        if trust_xff:
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            if parts:
                return parts[-hops] if len(parts) >= hops else parts[0]
    return remote


def _key(scope, request, username):
    ip = _client_ip(request)
    identity = "%s|%s|%s" % (scope, ip, (username or "").strip().lower())
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()
    return KEY % digest


def blocked(scope, request, username):
    return (cache.get(_key(scope, request, username)) or 0) >= settings.LOGIN_MAX_ATTEMPTS


def fail(scope, request, username):
    key = _key(scope, request, username)
    if cache.add(key, 1, settings.LOGIN_LOCK_SECONDS):
        return 1
    try:
        return cache.incr(key)
    except ValueError:  # 过期后并发
        cache.add(key, 1, settings.LOGIN_LOCK_SECONDS)
        return 1


def reset(scope, request, username):
    cache.delete(_key(scope, request, username))


def _rate_key(scope, request, extra=""):
    ip = _client_ip(request)
    identity = "%s|%s|%s" % (scope, ip, extra)
    return RATE_KEY % hashlib.sha1(identity.encode("utf-8")).hexdigest()


def too_many(scope, request, limit, window, extra=""):
    """固定窗口限流：达到上限返回 True。"""
    return (cache.get(_rate_key(scope, request, extra)) or 0) >= limit


def hit(scope, request, window, extra=""):
    """记一次请求；窗口内首次写入时设置过期时间。"""
    key = _rate_key(scope, request, extra)
    if cache.add(key, 1, window):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        cache.add(key, 1, window)
        return 1
