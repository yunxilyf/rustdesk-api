"""RustDesk 新版客户端 API。

旧版兼容接口在 views_api.py，本模块提供新版客户端使用的接口：
- /api/login-options、/api/oidc/*
- /api/ab/personal、/api/ab/settings、/api/ab/shared/profiles
- /api/ab/peers、/api/ab/tags/<guid>、/api/ab/peer|tag/*
- /api/users、/api/peers、/api/device-group/accessible
- /api/switch-grant、/api/record、/api/devices/cli、/api/devices/deploy
- /api/audit/conn/active
"""

import ipaddress
import json
import logging
import time
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import login as auth_login
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _

from . import oauth, oidc, throttle
from .client_auth import authenticate_client as _auth
from .models import (
    AddressBook,
    AddressBookPeer,
    AddressBookTag,
    ConnLog,
    DeviceGroup,
    DeviceGroupPeer,
    OidcLogin,
    RustDesDevice,
    RustDeskPeer,
    RustDeskTag,
    RustDeskToken,
    UserProfile,
)
from .tag_colors import normalize_color

# 控制台第三方登录：state 必须与本浏览器绑定，否则攻击者可以把自己的回调链接
# 发给受害者，让受害者在他自己的浏览器里登入攻击者的账号（登录 CSRF）。
CONSOLE_STATE_COOKIE = "oidc_console_state"

PAGE_SIZE_DEFAULT = 100
logger = logging.getLogger(__name__)


def _platform_from_os(os_name):
    """把 sysinfo 上报的 os 映射成客户端的 platform 常量。

    客户端 flutter/lib/common.dart:1703 getPlatformImage 只认 Windows/Linux/
    Mac OS/Android；platform 为空时连图标都不画（卡片只剩渐变底色）。
    """
    s = (os_name or "").strip()
    if not s:
        return ""
    low = s.lower()
    if low.startswith("windows"):
        return "Windows"
    if "mac" in low or "darwin" in low:
        return "Mac OS"
    if "android" in low:
        return "Android"
    if any(
        k in low for k in ("linux", "ubuntu", "debian", "centos", "fedora", "arch", "suse", "red hat", "rocky", "alma")
    ):
        return "Linux"
    return s


def _device_info_map(user):
    """rid -> 最近一次 sysinfo 上报的 platform/hostname/username。"""
    devices = RustDesDevice.objects.order_by("rid", "-update_time", "-id")
    if not user.is_admin:
        devices = devices.filter(rid__in=owned_device_ids(user))
    latest = {}
    for d in devices:
        latest.setdefault(d.rid, d)
    return {
        rid: {
            "platform": _platform_from_os(d.os),
            "hostname": d.hostname or "",
            "username": d.username or "",
        }
        for rid, d in latest.items()
    }


# --------------------------------------------------------------------------
# 通用工具
# --------------------------------------------------------------------------


def _body(request):
    """把请求体解析成 dict，解析失败返回空 dict。"""
    try:
        raw = request.body.decode("utf-8", "ignore")
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _body_any(request):
    """解析请求体，保留 list / dict。"""
    try:
        raw = request.body.decode("utf-8", "ignore")
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def _unauthorized():
    return JsonResponse({"error": _("未登录或登录已过期")}, status=401)


def _user_json(user):
    return {
        "name": user.username,
        "display_name": user.display_name or user.username,
        "avatar": user.avatar or "",
        "email": user.email or "",
        "note": user.note or "",
        "verifier": user.verifier or "",
        "status": 1 if user.status is None else int(user.status),
        "is_admin": bool(user.is_admin),
    }


def _page_params(request):
    def _int(name, default):
        try:
            return max(1, int(request.GET.get(name, default)))
        except (TypeError, ValueError):
            return default

    page_size = _int("pageSize", PAGE_SIZE_DEFAULT)
    current = _int("current", 1)
    return current, page_size


def _paginate(qs, current, page_size):
    total = qs.count()
    start = (current - 1) * page_size
    return total, list(qs[start : start + page_size])


def _empty_ok():
    """地址簿写操作成功时必须返回空 body，客户端把非空 body 当错误。"""
    return HttpResponse(status=200)


# --------------------------------------------------------------------------
# 地址簿
# --------------------------------------------------------------------------


def _personal_ab(user):
    ab = AddressBook.objects.filter(owner=user, is_personal=True).order_by("id").first()
    if ab is None:
        ab = AddressBook.objects.create(
            guid=uuid.uuid4().hex,
            owner=user,
            name=_("个人地址簿"),
            is_personal=True,
        )
    return ab


def _accessible_abs(user):
    return AddressBook.objects.filter(Q(owner=user) | Q(rule__gt=0))


def _get_ab(user, guid, *, write=False):
    """按 guid 取地址簿；guid 为空时取个人地址簿。"""
    if not guid:
        return _personal_ab(user)
    ab = AddressBook.objects.filter(guid=guid).first()
    if ab is None:
        return None
    if ab.owner_id != user.id and ab.rule < (2 if write else 1):
        return None
    return ab


def _peer_json(peer, group_names=None, dev_info=None):
    tags = [t for t in (peer.tags or "").split(",") if t]
    info = (dev_info or {}).get(peer.rid) or {}
    # 个人地址簿只同步个人连接密码哈希（hash），共享地址簿只同步共享密码（password）。
    # 混用会让客户端把另一种凭据当成连接密码，甚至把密码写进个人簿。
    personal = bool(peer.ab.is_personal)
    return {
        "id": peer.rid,
        "hash": (peer.rhash or "") if personal else "",
        "password": "" if personal else (peer.password or ""),
        "username": peer.username or info.get("username", ""),
        "hostname": peer.hostname or info.get("hostname", ""),
        "platform": peer.platform or info.get("platform", ""),
        "alias": peer.alias or "",
        "tags": tags,
        "note": peer.note or "",
        "loginName": peer.login_name or "",
        "device_group_name": (group_names or {}).get(peer.rid, ""),
        "forceAlwaysRelay": "false",
        "rdpPort": "",
        "rdpUsername": "",
        "same_server": peer.rid in (dev_info or {}),
    }


def _peer_payload(peer, group_names=None, login_name="", dev_info=None):
    """GET /api/peers 的条目：Flutter PeerPayload 读 user/user_name/info.*

    loginName 必须是「API 账号名」：客户端设备分组页按 peer.loginName 过滤
    （flutter/lib/common/widgets/peers_view.dart:591），留空则选中用户后列表为空。
    """
    rid = peer.rid
    info = (dev_info or {}).get(rid) or {}
    username = peer.username or info.get("username", "")
    hostname = peer.hostname or info.get("hostname", "")
    platform = peer.platform or info.get("platform", "")
    return {
        "id": rid,
        "user": login_name or username,
        "user_name": login_name or peer.login_name or username,
        "loginName": login_name,
        "device_group_name": (group_names or {}).get(rid, ""),
        "note": peer.note or "",
        "status": 1,
        "info": {
            "username": username,
            "device_name": hostname,
            "os": platform,
        },
        # 同时带上地址簿 Peer 的字段，兼容按 Peer 解析的界面
        "hash": peer.rhash or "",
        "username": username,
        "hostname": hostname,
        "platform": platform,
        "alias": peer.alias or "",
        "tags": [t for t in (peer.tags or "").split(",") if t],
    }


def _tag_json(tag):
    return {"name": tag.name, "color": normalize_color(tag.color, tag.name)}


def _legacy_to_ab(user):
    """把旧表里的地址簿数据迁移到 AddressBook，只在首次访问时执行。"""
    ab = AddressBook.objects.filter(owner=user, is_personal=True).order_by("id").first()
    if ab is None:
        ab = AddressBook.objects.create(guid=uuid.uuid4().hex, owner=user, name=_("个人地址簿"), is_personal=True)
    old_tags = RustDeskTag.objects.filter(uid=str(user.id))
    for t in old_tags:
        color = 0
        try:
            color = normalize_color(t.tag_color, t.tag_name)
        except (TypeError, ValueError):
            color = 0
        AddressBookTag.objects.get_or_create(ab=ab, name=t.tag_name, defaults={"color": color})
    old_peers = RustDeskPeer.objects.filter(uid=str(user.id))
    for p in old_peers:
        AddressBookPeer.objects.get_or_create(
            ab=ab,
            rid=p.rid,
            defaults={
                "rhash": p.rhash or "",
                "username": p.username or "",
                "hostname": p.hostname or "",
                "platform": p.platform or "",
                "alias": p.alias or "",
                "tags": p.tags or "",
            },
        )
    return ab


def ab_personal(request):
    """POST /api/ab/personal -> {guid, name, owner, note, info, rule}"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    ab = _personal_ab(user)
    return JsonResponse(
        {
            "guid": ab.guid,
            "name": ab.name,
            "owner": user.username,
            "note": ab.note or "",
            "info": ab.info or "",
            "rule": ab.rule,
        }
    )


def ab_settings(request):
    """POST /api/ab/settings -> {max_peer_one_ab}"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    return JsonResponse({"max_peer_one_ab": 0})


def ab_shared_profiles(request):
    """POST /api/ab/shared/profiles -> {total, data:[profile]}"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    current, page_size = _page_params(request)
    # 共享给所有人的地址簿（rule>0）+ 自己创建的地址簿（rule=0 时仅自己可见）
    qs = AddressBook.objects.filter(is_personal=False).filter(Q(rule__gt=0) | Q(owner=user)).order_by("id")
    total, rows = _paginate(qs, current, page_size)
    data = []
    for ab in rows:
        # 属于本人的地址簿按“可读写”下发（客户端据此允许增删联系人），
        # 别人共享来的地址簿保持真实 rule（1=只读 / 2=读写 / 3=完全控制）。
        rule = ab.rule
        if ab.owner_id == user.id and rule < 2:
            rule = 2
        data.append(
            {
                "guid": ab.guid,
                "name": ab.name,
                "owner": ab.owner.username if ab.owner else "",
                "note": ab.note or "",
                "info": ab.info or "",
                "rule": rule,
            }
        )
    return JsonResponse({"total": total, "data": data})


def ab_peers(request):
    """POST /api/ab/peers?current&pageSize&ab -> {total, data}"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    ab = _get_ab(user, request.GET.get("ab", ""))
    if ab is None:
        return JsonResponse({"error": _("地址簿不存在")}, status=404)
    current, page_size = _page_params(request)
    total, rows = _paginate(ab.peers.all().order_by("id"), current, page_size)
    group_names = _device_group_names(user)
    dev_info = _device_info_map(user)
    return JsonResponse({"total": total, "data": [_peer_json(p, group_names, dev_info) for p in rows]})


def ab_tags(request, guid):
    """POST /api/ab/tags/<guid> -> [ {name, color} ]"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    ab = _get_ab(user, guid)
    if ab is None:
        return JsonResponse({"error": _("地址簿不存在")}, status=404)
    return JsonResponse([_tag_json(t) for t in ab.tags.all().order_by("id")], safe=False)


def ab_peer_add(request, guid):
    """POST /api/ab/peer/add/<guid>，body 是单个 peer 对象。"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    ab = _get_ab(user, guid, write=True)
    if ab is None:
        return JsonResponse({"error": _("地址簿不存在")}, status=404)
    data = _body(request)
    rid = str(data.get("id", "")).strip()
    if not rid:
        return JsonResponse({"error": _("缺少设备 ID")}, status=400)
    tags = data.get("tags")
    if isinstance(tags, list):
        tags = ",".join([str(t) for t in tags])
    peer, created = AddressBookPeer.objects.get_or_create(
        ab=ab,
        rid=rid,
        defaults={
            "rhash": str(data.get("hash", "")) if ab.is_personal else "",
            "password": "" if ab.is_personal else str(data.get("password", "")),
            "username": str(data.get("username", "")),
            "hostname": str(data.get("hostname", "")),
            "platform": str(data.get("platform", "")),
            "alias": str(data.get("alias", "")),
            "tags": tags or "",
            "note": str(data.get("note", "")),
            "login_name": str(data.get("loginName", "")),
        },
    )
    if not created:
        _apply_peer_fields(peer, data, ab.is_personal)
        peer.save()
    return _empty_ok()


def ab_peer_update(request, guid):
    """PUT /api/ab/peer/update/<guid>，body {id, ...要改的字段}。"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    ab = _get_ab(user, guid, write=True)
    if ab is None:
        return JsonResponse({"error": _("地址簿不存在")}, status=404)
    data = _body(request)
    rid = str(data.get("id", "")).strip()
    peer = ab.peers.filter(rid=rid).first() if rid else None
    if peer is None:
        return JsonResponse({"error": _("设备不存在")}, status=404)
    _apply_peer_fields(peer, data, ab.is_personal)
    peer.save()
    return _empty_ok()


def _apply_peer_fields(peer, data, personal):
    # 个人地址簿只接受 hash（个人连接密码哈希），共享地址簿只接受 password。
    # 客户端本应在发送前自行剥离，这里再兜底一次，避免凭据串到错误字段。
    if personal:
        if "hash" in data:
            peer.rhash = str(data.get("hash") or "")
        peer.password = ""
    else:
        if "password" in data:
            peer.password = str(data.get("password") or "")
        peer.rhash = ""
    if "username" in data:
        peer.username = str(data.get("username") or "")
    if "hostname" in data:
        peer.hostname = str(data.get("hostname") or "")
    if "platform" in data:
        peer.platform = str(data.get("platform") or "")
    if "alias" in data:
        peer.alias = str(data.get("alias") or "")
    if "note" in data:
        peer.note = str(data.get("note") or "")
    if "loginName" in data:
        peer.login_name = str(data.get("loginName") or "")
    if "tags" in data:
        tags = data.get("tags")
        if isinstance(tags, list):
            peer.tags = ",".join([str(t) for t in tags])
        else:
            peer.tags = str(tags or "")


def ab_peer_delete(request, guid):
    """DELETE /api/ab/peer/<guid>，body 是 id 数组。"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    ab = _get_ab(user, guid, write=True)
    if ab is None:
        return JsonResponse({"error": _("地址簿不存在")}, status=404)
    ids = _body_any(request)
    if isinstance(ids, list):
        ab.peers.filter(rid__in=[str(i) for i in ids]).delete()
    return _empty_ok()


def ab_tag_add(request, guid):
    """POST /api/ab/tag/add/<guid>，body {name, color}。"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    ab = _get_ab(user, guid, write=True)
    if ab is None:
        return JsonResponse({"error": _("地址簿不存在")}, status=404)
    data = _body(request)
    name = str(data.get("name", "")).strip()
    if not name:
        return JsonResponse({"error": _("缺少标签名")}, status=400)
    if len(name) > 64:
        return JsonResponse({"error": _("标签名过长")}, status=400)
    AddressBookTag.objects.update_or_create(
        ab=ab, name=name, defaults={"color": normalize_color(data.get("color"), name)}
    )
    return _empty_ok()


def ab_tag_rename(request, guid):
    """PUT /api/ab/tag/rename/<guid>，body {old, new}。"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    ab = _get_ab(user, guid, write=True)
    if ab is None:
        return JsonResponse({"error": _("地址簿不存在")}, status=404)
    data = _body(request)
    old = str(data.get("old", "")).strip()
    new = str(data.get("new", "")).strip()
    if not new:
        return JsonResponse({"error": _("缺少标签名")}, status=400)
    if len(new) > 64:
        return JsonResponse({"error": _("标签名过长")}, status=400)
    tag = ab.tags.filter(name=old).first()
    if tag is None:
        return JsonResponse({"error": _("标签不存在")}, status=404)
    if new != old and ab.tags.filter(name=new).exists():
        return JsonResponse({"error": _("标签名已存在")}, status=400)
    tag.name = new
    tag.save()
    for peer in ab.peers.all():
        names = [t for t in (peer.tags or "").split(",") if t]
        if old in names:
            names = [new if t == old else t for t in names]
            peer.tags = ",".join(names)
            peer.save()
    return _empty_ok()


def ab_tag_update(request, guid):
    """PUT /api/ab/tag/update/<guid>，body {name, color}。"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    ab = _get_ab(user, guid, write=True)
    if ab is None:
        return JsonResponse({"error": _("地址簿不存在")}, status=404)
    data = _body(request)
    name = str(data.get("name", ""))
    updated = ab.tags.filter(name=name).update(color=normalize_color(data.get("color"), name))
    if not updated:
        return JsonResponse({"error": _("标签不存在")}, status=404)
    return _empty_ok()


def ab_tag_delete(request, guid):
    """DELETE /api/ab/tag/<guid>，body 是标签名数组。"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    ab = _get_ab(user, guid, write=True)
    if ab is None:
        return JsonResponse({"error": _("地址簿不存在")}, status=404)
    names = _body_any(request)
    if isinstance(names, list):
        names = [str(n) for n in names]
        ab.tags.filter(name__in=names).delete()
        for peer in ab.peers.all():
            tags = [t for t in (peer.tags or "").split(",") if t and t not in names]
            peer.tags = ",".join(tags)
            peer.save()
    return _empty_ok()


# --------------------------------------------------------------------------
# 用户 / 设备 / 分组
# --------------------------------------------------------------------------


def owned_device_ids(user):
    """设备归属由管理员分配，地址簿只保存联系人。"""
    return RustDeskPeer.objects.filter(uid=str(user.pk)).values("rid")


def device_is_assigned(rid):
    return RustDeskPeer.objects.filter(rid=rid).exists()


def can_manage_device(user, rid, token):
    if user.is_admin or owned_device_ids(user).filter(rid=rid).exists():
        return True
    if not rid or token.rid != rid or not token.uuid or device_is_assigned(rid):
        return False
    uuid = RustDesDevice.objects.filter(rid=rid).order_by("-update_time", "-id").values_list("uuid", flat=True).first()
    return uuid == token.uuid


def _device_group_names(user):
    mapping = {}
    for m in DeviceGroupPeer.objects.filter(group__owner=user).select_related("group"):
        mapping[m.rid] = m.group.name
    return mapping


def users(request):
    """GET /api/users?current&pageSize&accessible&status -> {total, data}"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    current, page_size = _page_params(request)
    if user.is_admin:
        qs = UserProfile.objects.all().order_by("id")
    else:
        # 客户端「设备分组」按 peer.loginName 过滤，用户列表里必须包含
        # 共享地址簿的属主，否则普通用户看不到别人共享给自己的设备。
        owner_ids = set(_accessible_abs(user).filter(rule__gt=0).values_list("owner_id", flat=True))
        qs = UserProfile.objects.filter(Q(id=user.id) | Q(id__in=owner_ids), is_active=True).order_by("id")
    total, rows = _paginate(qs, current, page_size)
    return JsonResponse({"total": total, "data": [_user_json(u) for u in rows]})


def peers(request):
    """GET /api/peers?current&pageSize&accessible&status -> {total, data}"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    current, page_size = _page_params(request)

    ab_ids = list(_accessible_abs(user).values_list("id", flat=True))
    raw_rows = list(AddressBookPeer.objects.filter(ab_id__in=ab_ids).select_related("ab__owner").order_by("id"))
    # 同一设备可能同时出现在个人簿与共享簿里，客户端按设备 ID 展示，这里先去重
    uniq = {}
    for p in raw_rows:
        uniq.setdefault(p.rid, p)
    rows = list(uniq.values())
    seen = set(uniq)
    group_names = _device_group_names(user)

    # rid -> API 账号名（客户端按 loginName 归属设备）
    owner_by_rid = {}
    for p in raw_rows:
        owner = p.ab.owner
        if owner is not None:
            owner_by_rid.setdefault(p.rid, owner.username)
    bindings = RustDeskPeer.objects.all()
    if user.is_admin:
        uid_names = {str(u.id): u.username for u in UserProfile.objects.all()}
    else:
        bindings = bindings.filter(uid=str(user.pk))
        uid_names = {str(user.pk): user.username}
    for rid, uid in bindings.values_list("rid", "uid"):
        if rid not in owner_by_rid and uid in uid_names:
            owner_by_rid[rid] = uid_names[uid]

    dev_info = _device_info_map(user)
    data = [_peer_payload(p, group_names, owner_by_rid.get(p.rid, ""), dev_info) for p in rows]
    devices = RustDesDevice.objects.order_by("-update_time")
    if not user.is_admin:
        devices = devices.filter(rid__in=owned_device_ids(user))
    for dev in devices:
        if dev.rid in seen:
            continue
        seen.add(dev.rid)
        data.append(
            {
                "id": dev.rid,
                "user": owner_by_rid.get(dev.rid) or dev.username or "",
                "user_name": owner_by_rid.get(dev.rid) or dev.username or "",
                "loginName": owner_by_rid.get(dev.rid, ""),
                "device_group_name": group_names.get(dev.rid, ""),
                "note": "",
                "status": 1,
                "info": {
                    "username": dev.username or "",
                    "device_name": dev.hostname or "",
                    "os": dev.os or "",
                },
                "hash": "",
                "password": "",
                "username": dev.username or "",
                "hostname": dev.hostname or "",
                "platform": _platform_from_os(dev.os),
                "alias": "",
                "tags": [],
            }
        )

    total = len(data)
    start = (current - 1) * page_size
    return JsonResponse({"total": total, "data": data[start : start + page_size]})


def peers_online(request):
    """POST /api/peers/online {"ids": [...]} -> {onlines, offlines}

    网页端的 hbbs WebSocket 桥不处理 OnlineRequest（桌面版走 TCP 21115 的
    create_online_stream），所以这里用设备心跳时间给出与桌面端一致的在线状态。
    """
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        payload = {}
    ids = payload.get("ids") if isinstance(payload, dict) else None
    if not isinstance(ids, list):
        ids = []
    seen = set()
    clean = []
    for value in ids:
        if value is None:
            continue
        rid = str(value).strip()
        if rid and rid not in seen:
            seen.add(rid)
            clean.append(rid)
    ids = clean[:500]
    if not user.is_admin:
        # 只允许查询自己能看到的设备，避免拿 9 位 ID 枚举在线状态。
        visible = set(AddressBookPeer.objects.filter(ab_id__in=_accessible_abs(user)).values_list("rid", flat=True))
        visible.update(row["rid"] for row in owned_device_ids(user))
        ids = [rid for rid in ids if rid in visible]
    if not ids:
        return JsonResponse({"onlines": [], "offlines": []})
    window = int(getattr(settings, "DEVICE_ONLINE_SECONDS", 300))
    cutoff = timezone.now() - timedelta(seconds=window)
    online = set(
        RustDesDevice.objects.filter(rid__in=ids, update_time__gte=cutoff).values_list("rid", flat=True).distinct()
    )
    return JsonResponse(
        {
            "onlines": [x for x in ids if x in online],
            "offlines": [x for x in ids if x not in online],
        }
    )


def device_groups(request):
    """GET /api/device-group/accessible?current&pageSize -> {total, data}"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    current, page_size = _page_params(request)
    qs = DeviceGroup.objects.filter(owner=user).order_by("id")
    total, rows = _paginate(qs, current, page_size)
    return JsonResponse(
        {
            "total": total,
            "data": [{"guid": g.guid, "name": g.name, "note": g.note or ""} for g in rows],
        }
    )


# --------------------------------------------------------------------------
# 设备维护 / 切换授权 / 录像
# --------------------------------------------------------------------------


def switch_grant(request):
    """保留客户端响应协议，当前服务未实现签名校验。"""
    return JsonResponse({"accepted": False, "server_time": int(time.time())})


def record_upload(request):
    """为历史客户端保留路由，停用未认证的录像写入协议。"""
    return JsonResponse({"error": _("服务端录像上传已停用")}, status=410)


def _clean_display_name(value, label):
    name = str(value or "").strip()
    if not name:
        return ""
    if len(name) > 64 or any(ord(ch) < 32 for ch in name):
        raise ValueError(label)
    return name


def _first_or_create(model, lookup, defaults=None):
    """同名数据可能重复：按 id 取最早一条，避免 get_or_create 抛 MultipleObjectsReturned。"""
    obj = model.objects.filter(**lookup).order_by("id").first()
    if obj is not None:
        return obj, False
    return model.objects.create(**lookup, **(defaults or {})), True


def devices_cli(request):
    """POST /api/devices/cli：把当前设备分配到用户/地址簿/分组。"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    if request.method != "POST":
        return HttpResponse(status=405)
    data = _body(request)
    rid = str(data.get("id", "")).strip()
    if not rid:
        return JsonResponse({"error": "missing id"}, status=400)
    rename = data.get("device_name") or data.get("device_username")
    if rename and not can_manage_device(user, rid, token):
        return JsonResponse({"error": _("没有修改该设备的权限")}, status=403)

    owner = user
    user_name = str(data.get("user_name", "")).strip()
    if user_name and user.is_admin:
        owner = UserProfile.objects.filter(username=user_name).first() or user

    # 先完成全部校验再落库，避免 400 响应留下半成品地址簿/分组。
    try:
        ab_name = _clean_display_name(data.get("address_book_name"), _("地址簿名称不合法"))
        group_name = _clean_display_name(data.get("device_group_name"), _("分组名称不合法"))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    raw_password = str(data.get("address_book_password") or "").strip()
    if len(raw_password) > 128:
        return JsonResponse({"error": _("地址簿密码过长")}, status=400)

    with transaction.atomic():
        if ab_name:
            ab, _created = _first_or_create(
                AddressBook,
                {"owner": owner, "name": ab_name, "is_personal": False},
                {"guid": uuid.uuid4().hex, "rule": 2},
            )
            peer, _created = AddressBookPeer.objects.get_or_create(ab=ab, rid=rid)
            tag = str(data.get("address_book_tag", "")).strip()
            if tag:
                AddressBookTag.objects.get_or_create(ab=ab, name=tag[:60])
                # CLI 是“追加分配”，不能清掉设备在共享簿里已有的标签。
                existing = [t for t in (peer.tags or "").split(",") if t]
                if tag[:60] not in existing:
                    existing.append(tag[:60])
                peer.tags = ",".join(existing)[:255]
            if data.get("address_book_alias"):
                peer.alias = str(data["address_book_alias"])[:30]
            if raw_password:
                # CLI 指定的地址簿是共享簿，密码按共享密码存储（不是个人簿 hash）。
                peer.password = raw_password[:128]
            if data.get("address_book_note"):
                peer.note = str(data["address_book_note"])
            peer.save()

        if group_name:
            group, _created = _first_or_create(
                DeviceGroup, {"owner": owner, "name": group_name}, {"guid": uuid.uuid4().hex}
            )
            DeviceGroupPeer.objects.get_or_create(group=group, rid=rid)

        if rename:
            dev = RustDesDevice.objects.filter(rid=rid).order_by("-update_time", "-id").first()
            if dev:
                if data.get("device_name"):
                    dev.hostname = str(data["device_name"])[:100]
                if data.get("device_username"):
                    dev.username = str(data["device_username"])[:100]
                dev.save(update_fields=["hostname", "username"])

    # CLI 以“空正文”判定成功并打印 Done!
    return HttpResponse(status=200)


def devices_deploy(request):
    """POST /api/devices/deploy  body {id, uuid, pk} -> {result: OK}"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    if request.method != "POST":
        return HttpResponse(status=405)
    data = _body(request)
    rid = str(data.get("id", "")).strip()
    uuid_str = str(data.get("uuid", "")).strip()
    pk = str(data.get("pk", "")).strip()
    if not rid or not uuid_str or not pk or len(rid) > 60 or len(uuid_str) > 100:
        return JsonResponse({"result": "INVALID_INPUT"})
    if not user.is_admin:
        # 换 ID 时正文 id 是新 ID，令牌里的 rid 还是旧 ID：以 uuid 绑定同一台物理设备，
        # 并要求旧 ID 确实归该用户，避免拿别人的设备令牌去抢注新 ID。
        if token.uuid != uuid_str:
            return JsonResponse({"result": "NOT_ENABLED"})
        if token.rid != rid and not can_manage_device(user, token.rid, token):
            return JsonResponse({"result": "NOT_ENABLED"})
        if rid != token.rid and device_is_assigned(rid):
            return JsonResponse({"result": "NOT_ENABLED"})
    if device_is_assigned(rid) and not can_manage_device(user, rid, token):
        return JsonResponse({"result": "NOT_ENABLED"})
    exists = RustDesDevice.objects.filter(rid=rid).exclude(uuid=uuid_str).first()
    if exists:
        return JsonResponse({"result": "ID_TAKEN"})
    dev = RustDesDevice.objects.filter(rid=rid, uuid=uuid_str).first()
    if dev is None:
        RustDesDevice.objects.create(rid=rid, uuid=uuid_str)
    return JsonResponse({"result": "OK"})


# --------------------------------------------------------------------------
# OIDC / 登录选项
# --------------------------------------------------------------------------


def login_options(request):
    """GET /api/login-options -> JSON 数组（字符串）。

    可配置多个第三方登录：第一项固定 `common-oidc/<json>`（新客户端一次性渲染全部
    按钮），其后每项 `oidc/<op>` 兼容只认单元素的旧客户端。
    """
    return JsonResponse(oauth.login_options(), safe=False)


def oidc_auth(request):
    """POST /api/oidc/auth -> {code, url}；code 供客户端轮询。"""
    if request.method != "POST":
        return JsonResponse({"error": _("请求方式错误！")})
    limit = getattr(settings, "OIDC_MAX_PER_HOUR", 60)
    if throttle.too_many("oidc", request, limit, 3600):
        return JsonResponse({"error": _("请求过于频繁，请稍后再试。")}, status=429)
    throttle.hit("oidc", request, 3600)
    providers = oauth.providers()
    if not providers:
        return JsonResponse({"error": _("未配置 OIDC 登录")})
    try:
        data = json.loads(request.body.decode() or "{}")
    except ValueError:
        return JsonResponse({"error": _("请求体不是合法的 JSON")})
    if not isinstance(data, dict):
        return JsonResponse({"error": _("请求体必须是 JSON 对象")})
    rid = str(data.get("id") or "").strip()[:100]
    if not rid:
        return JsonResponse({"error": _("缺少设备 ID")})
    op = str(data.get("op") or "").strip()[:64]
    provider = oauth.provider_for(op)
    if provider is None:
        return JsonResponse({"error": _("登录方式不存在或已停用")})
    api_domain = str(data.get("apiDomain") or "")
    try:
        state, verifier, url = oauth.begin_auth(provider, api_domain)
    except oidc.OidcError as exc:
        logger.warning("OIDC auth start failed: %s", exc)
        return JsonResponse({"error": str(exc)})
    OidcLogin.objects.create(
        state=state[:64],
        flow=OidcLogin.FLOW_CLIENT,
        rid=rid,
        uuid=str(data.get("uuid") or "")[:100],
        api_domain=api_domain[:255],
        op=provider.op[:64],
        code_verifier=verifier[:128],
    )
    oidc.cleanup_expired()
    return JsonResponse({"code": state, "url": url})


def oidc_auth_query(request):
    """GET /api/oidc/auth-query -> 未完成时返回客户端识别的固定错误。"""
    if request.method != "GET":
        return JsonResponse({"error": _("请求方式错误！")})
    state = request.GET.get("code", "")
    rid = request.GET.get("id", "")
    row = OidcLogin.objects.filter(state=state).first() if state else None
    if row is None or (row.rid and rid and row.rid != rid):
        return JsonResponse({"error": oidc.PENDING_ERROR})
    if row.completed_at is None or not row.access_token:
        if (timezone.now() - row.created_at).total_seconds() > oidc.LOGIN_TTL_SECONDS:
            row.delete()
        return JsonResponse({"error": oidc.PENDING_ERROR})
    token = RustDeskToken.objects.filter(access_token=row.access_token).first()
    user = row.user
    if token is None or user is None or (token.expires_at and token.expires_at <= timezone.now()):
        row.delete()
        return JsonResponse({"error": oidc.PENDING_ERROR})
    body = {
        "access_token": token.access_token,
        "type": "access_token",
        "tfa_type": "",
        "secret": "",
        "user": oidc.user_payload(user),
    }
    row.delete()
    return JsonResponse(body)


def console_oauth_start(request):
    """GET /api/oidc/console/auth?op=xxx：控制台登录页的第三方登录入口。

    与客户端流程共用一套 provider/OidcLogin 状态机，区别有两点：
    回调基址取浏览器当前访问的域名（`api_domain`），登录成功后建立 Session 而非签发令牌。
    """
    if request.method != "GET":
        return oidc.render_page("登录失败", "不支持的请求方式。", 405)
    limit = getattr(settings, "OIDC_MAX_PER_HOUR", 60)
    if throttle.too_many("oidc", request, limit, 3600):
        return oidc.render_page("登录失败", "请求过于频繁，请稍后再试。", 429)
    throttle.hit("oidc", request, 3600)
    op = str(request.GET.get("op") or "").strip()[:64]
    provider = oauth.provider_for(op)
    if provider is None:
        return oidc.render_page("登录失败", "登录方式不存在或已停用。", 400)
    api_domain = request.build_absolute_uri("/")[:255]
    try:
        state, verifier, url = oauth.begin_auth(provider, api_domain)
    except oidc.OidcError as exc:
        logger.warning("Console OIDC auth start failed: %s", exc)
        return oidc.render_page("登录失败", str(exc), 400)
    OidcLogin.objects.create(
        state=state[:64],
        flow=OidcLogin.FLOW_CONSOLE,
        api_domain=api_domain,
        op=provider.op[:64],
        code_verifier=verifier[:128],
    )
    if request.GET.get("next") == "/web/":
        request.session["oidc_console_next"] = "/web/"
    else:
        request.session.pop("oidc_console_next", None)
    oidc.cleanup_expired()
    response = HttpResponseRedirect(url)
    response.set_cookie(
        CONSOLE_STATE_COOKIE,
        state,
        max_age=oidc.LOGIN_TTL_SECONDS,
        httponly=True,
        samesite="Lax",
        secure=bool(getattr(settings, "HTTPS", False)),
        path="/",
    )
    return response


def oidc_callback(request):
    """IdP 回调：换取 token、建立账号，客户端随后轮询 auth-query。"""
    if request.method != "GET":
        return oidc.render_page("登录失败", "不支持的请求方式。", 405)
    state = request.GET.get("state", "")
    code = request.GET.get("code", "")
    row = OidcLogin.objects.filter(state=state).first() if state else None
    if row is None:
        return oidc.render_page("登录失败", "登录请求不存在或已过期，请重新发起登录。", 400)
    if (timezone.now() - row.created_at).total_seconds() > oidc.LOGIN_TTL_SECONDS:
        row.delete()
        return oidc.render_page("登录失败", "登录请求已过期，请重新发起登录。", 400)
    if request.GET.get("error"):
        reason = request.GET.get("error_description") or request.GET.get("error")
        row.delete()
        return oidc.render_page("登录失败", "身份提供方返回了错误：{}".format(reason), 400)
    if not code:
        return oidc.render_page("登录失败", "缺少授权码，请重新发起登录。", 400)
    provider = oauth.provider_for(row.op)
    if provider is None:
        row.delete()
        return oidc.render_page("登录失败", "该登录方式已被删除或停用，请重新发起登录。", 400)
    is_console = row.flow == OidcLogin.FLOW_CONSOLE
    if is_console and request.COOKIES.get(CONSOLE_STATE_COOKIE, "") != state:
        row.delete()
        return oidc.render_page("登录失败", "登录请求与当前浏览器不匹配，请重新发起登录。", 400)
    try:
        if is_console:
            user = oauth.complete_console_login(provider, row, code)
            token = None
        else:
            user, token = oauth.complete_login(provider, row, code)
    except oidc.OidcError as exc:
        # 已知的业务失败（邮箱未验证、账号被禁用、已绑定其他身份等）直接回显，
        # 让用户知道该找管理员处理什么，而不是笼统的"无法完成登录"。
        logger.info("OIDC callback rejected: %s", exc)
        row.delete()
        return oidc.render_page("登录失败", str(exc), 400)
    except Exception as exc:  # noqa: BLE001 - 对浏览器只给通用错误，细节写日志
        logger.warning("OIDC callback failed: %s", exc)
        row.delete()
        return oidc.render_page("登录失败", "无法完成登录，请重试或联系管理员。", 400)
    if is_console:
        # 控制台流程：建立浏览器会话后回控制台（或白名单 /web/）；OidcLogin 行用完即删。
        row.delete()
        next_url = request.session.pop("oidc_console_next", "")
        target = "/web/" if next_url == "/web/" else "/console/"
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        UserProfile.objects.filter(pk=user.pk).update(last_login=timezone.now())
        response = HttpResponseRedirect(target)
        response.delete_cookie(CONSOLE_STATE_COOKIE, path="/")
        return response
    row.completed_at = timezone.now()
    row.access_token = token.access_token
    row.user = user
    row.save(update_fields=["completed_at", "access_token", "user"])
    return oidc.render_page("登录成功", "已完成认证，请返回 RustDesk 客户端。")


# --------------------------------------------------------------------------
# 审计
# --------------------------------------------------------------------------


def visible_connection_logs(user, token):
    logs = ConnLog.objects.all()
    if user.is_admin:
        return logs
    owned = owned_device_ids(user)
    visible = Q(rid__in=owned) | Q(from_id__in=owned)
    if can_manage_device(user, token.rid, token):
        visible |= Q(rid=token.rid) | Q(from_id=token.rid)
    return logs.filter(visible)


def audit_active(request):
    """GET /api/audit/conn/active?id=&session_id=&conn_type= -> JSON 字符串 guid"""
    if request.method != "GET":
        return HttpResponse(status=405)
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    rid = request.GET.get("id", "")
    session_id = request.GET.get("session_id", "")
    if not rid:
        # 契约要求返回 JSON 字符串；缺 id 时给空串，客户端会直接跳过。
        return JsonResponse("", safe=False)
    logs = visible_connection_logs(user, token).filter(rid=rid, action="new", conn_end__isnull=True)
    if session_id:
        logs = logs.filter(session_id=session_id)
    conn = logs.order_by("-id").first()
    # 契约要求返回一个 JSON 字符串；没有进行中的连接时返回空串，客户端可直接跳过。
    return JsonResponse(str(conn.id) if conn else "", safe=False)


def health(request):
    """GET /api/health：部署健康检查（数据库 + 缓存 + 版本号）。

    数据库不可用时返回 503；缓存不可用只算 degraded（仍返回 200），
    避免缓存故障把正常流量从负载均衡上摘掉。
    """
    from django.core.cache import cache
    from django.db import connections

    from version import APP_VERSION

    db_ok = True
    try:
        with connections["default"].cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception:
        db_ok = False

    cache_ok = True
    try:
        cache.set("health:ping", "1", 5)
        cache_ok = cache.get("health:ping") == "1"
    except Exception:
        cache_ok = False

    if not db_ok:
        status = "error"
    elif not cache_ok:
        status = "degraded"
    else:
        status = "ok"

    # 版本/数据库/缓存/调试信息只给本机或持有 HEALTH_TOKEN 的监控；公网只暴露状态。
    token = getattr(settings, "HEALTH_TOKEN", "")
    from django.utils.crypto import constant_time_compare

    from api import throttle

    remote = throttle._client_ip(request)
    private_nets = [
        ipaddress.ip_network(n)
        for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "::1/128", "fc00::/7")
    ]
    try:
        addr = ipaddress.ip_address(remote)
        internal = any(addr in net for net in private_nets)
    except ValueError:
        internal = False
    header_token = request.headers.get("X-Health-Token", "")
    privileged = internal or (bool(token) and bool(header_token) and constant_time_compare(header_token, token))
    if not privileged:
        return JsonResponse({"status": status}, status=200 if db_ok else 503)

    payload = {
        "status": status,
        "version": APP_VERSION,
        "database": "ok" if db_ok else "error",
        "cache": "ok" if cache_ok else "error",
        "cache_backend": getattr(settings, "CACHE_BACKEND", "unknown"),
        "debug": bool(settings.DEBUG),
    }
    return JsonResponse(payload, status=200 if db_ok else 503)


def _default_webclient_id_server(request):
    """未显式配置 ID_SERVER 时推导网页远控的默认信令地址。

    Web 核心对不带协议的 IP 字面量会把端口 +2（21116 -> 21118），对不带协议的域名会
    直接走 /ws/id 并丢弃非标准端口；只有显式 ws(s):// 地址才能把 IP 或非默认端口
    准确路由到同源反代的 /ws/id。
    """
    host = request.get_host()
    parsed = urlsplit(f"http://{host}")
    hostname = parsed.hostname or ""
    has_port = parsed.port is not None
    try:
        ipaddress.ip_address(hostname)
        is_ip = True
    except ValueError:
        is_ip = False

    if getattr(settings, "INTERNAL_PROXY", False) or getattr(settings, "BEHIND_PROXY", False):
        if is_ip or has_port:
            scheme = "wss" if request.is_secure() else "ws"
            return f"{scheme}://{host}"
        return host

    # 免安装包 / 直连 Django（无同源 /ws/id 反代）：去掉 HTTP 端口（如 21114），
    # 让 Web 核心按默认协议直接连接同机 hbbs 的 21118。
    if has_port and hostname:
        return f"[{hostname}]" if ":" in hostname else hostname
    return host


def webclient_config(request):
    """网页远控的运行时配置（/api/webclient/config.js 与 /web/rd-config.js）。

    仅向已登录且启用的控制台会话下发：
    - 避免匿名抓取 RUSTDESK_KEY 或跨站 XSSI 读取内网配置；
    - 随配置下发当前会话绑定的 RustDesk Bearer 令牌与用户信息，Web 客户端自动复用控制台登录态。
    """
    if request.method not in ("GET", "HEAD"):
        return HttpResponse(status=405)

    from api.webclient import ensure_web_token

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_active:
        resp = HttpResponse(
            "/* unauthorized */\n",
            status=401,
            content_type="application/javascript; charset=utf-8",
        )
        resp["Cache-Control"] = "no-store"
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Cross-Origin-Resource-Policy"] = "same-origin"
        return resp

    id_server = settings.ID_SERVER or _default_webclient_id_server(request)
    # build_absolute_uri 会保留非 443/80 的端口；直接拼 host 会让本地 21114/21205 部署把 API 指到 80。
    api_server = settings.API_SERVER or request.build_absolute_uri("/").rstrip("/")
    web_token = ensure_web_token(request, user)
    payload = {
        "force": True,
        "idServer": id_server,
        "apiServer": api_server,
        "relayServer": settings.RELAY_SERVER,
        "key": settings.RUSTDESK_KEY,
        "accessToken": web_token.access_token,
        "userInfo": _user_json(user),
        "authCheckUrl": "/api/webclient/auth",
        "loginUrl": "/console/?next=/web/",
        "sessionId": web_token.rid,
    }
    serialized = (
        json.dumps(payload, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    response = HttpResponse(
        "window.RD_CONFIG = " + serialized + ";\n",
        content_type="application/javascript; charset=utf-8",
    )
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cross-Origin-Resource-Policy"] = "same-origin"
    return response
