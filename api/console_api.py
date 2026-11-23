# -*- coding: utf-8 -*-
"""控制台（TDesign 前端）使用的 JSON API。

挂载点：/api/console/*
认证：Django Session（前端 fetch 带 credentials: 'include'）。
权限：is_admin 看全部；普通用户只看自己名下的设备（按 rid 归属）、
自己的地址簿与共享地址簿、以及这些设备相关的日志。
"""

import datetime
import json
import os
import re
import urllib.request
import uuid as uuidlib

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.http import FileResponse, HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import ensure_csrf_cookie

from api import throttle, views_pro
from api.models_pro import (
    AddressBook,
    AddressBookPeer,
    AddressBookTag,
    DeviceGroup,
    DeviceGroupPeer,
    OauthProvider,
    SystemSetting,
)
from api.models_user import UserProfile
from api.models_work import ConnLog, FileLog, RustDesDevice, RustDeskPeer, RustDeskToken
from api.tag_colors import normalize_color
from api.webclient import clear_webclient_cookie, revoke_web_token
from version import APP_VERSION


def password_problem(password, user=None):
    """返回密码强度问题；通过返回 None。可用 PASSWORD_VALIDATION=0 关闭。"""
    if not getattr(settings, "PASSWORD_VALIDATION", True):
        return None
    try:
        validate_password(password, user)
    except ValidationError as exc:
        return " ".join(exc.messages)
    return None


# 「在线」判定窗口。必须显著大于心跳写库的节流间隔（默认 120 秒），
# 否则设备两次写库之间会被判成离线：客户端 15 秒一次心跳，但 update_time
# 最多每 HEARTBEAT_DEVICE_TOUCH_SECONDS 秒才落库一次。
ONLINE_SECONDS = getattr(settings, "DEVICE_ONLINE_SECONDS", 300)


# ---------------------------------------------------------------- 基础工具
def _json_body(request):
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _fail(msg, status=400):
    return JsonResponse({"ok": False, "msg": msg}, status=status)


def _ok(**kw):
    payload = {"ok": True}
    payload.update(kw)
    return JsonResponse(payload)


def _fmt(dt):
    if not dt:
        return ""
    try:
        return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def _current_user(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    return user


def login_required_json(view):
    def wrapper(request, *args, **kwargs):
        user = _current_user(request)
        if user is None:
            return _fail("未登录", 401)
        if not user.is_active:
            return _fail("账号已禁用", 403)
        request.console_user = user
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


def admin_required_json(view):
    @login_required_json
    def wrapper(request, *args, **kwargs):
        if not request.console_user.is_admin:
            return _fail("无权限", 403)
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


def _page_params(request):
    try:
        current = int(request.GET.get("current", 1))
    except Exception:
        current = 1
    try:
        size = int(request.GET.get("pageSize", 20))
    except Exception:
        size = 20
    current = max(current, 1)
    size = min(max(size, 1), 200)
    return current, size


def _paginate(request, queryset, serializer):
    current, size = _page_params(request)
    total = queryset.count()
    start = (current - 1) * size
    rows = [serializer(obj) for obj in queryset[start : start + size]]
    return JsonResponse({"total": total, "list": rows})


def _my_rids(user):
    """返回用户名下的 rid 列表；管理员返回 None 表示不限。"""
    if user.is_admin:
        return None
    return views_pro.owned_device_ids(user)


def _device_owner_map():
    """rid -> (user_id, username)，以 RustDeskPeer 绑定关系为准。"""
    mapping = {}
    for peer in RustDeskPeer.objects.all().only("rid", "uid"):
        if peer.uid and peer.rid not in mapping:
            mapping[peer.rid] = peer.uid
    users = {str(u.id): u.username for u in UserProfile.objects.all().only("id", "username")}
    return {rid: (uid, users.get(str(uid), "")) for rid, uid in mapping.items()}


# ---------------------------------------------------------------- 序列化
def user_json(user, with_count=False):
    data = {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or "",
        "email": user.email or "",
        "avatar": user.avatar or "",
        "note": user.note or "",
        "is_admin": bool(user.is_admin),
        "is_active": bool(user.is_active),
        "status": user.status if user.status is not None else 1,
    }
    if with_count:
        data["device_count"] = RustDeskPeer.objects.filter(uid=str(user.id)).count()
    return data


def _online(device):
    if not device.update_time:
        return False
    return (timezone.now() - device.update_time).total_seconds() <= ONLINE_SECONDS


def device_json(device, owners=None):
    owners = owners if owners is not None else {}
    owner_id, owner_name = owners.get(device.rid, (None, ""))
    return {
        "rid": device.rid,
        "hostname": device.hostname,
        "username": device.username,
        "os": device.os,
        "cpu": device.cpu,
        "memory": device.memory,
        "version": device.version,
        "update_time": _fmt(device.update_time),
        "online": _online(device),
        "owner": owner_name,
        "owner_id": int(owner_id) if owner_id not in (None, "") else None,
    }


def ab_json(ab, with_count=True):
    data = {
        "guid": ab.guid,
        "name": ab.name,
        "owner": ab.owner.username if ab.owner else "",
        "owner_id": ab.owner_id,
        "rule": ab.rule,
        "is_personal": ab.is_personal,
        "note": ab.note,
        "updated_at": _fmt(ab.updated_at),
    }
    if with_count:
        data["peer_count"] = ab.peers.count()
    return data


def ab_peer_json(peer, dev_info=None):
    """联系人行；联系人自身没存主机名/平台时用设备上报信息补全。

    客户端旧版推送地址簿只带 id/hash，`AddressBookPeer.hostname/platform`
    常为空，但 `/api/sysinfo` 里其实有这些数据，展示时兜底即可。
    """
    tags = [t for t in (peer.tags or "").split(",") if t]
    info = dev_info or {}
    return {
        "id": peer.rid,
        "alias": peer.alias,
        "username": peer.username or info.get("username", ""),
        "hostname": peer.hostname or info.get("hostname", ""),
        "platform": peer.platform or info.get("platform", ""),
        "tags": tags,
        "note": peer.note,
        # 共享地址簿里客户端保存的连接密码；只回是否设置，绝不回明文。
        "has_password": bool(peer.password),
    }


def tag_json(tag):
    return {"name": tag.name, "color": normalize_color(tag.color, tag.name)}


def group_json(group):
    return {
        "guid": group.guid,
        "name": group.name,
        "owner": group.owner.username if group.owner else "",
        "owner_id": group.owner_id,
        "member_count": group.members.count(),
        "note": group.note,
    }


# ---------------------------------------------------------------- 认证
@ensure_csrf_cookie
def setup(request):
    """仅允许持有部署方初始化密钥的人创建首个管理员。"""
    from api.settings_store import allow_registration

    setup_token = settings.WEB_SETUP_TOKEN
    setup_enabled = len(setup_token) >= 32
    needs_setup = not UserProfile.objects.exists()
    if request.method == "GET":
        return JsonResponse(
            {
                "ok": True,
                "needs_setup": needs_setup,
                "web_setup_enabled": setup_enabled and needs_setup,
                "allow_registration": allow_registration(),
            }
        )
    if request.method != "POST":
        return _fail("请求方式错误", 405)
    if not needs_setup:
        return _fail("系统已初始化", 403)
    if throttle.too_many("setup", request, settings.SETUP_MAX_PER_HOUR, 3600):
        return _fail("尝试次数过多，请稍后再试", 429)
    data = _json_body(request)
    provided_token = data.get("setup_token")
    if (
        not setup_enabled
        or not isinstance(provided_token, str)
        or not constant_time_compare(provided_token, setup_token)
    ):
        throttle.hit("setup", request, 3600)
        return _fail("需要有效的部署初始化密钥", 403)
    username = data.get("username") or ""
    password = data.get("password") or ""
    if not isinstance(username, str) or not isinstance(password, str):
        return _fail("用户名或密码格式错误")
    username = username.strip()
    if not 3 <= len(username) <= 50 or len(password) < 8:
        return _fail("用户名长度需在 3~50 位之间，密码至少 8 位")
    problem = password_problem(password, UserProfile(username=username))
    if problem:
        return _fail(problem)
    display_name = data.get("display_name") or username
    if not isinstance(display_name, str) or len(display_name) > 64:
        return _fail("显示名最多 64 个字符")

    with transaction.atomic():
        _, claimed = SystemSetting.objects.get_or_create(key="web_setup_completed")
        if not claimed or UserProfile.objects.exists():
            return _fail("系统已初始化", 403)
        user = UserProfile.objects.create_superuser(username=username, password=password)
        user.display_name = display_name
        user.save(update_fields=["display_name"])
    auth_login(request, user)
    return JsonResponse({"ok": True, "user": user_json(user)})


def register(request):
    """自助注册（登录页入口，受「允许注册」开关控制）。"""
    if request.method != "POST":
        return _fail("请求方式错误", 405)
    from api.settings_store import allow_registration

    if not allow_registration():
        return _fail("当前未开放注册，请联系管理员")
    if UserProfile.objects.count() == 0:
        return _fail("系统尚未初始化，请先创建管理员")
    if throttle.too_many("register", request, settings.REGISTER_MAX_PER_HOUR, 3600):
        return _fail("注册过于频繁，请稍后再试", 429)
    throttle.hit("register", request, 3600)
    data = _json_body(request)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if len(username) < 3 or len(username) > 50:
        return _fail("用户名长度需在 3~50 位之间")
    if len(password) < 8:
        return _fail("密码至少 8 位")
    problem = password_problem(password)
    if problem:
        return _fail(problem)
    if UserProfile.objects.filter(username=username).exists():
        return _fail("用户名已存在")
    user = UserProfile.objects.create_user(username=username, password=password)
    user.display_name = username
    user.save(update_fields=["display_name"])
    return JsonResponse({"ok": True, "user": user_json(user)})


def console_login(request):
    if request.method != "POST":
        return _fail("请求方式错误", 405)
    data = _json_body(request)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return _fail("请输入用户名和密码")
    if throttle.blocked("console", request, username):
        return _fail("尝试次数过多，请稍后再试", 429)
    user = authenticate(request, username=username, password=password)
    if user is None:
        throttle.fail("console", request, username)
        return _fail("用户名或密码错误")
    throttle.reset("console", request, username)
    if not user.is_active:
        return _fail("账号已被禁用")
    auth_login(request, user)
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    return JsonResponse({"ok": True, "user": user_json(user)})


def console_login_options(request):
    """GET /api/console/login-options：登录页可用的第三方登录方式（匿名可读）。

    只回 op 与显示名，前端拼成 `/api/oidc/console/auth?op=<op>` 的跳转链接，
    不放 issuer / client_id / secret 等配置细节。
    """
    from api import oauth

    if request.method != "GET":
        return _fail("请求方式错误", 405)
    return JsonResponse({"ok": True, "providers": oauth.console_options()})


def console_logout(request):
    if request.method != "POST":
        return _fail("请求方式错误", 405)
    revoke_web_token(request)
    auth_logout(request)
    return clear_webclient_cookie(_ok())


@login_required_json
def console_me(request):
    user = request.console_user
    if request.method in ("PATCH", "PUT", "POST"):
        return _update_own_profile(request, user)
    return JsonResponse({"user": user_json(user)})


def _update_own_profile(request, user):
    """本人修改显示名与邮箱（用户名/角色/状态不可自改）。"""
    data = _json_body(request)
    if not isinstance(data, dict):
        return _fail("请求体格式错误")
    fields = []
    if "display_name" in data:
        name = (data.get("display_name") or "").strip()
        if len(name) > 64:
            return _fail("显示名最多 64 个字符")
        user.display_name = name or user.username
        fields.append("display_name")
    if "email" in data:
        email = (data.get("email") or "").strip()
        if email:
            if len(email) > 254 or "@" not in email:
                return _fail("邮箱格式不正确")
            domain = email.rsplit("@", 1)[-1]
            if "." not in domain:
                return _fail("邮箱格式不正确")
        user.email = email
        fields.append("email")
    if not fields:
        return _fail("没有需要更新的字段")
    user.save(update_fields=fields)
    return JsonResponse({"ok": True, "user": user_json(user)})


GITHUB_REPO = "yunxilyf/rustdesk-api"
LATEST_RELEASE_CACHE = "console:latest-release"
LATEST_RELEASE_TTL = 600


def _semver(value):
    """把 v1.2.3 / 1.2.3 转成可比较的元组。"""
    numbers = re.findall(r"\d+", (value or "").lstrip("v"))
    return tuple(int(n) for n in numbers[:3]) or (0,)


def _latest_release():
    """读取 GitHub 最新 Release；失败时返回带 error 的结果并缓存，避免频繁重试。"""
    cached = cache.get(LATEST_RELEASE_CACHE)
    if cached is not None:
        return cached
    result = {"tag": "", "url": "", "error": ""}
    try:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "rustdesk-api-console",
            },
        )
        with urllib.request.urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result["tag"] = (payload.get("tag_name") or "").strip()
        release_url = (payload.get("html_url") or "").strip()
        # 只接受 GitHub 的 https 链接，避免把不可信 scheme 塞进前端 href。
        result["url"] = release_url if release_url.startswith("https://github.com/") else ""
    except Exception as exc:  # 网络不可达时不影响控制台其它功能
        result["error"] = str(exc)[:200]
    cache.set(LATEST_RELEASE_CACHE, result, LATEST_RELEASE_TTL)
    return result


@login_required_json
def console_version(request):
    """返回当前版本，并尝试检查 GitHub 上是否有更新（结果缓存 10 分钟）。"""
    if request.method != "GET":
        return _fail("请求方式错误", status=405)
    latest = _latest_release()
    current = APP_VERSION.lstrip("v")
    latest_tag = latest["tag"].lstrip("v")
    update_available = bool(latest_tag) and _semver(latest_tag) > _semver(current)
    return JsonResponse(
        {
            "ok": True,
            "version": APP_VERSION,
            "latest": latest["tag"],
            "update_available": update_available,
            "release_url": latest["url"],
            "error": latest["error"],
        }
    )


@login_required_json
@transaction.atomic
def console_password(request):
    if request.method != "PUT":
        return _fail("请求方式错误", 405)
    data = _json_body(request)
    user = request.console_user
    if not user.check_password(data.get("old") or ""):
        return _fail("原密码错误")
    new = data.get("password") or ""
    if len(new) < 8:
        return _fail("新密码至少 8 位")
    problem = password_problem(new, user)
    if problem:
        return _fail(problem)
    user.set_password(new)
    user.save(update_fields=["password"])
    RustDeskToken.objects.filter(uid=user.pk).delete()
    return _ok()


# ---------------------------------------------------------------- 用户
@admin_required_json
def users(request):
    if request.method == "GET":
        qs = UserProfile.objects.all().order_by("id")
        keyword = (request.GET.get("keyword") or "").strip()
        if keyword:
            qs = qs.filter(
                Q(username__icontains=keyword) | Q(display_name__icontains=keyword) | Q(email__icontains=keyword)
            )
        return _paginate(request, qs, lambda u: user_json(u, with_count=True))

    if request.method == "POST":
        data = _json_body(request)
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        if len(username) < 3:
            return _fail("用户名至少 3 位")
        if len(password) < 8:
            return _fail("密码至少 8 位")
        problem = password_problem(password)
        if problem:
            return _fail(problem)
        if UserProfile.objects.filter(username=username).exists():
            return _fail("用户名已存在")
        user = UserProfile(
            username=username,
            display_name=data.get("display_name") or "",
            email=data.get("email") or "",
            note=data.get("note") or "",
            is_admin=bool(data.get("is_admin")),
            is_active=bool(data.get("is_active", True)),
        )
        user.set_password(password)
        user.save()
        return _ok(id=user.id)

    return _fail("请求方式错误", 405)


@admin_required_json
def user_detail(request, uid):
    user = UserProfile.objects.filter(id=uid).first()
    if user is None:
        return _fail("用户不存在", 404)

    if request.method == "GET":
        return JsonResponse({"user": user_json(user, with_count=True)})

    if request.method == "PUT":
        data = _json_body(request)
        user.display_name = data.get("display_name", user.display_name) or ""
        user.email = data.get("email", user.email) or ""
        user.note = data.get("note", user.note) or ""
        if "is_admin" in data:
            if user.id == request.console_user.id and not data.get("is_admin"):
                return _fail("不能取消自己的管理员权限")
            user.is_admin = bool(data.get("is_admin"))
            user.is_superuser = user.is_admin
        if "is_active" in data:
            if user.id == request.console_user.id and not data.get("is_active"):
                return _fail("不能禁用自己的账号")
            user.is_active = bool(data.get("is_active"))
        password = data.get("password") or ""
        if password:
            if len(password) < 8:
                return _fail("密码至少 8 位")
            problem = password_problem(password, user)
            if problem:
                return _fail(problem)
            user.set_password(password)
        with transaction.atomic():
            user.save()
            if password or not user.is_active:
                RustDeskToken.objects.filter(uid=user.pk).delete()
        return _ok()

    if request.method == "DELETE":
        if user.id == request.console_user.id:
            return _fail("不能删除自己")
        with transaction.atomic():
            RustDeskToken.objects.filter(uid=user.pk).delete()
            # RustDeskPeer.uid 是字符串、没有外键，不清理会让设备永久处于“已归属”状态。
            RustDeskPeer.objects.filter(uid=str(user.pk)).delete()
            user.delete()
        return _ok()

    return _fail("请求方式错误", 405)


def _latest_device_subquery():
    """同一 rid 只保留最近更新的一条记录（历史版本会因 uuid 变化产生重复行）。"""
    return Subquery(RustDesDevice.objects.filter(rid=OuterRef("rid")).order_by("-update_time", "-id").values("id")[:1])


# ---------------------------------------------------------------- 设备
@login_required_json
def devices(request):
    user = request.console_user
    qs = RustDesDevice.objects.filter(id=_latest_device_subquery())
    rids = _my_rids(user)
    if rids is not None:
        qs = qs.filter(rid__in=rids)
    keyword = (request.GET.get("keyword") or "").strip()
    if keyword:
        qs = qs.filter(
            Q(rid__icontains=keyword)
            | Q(hostname__icontains=keyword)
            | Q(username__icontains=keyword)
            | Q(os__icontains=keyword)
        )
    owners = _device_owner_map()
    owner_id = request.GET.get("user_id")
    if owner_id:
        qs = qs.filter(rid__in=[r for r, (oid, _n) in owners.items() if str(oid) == str(owner_id)])
    status = request.GET.get("status") or ""
    if status == "online":
        qs = qs.filter(update_time__gte=timezone.now() - datetime.timedelta(seconds=ONLINE_SECONDS))
    elif status == "offline":
        qs = qs.filter(
            Q(update_time__lt=timezone.now() - datetime.timedelta(seconds=ONLINE_SECONDS)) | Q(update_time__isnull=True)
        )
    qs = qs.order_by("-update_time")
    return _paginate(request, qs, lambda d: device_json(d, owners))


def _bind_device(user, rid):
    """把设备 rid 挂到 user 名下：RustDeskPeer + 个人地址簿联系人。"""
    RustDeskPeer.objects.filter(rid=rid).delete()
    if user is None:
        return
    device = RustDesDevice.objects.filter(rid=rid).first()
    peer = RustDeskPeer(
        uid=str(user.id),
        rid=rid,
        username=(device.username if device else "") or user.username,
        hostname=(device.hostname if device else "") or "",
        alias="",
        platform="",
        tags="",
        rhash="",
    )
    peer.save()
    ab = _ensure_personal_ab(user)
    AddressBookPeer.objects.get_or_create(
        ab=ab,
        rid=rid,
        defaults={"username": peer.username, "hostname": peer.hostname},
    )


def _ensure_personal_ab(user):
    ab = AddressBook.objects.filter(owner=user, is_personal=True).order_by("id").first()
    if ab is None:
        ab = AddressBook.objects.create(
            guid=uuidlib.uuid4().hex,
            owner=user,
            name="%s 的地址簿" % user.username,
            is_personal=True,
            rule=0,
        )
    return ab


@admin_required_json
@transaction.atomic
def device_owner(request, rid):
    if request.method not in ("PUT", "DELETE"):
        return _fail("请求方式错误", 405)
    data = _json_body(request) if request.method == "PUT" else {}
    uid = data.get("user_id")
    if request.method == "DELETE" or uid in (None, "", 0):
        RustDeskPeer.objects.filter(rid=rid).delete()
        return _ok()
    target = UserProfile.objects.filter(id=uid).first()
    if target is None:
        return _fail("用户不存在", 404)
    _bind_device(target, rid)
    return _ok()


# ---------------------------------------------------------------- 地址簿
def _visible_abs(user):
    qs = AddressBook.objects.all()
    if not user.is_admin:
        qs = qs.filter(Q(owner=user) | Q(rule__gt=0))
    return qs.order_by("is_personal", "-updated_at")


def _ab_for_write(user, guid):
    ab = AddressBook.objects.filter(guid=guid).first()
    if ab is None:
        return None, _fail("地址簿不存在", 404)
    if not user.is_admin and ab.owner_id != user.id:
        return None, _fail("无权限", 403)
    return ab, None


def _ab_name_taken(name, exclude_guid=None):
    qs = AddressBook.objects.filter(is_personal=False, name=name)
    if exclude_guid:
        qs = qs.exclude(guid=exclude_guid)
    return qs.exists()


@login_required_json
def addressbooks(request):
    user = request.console_user
    if request.method == "GET":
        _ensure_personal_ab(user)
        return _paginate(request, _visible_abs(user), lambda ab: ab_json(ab))

    if request.method == "POST":
        data = _json_body(request)
        owner = user
        if user.is_admin and data.get("owner_id"):
            owner = UserProfile.objects.filter(id=data.get("owner_id")).first()
            if owner is None:
                return _fail("用户不存在", 404)
        name = (data.get("name") or "未命名地址簿")[:64]
        if _ab_name_taken(name):
            return _fail("地址簿名称已存在", 400)
        ab = AddressBook.objects.create(
            guid=uuidlib.uuid4().hex,
            owner=owner,
            name=name,
            note=(data.get("note") or "")[:200],
            # 0=私有 1=只读 2=读写 3=完全控制；越界值归一到合法范围。
            rule=max(0, min(3, int(data.get("rule") or 0))),
            is_personal=False,
        )
        return _ok(guid=ab.guid)

    return _fail("请求方式错误", 405)


@login_required_json
def addressbook_detail(request, guid):
    user = request.console_user
    ab, err = _ab_for_write(user, guid)
    if err:
        return err
    if request.method == "GET":
        return JsonResponse({"addressbook": ab_json(ab)})
    if request.method == "PUT":
        data = _json_body(request)
        if "name" in data:
            new_name = (data.get("name") or ab.name)[:64]
            if ab.is_personal and new_name != ab.name:
                return _fail(
                    "个人地址簿的名称由客户端固定显示为「我的地址簿」，不能修改；如需自定义名称请新建共享地址簿", 400
                )
            if new_name != ab.name and _ab_name_taken(new_name, ab.guid):
                return _fail("地址簿名称已存在", 400)
            ab.name = new_name
        if "note" in data:
            ab.note = (data.get("note") or "")[:200]
        if "rule" in data:
            # 0=私有 1=只读 2=读写 3=完全控制；越界值归一到合法范围。
            ab.rule = max(0, min(3, int(data.get("rule") or 0)))
        ab.save()
        return _ok()
    if request.method == "DELETE":
        if ab.is_personal:
            return _fail("个人地址簿不能删除")
        ab.delete()
        return _ok()
    return _fail("请求方式错误", 405)


@login_required_json
def ab_peers(request, guid):
    user = request.console_user
    ab = AddressBook.objects.filter(guid=guid).first()
    if ab is None:
        return _fail("地址簿不存在", 404)
    if not user.is_admin and ab.owner_id != user.id and ab.rule <= 0:
        return _fail("无权限", 403)

    if request.method == "GET":
        qs = ab.peers.all().order_by("alias", "rid")
        keyword = (request.GET.get("keyword") or "").strip()
        if keyword:
            qs = qs.filter(
                Q(rid__icontains=keyword)
                | Q(alias__icontains=keyword)
                | Q(hostname__icontains=keyword)
                | Q(username__icontains=keyword)
            )
        dev_info = views_pro._device_info_map(request.console_user)
        return _paginate(request, qs, lambda p: ab_peer_json(p, dev_info.get(p.rid)))

    if not user.is_admin and ab.owner_id != user.id:
        return _fail("无权限", 403)

    data = _json_body(request)
    if request.method == "POST":
        rid = (data.get("id") or data.get("rid") or "").strip()
        if not rid:
            return _fail("缺少设备 ID")
        defaults = {
            "alias": (data.get("alias") or "")[:128],
            "username": (data.get("username") or "")[:64],
            "hostname": (data.get("hostname") or "")[:128],
            "platform": (data.get("platform") or "")[:64],
            "tags": ",".join(data.get("tags") or [])[:255],
            "note": (data.get("note") or "")[:200],
        }
        # 共享地址簿的连接密码（对应客户端「设置共享密码」）；个人簿不使用该字段。
        if "password" in data and not ab.is_personal:
            defaults["password"] = (data.get("password") or "")[:128]
        AddressBookPeer.objects.update_or_create(ab=ab, rid=rid, defaults=defaults)
        ab.save()  # 刷新 updated_at
        return _ok()

    if request.method == "DELETE":
        ids = data.get("ids") or []
        ab.peers.filter(rid__in=ids).delete()
        ab.save()
        return _ok()

    return _fail("请求方式错误", 405)


@login_required_json
def ab_peer_detail(request, guid, rid):
    if request.method != "PUT":
        return _fail("请求方式错误", 405)
    user = request.console_user
    ab, err = _ab_for_write(user, guid)
    if err:
        return err
    peer = ab.peers.filter(rid=rid).first()
    if peer is None:
        return _fail("联系人不存在", 404)
    data = _json_body(request)
    for field, limit in (("alias", 128), ("username", 64), ("hostname", 128), ("platform", 64), ("note", 200)):
        if field in data:
            setattr(peer, field, (data.get(field) or "")[:limit])
    if "tags" in data:
        peer.tags = ",".join(data.get("tags") or [])[:255]
    peer.save()
    ab.save()
    return _ok()


@login_required_json
def ab_tags(request, guid):
    user = request.console_user
    ab = AddressBook.objects.filter(guid=guid).first()
    if ab is None:
        return _fail("地址簿不存在", 404)
    if not user.is_admin and ab.owner_id != user.id and ab.rule <= 0:
        return _fail("无权限", 403)
    if request.method == "GET":
        return _paginate(request, ab.tags.all().order_by("name"), tag_json)

    if not user.is_admin and ab.owner_id != user.id:
        return _fail("无权限", 403)

    data = _json_body(request)
    if request.method == "POST":
        name = (data.get("name") or "").strip()
        if not name:
            return _fail("标签名不能为空")
        AddressBookTag.objects.update_or_create(
            ab=ab, name=name[:64], defaults={"color": normalize_color(data.get("color"), name[:64])}
        )
        return _ok()
    if request.method == "DELETE":
        ab.tags.filter(name__in=data.get("names") or []).delete()
        return _ok()
    return _fail("请求方式错误", 405)


@login_required_json
def ab_tag_detail(request, guid, name):
    if request.method != "PUT":
        return _fail("请求方式错误", 405)
    user = request.console_user
    ab, err = _ab_for_write(user, guid)
    if err:
        return err
    tag = ab.tags.filter(name=name).first()
    if tag is None:
        return _fail("标签不存在", 404)
    data = _json_body(request)
    new_name = (data.get("new_name") or "").strip()
    if new_name and new_name != name:
        tag.name = new_name[:64]
    if "color" in data:
        tag.color = normalize_color(data.get("color"), tag.name)
    tag.save()
    return _ok()


# ---------------------------------------------------------------- 设备分组
def _visible_groups(user):
    qs = DeviceGroup.objects.all()
    if not user.is_admin:
        qs = qs.filter(Q(owner=user) | Q(owner__isnull=True))
    return qs.order_by("-updated_at", "name")


@login_required_json
def groups(request):
    user = request.console_user
    if request.method == "GET":
        return _paginate(request, _visible_groups(user), group_json)
    if request.method == "POST":
        data = _json_body(request)
        name = (data.get("name") or "").strip()
        if not name:
            return _fail("分组名称不能为空")
        owner = user
        if user.is_admin and data.get("owner_id"):
            owner = UserProfile.objects.filter(id=data.get("owner_id")).first()
        if DeviceGroup.objects.filter(owner=owner, name=name[:64]).exists():
            return _fail("分组名称已存在", 400)
        group = DeviceGroup.objects.create(
            guid=uuidlib.uuid4().hex,
            owner=owner,
            name=name[:64],
            note=(data.get("note") or "")[:200],
        )
        return _ok(guid=group.guid)
    return _fail("请求方式错误", 405)


@login_required_json
def group_detail(request, guid):
    user = request.console_user
    group = DeviceGroup.objects.filter(guid=guid).first()
    if group is None:
        return _fail("分组不存在", 404)
    if not user.is_admin and group.owner_id != user.id:
        return _fail("无权限", 403)
    if request.method == "GET":
        return JsonResponse({"group": group_json(group)})
    if request.method == "PUT":
        data = _json_body(request)
        if "name" in data:
            name = (data.get("name") or "").strip()
            if not name:
                return _fail("分组名称不能为空")
            if name[:64] != group.name and DeviceGroup.objects.filter(owner=group.owner, name=name[:64]).exists():
                return _fail("分组名称已存在", 400)
            group.name = name[:64]
        if "note" in data:
            group.note = (data.get("note") or "")[:200]
        group.save()
        return _ok()
    if request.method == "DELETE":
        group.delete()
        return _ok()
    return _fail("请求方式错误", 405)


@login_required_json
def group_members(request, guid):
    user = request.console_user
    group = DeviceGroup.objects.filter(guid=guid).first()
    if group is None:
        return _fail("分组不存在", 404)
    if not user.is_admin and group.owner_id != user.id:
        return _fail("无权限", 403)
    if request.method == "GET":
        rows = []
        for member in group.members.all():
            peer = AddressBookPeer.objects.filter(rid=member.rid).first()
            rows.append(
                {
                    "rid": member.rid,
                    "alias": (peer.alias if peer else "") or "",
                    "hostname": (peer.hostname if peer else "") or "",
                }
            )
        return JsonResponse({"total": len(rows), "list": rows})
    if request.method == "POST":
        for rid in _json_body(request).get("rids") or []:
            DeviceGroupPeer.objects.get_or_create(group=group, rid=rid)
        return _ok()
    if request.method == "DELETE":
        group.members.filter(rid__in=(_json_body(request).get("rids") or [])).delete()
        return _ok()
    return _fail("请求方式错误", 405)


# ---------------------------------------------------------------- 日志
def _duration(start, end):
    if not start or not end:
        return ""
    delta = end - start
    total = int(delta.total_seconds())
    return "%02d:%02d:%02d" % (total // 3600, total % 3600 // 60, total % 60)


@login_required_json
def conn_logs(request):
    user = request.console_user
    qs = ConnLog.objects.all()
    rids = _my_rids(user)
    if rids is not None:
        qs = qs.filter(Q(rid__in=rids) | Q(from_id__in=rids))
    keyword = (request.GET.get("keyword") or "").strip()
    if keyword:
        qs = qs.filter(
            Q(from_ip__icontains=keyword)
            | Q(from_id__icontains=keyword)
            | Q(rid__icontains=keyword)
            | Q(note__icontains=keyword)
        )
    start = (request.GET.get("start") or "").strip()
    end = (request.GET.get("end") or "").strip()
    if start:
        qs = qs.filter(conn_start__gte=start)
    if end:
        qs = qs.filter(conn_start__lte=end + " 23:59:59")
    qs = qs.order_by("-conn_start")

    def ser(log):
        peer = RustDeskPeer.objects.filter(rid=log.rid).first()
        return {
            "id": log.id,
            "from_ip": log.from_ip or "",
            "from_id": log.from_id or "",
            "from_alias": (peer.alias if peer else "") or "",
            "rid": log.rid or "",
            "alias": (peer.alias if peer else "") or "",
            "conn_start": _fmt(log.conn_start),
            "conn_end": _fmt(log.conn_end),
            "duration": _duration(log.conn_start, log.conn_end),
            "note": log.note or "",
        }

    return _paginate(request, qs, ser)


@login_required_json
def file_logs(request):
    user = request.console_user
    qs = FileLog.objects.all()
    rids = _my_rids(user)
    if rids is not None:
        qs = qs.filter(Q(remote_id__in=rids) | Q(user_id__in=rids))
    keyword = (request.GET.get("keyword") or "").strip()
    if keyword:
        qs = qs.filter(Q(file__icontains=keyword) | Q(remote_id__icontains=keyword) | Q(user_ip__icontains=keyword))
    qs = qs.order_by("-logged_at")

    return _paginate(
        request,
        qs,
        lambda log: {
            "id": log.id,
            "file": log.file or "",
            "remote_id": log.remote_id or "",
            "user_id": log.user_id or "",
            "user_ip": log.user_ip or "",
            "filesize": log.filesize or "",
            "direction": log.direction,
            "logged_at": _fmt(log.logged_at),
        },
    )


# ---------------------------------------------------------------- 概览
@login_required_json
def stats(request):
    user = request.console_user
    rids = _my_rids(user)
    devices_qs = RustDesDevice.objects.filter(id=_latest_device_subquery())
    conn_qs = ConnLog.objects.all()
    file_qs = FileLog.objects.all()
    ab_qs = _visible_abs(user)
    if rids is not None:
        devices_qs = devices_qs.filter(rid__in=rids)
        conn_qs = conn_qs.filter(Q(rid__in=rids) | Q(from_id__in=rids))
        file_qs = file_qs.filter(Q(remote_id__in=rids) | Q(user_id__in=rids))

    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    peer_count = sum(ab.peers.count() for ab in ab_qs)
    return JsonResponse(
        {
            "devices": {
                "total": devices_qs.count(),
                "online": devices_qs.filter(
                    update_time__gte=timezone.now() - datetime.timedelta(seconds=ONLINE_SECONDS)
                ).count(),
            },
            "users": {
                "total": UserProfile.objects.count() if user.is_admin else 1,
                "active": UserProfile.objects.filter(is_active=True).count() if user.is_admin else 1,
            },
            "addressbooks": {"total": ab_qs.count(), "peers": peer_count},
            "logs": {
                "conn_today": conn_qs.filter(conn_start__gte=today).count(),
                "file_today": file_qs.filter(logged_at__gte=today).count(),
            },
        }
    )


# ---------------------------------------------------------------- 前端承载
@ensure_csrf_cookie
def console_index(request):
    """返回 TDesign 控制台的 index.html（构建产物在 static/console/）。"""
    index_path = os.path.join(settings.BASE_DIR, "static", "console", "index.html")
    if not os.path.exists(index_path):
        return HttpResponse(
            '<html><body style="font-family:sans-serif;padding:40px">'
            "<h3>控制台尚未构建</h3>"
            "<p>请在项目目录执行 <code>npm --prefix frontend ci</code>，"
            "然后运行 <code>npm --prefix frontend run build</code>。</p></body></html>",
            content_type="text/html; charset=utf-8",
        )
    resp = FileResponse(open(index_path, "rb"), content_type="text/html; charset=utf-8")
    # 控制台入口不缓存，保证前端发版后浏览器立刻拿到新的 hash 资源
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp["Pragma"] = "no-cache"
    return resp


# ---------------------------------------------------------------- 系统设置
def _public_callback_url(request):
    """回调地址展示：优先显式配置，其次按代理/HTTPS 部署推断。"""
    configured = (getattr(settings, "OIDC_REDIRECT_URI", "") or "").strip()
    if configured:
        return configured
    if getattr(settings, "HTTPS", False) or getattr(settings, "BEHIND_PROXY", False):
        host = request.get_host().split(":", 1)[0]
        return "https://{}/api/oidc/callback".format(host)
    return request.build_absolute_uri("/api/oidc/callback")


def _oidc_settings_payload(request):
    from api import oauth

    rows = OauthProvider.objects.order_by("sort", "id")
    providers = [oauth.public_provider(row) for row in rows]
    return {
        "enabled": any(row["enabled"] for row in providers),
        "providers": providers,
        "redirect_uri": _public_callback_url(request),
    }


def _save_oauth_providers(items):
    """按提交的列表整体同步登录方式；返回错误文案，成功返回 None。"""
    from api import oauth

    if not isinstance(items, list):
        return "oidc.providers 必须是数组"
    normalized = []
    seen_ops = set()
    for item in items:
        if not isinstance(item, dict):
            return "每个登录方式必须是对象"
        op = str(item.get("op") or "").strip()[:32]
        if not op:
            return "登录方式缺少 op"
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", op):
            # 旧客户端把 op 拼进 "oidc/<op>" 里，含斜杠/空格会破坏解析。
            return "登录方式 op 只能包含字母、数字、下划线和短横线：{}".format(op)
        if op in seen_ops:
            return "登录方式 op 重复：{}".format(op)
        seen_ops.add(op)
        oauth_type = str(item.get("type") or "oidc").strip().lower()
        if oauth_type not in oauth.SUPPORTED_TYPES:
            return "不支持的登录类型：{}".format(oauth_type)
        issuer = str(item.get("issuer") or "").strip().rstrip("/")[:255]
        if issuer and not issuer.startswith(("http://", "https://")):
            return "issuer 必须是 http(s) 地址"
        if oauth_type in ("oidc", "google") and not issuer:
            return "{} 缺少 issuer".format(op)
        client_id = str(item.get("client_id") or "").strip()[:255]
        if not client_id:
            return "{} 缺少 client_id".format(op)
        try:
            sort = int(item.get("sort") or 0)
        except (TypeError, ValueError):
            sort = 0
        normalized.append(
            {
                "op": op,
                "oauth_type": oauth_type,
                "issuer": issuer,
                "client_id": client_id,
                "name": str(item.get("name") or "").strip()[:64],
                "scopes": str(item.get("scopes") or "").strip()[:255],
                "auto_register": bool(item.get("auto_register", True)),
                "pkce_enable": bool(item.get("pkce_enable", True)),
                "enabled": bool(item.get("enabled", True)),
                "sort": sort,
                "secret": str(item.get("client_secret") or "").strip()[:255],
                "clear_secret": bool(item.get("clear_secret")),
            }
        )
    existing = {row.op: row for row in OauthProvider.objects.all()}
    for item in normalized:
        if not item["secret"] and not item["clear_secret"]:
            current = existing.get(item["op"])
            if current is None or not (current.client_secret or "").strip():
                return "{} 缺少 client_secret".format(item["op"])
    with transaction.atomic():
        for item in normalized:
            row = existing.pop(item["op"], None) or OauthProvider(op=item["op"])
            row.oauth_type = item["oauth_type"]
            row.issuer = item["issuer"]
            row.client_id = item["client_id"]
            row.name = item["name"]
            row.scopes = item["scopes"]
            row.auto_register = item["auto_register"]
            row.pkce_enable = item["pkce_enable"]
            row.enabled = item["enabled"]
            row.sort = item["sort"]
            if item["secret"]:
                row.client_secret = item["secret"]
            elif item["clear_secret"]:
                row.client_secret = ""
            row.save()
        for row in existing.values():
            row.delete()
    return None


def console_settings(request):
    """GET 读取公开设置（登录用户）；PUT 管理员修改（注册开关 + OIDC）。"""
    from api.settings_store import allow_registration, set_setting

    user = _current_user(request)
    if user is None:
        return _fail("未登录", 401)
    if request.method == "GET":
        data = {"ok": True, "allow_registration": allow_registration(), "is_admin": bool(user.is_admin)}
        if user.is_admin:
            # OIDC 的 issuer/client_id/密钥状态只对管理员可见，普通用户不返回。
            data["oidc"] = _oidc_settings_payload(request)
        return JsonResponse(data)
    if request.method in ("PUT", "POST"):
        if not user.is_admin:
            return _fail("需要管理员权限", 403)
        data = _json_body(request)
        changed = False
        if "allow_registration" in data:
            value = data.get("allow_registration")
            if not isinstance(value, bool):
                return _fail("allow_registration 必须是布尔值")
            set_setting("allow_registration", "1" if value else "0")
            changed = True
        oidc_data = data.get("oidc")
        if oidc_data is not None:
            if not isinstance(oidc_data, dict):
                return _fail("oidc 必须是对象")
            if "providers" in oidc_data:
                error = _save_oauth_providers(oidc_data.get("providers"))
                if error:
                    return _fail(error)
                changed = True
            else:
                # 兼容旧版单 IdP 配置（仅在数据库无 provider 时作为回退生效）。
                if "issuer" in oidc_data:
                    issuer = str(oidc_data.get("issuer") or "").strip().rstrip("/")[:255]
                    if issuer and not issuer.startswith(("http://", "https://")):
                        return _fail("OIDC issuer 必须是 http(s) 地址")
                    set_setting("oidc_issuer", issuer)
                if "client_id" in oidc_data:
                    set_setting("oidc_client_id", str(oidc_data.get("client_id") or "").strip()[:255])
                if "client_secret" in oidc_data:
                    secret = str(oidc_data.get("client_secret") or "").strip()[:255]
                    if secret:
                        set_setting("oidc_client_secret", secret)
                if oidc_data.get("clear_secret"):
                    set_setting("oidc_client_secret", "")
                if "label" in oidc_data:
                    set_setting("oidc_label", str(oidc_data.get("label") or "").strip()[:32])
                changed = True
        if not changed:
            return _fail("没有可更新的设置")
        return _ok(allow_registration=allow_registration(), oidc=_oidc_settings_payload(request))
    return _fail("请求方式错误", 405)
