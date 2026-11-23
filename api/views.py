"""视图汇总：仅做 re-export，路由在 api/urls.py 中显式引用各视图。"""

from .views_api import (
    ab,
    ab_get,
    audit,
    audit_note,
    convert_filesize,
    currentUser,
    heartbeat,
    login,
    logout,
    sysinfo,
    sysinfo_ver,
)
from .views_front import index, user_action, user_logout, user_register

__all__ = [
    "ab",
    "ab_get",
    "audit",
    "audit_note",
    "convert_filesize",
    "currentUser",
    "heartbeat",
    "index",
    "login",
    "logout",
    "sysinfo",
    "sysinfo_ver",
    "user_action",
    "user_logout",
    "user_register",
]
