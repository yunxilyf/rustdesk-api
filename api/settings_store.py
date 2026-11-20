# -*- coding: utf-8 -*-
"""运行时系统设置：数据库持久化 + 进程缓存。

环境变量作为默认值（未在后台改过时生效），管理员可在控制台切换。
"""

from django.conf import settings
from django.core.cache import cache

from api.models_pro import SystemSetting

CACHE_PREFIX = "syssetting:"
CACHE_TTL = 300


def get_setting(key, default=None):
    """读取设置；数据库不可用时回退默认值。"""
    cached = cache.get(CACHE_PREFIX + key)
    if cached is not None:
        return cached
    try:
        value = SystemSetting.objects.filter(key=key).values_list("value", flat=True).first()
    except Exception:
        return default
    if value is None:
        return default
    cache.set(CACHE_PREFIX + key, value, CACHE_TTL)
    return value


def set_setting(key, value):
    SystemSetting.objects.update_or_create(key=key, defaults={"value": "" if value is None else str(value)})
    cache.set(CACHE_PREFIX + key, "" if value is None else str(value), CACHE_TTL)


def bool_setting(key, default=False):
    raw = get_setting(key, None)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def allow_registration():
    """是否允许用户自助注册（默认取 settings.ALLOW_REGISTRATION）。"""
    return bool_setting("allow_registration", getattr(settings, "ALLOW_REGISTRATION", True))
