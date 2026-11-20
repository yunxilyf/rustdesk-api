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


def _key(scope, request, username):
    ip = request.META.get("REMOTE_ADDR", "") or ""
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
