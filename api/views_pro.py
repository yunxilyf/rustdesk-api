"""RustDesk 新版客户端 API。

旧版兼容接口在 views_api.py，本模块提供新版客户端使用的接口：
- /api/login-options、/api/oidc/*
- /api/ab/personal、/api/ab/settings、/api/ab/shared/profiles
- /api/ab/peers、/api/ab/tags/<guid>、/api/ab/peer|tag/*
- /api/users、/api/peers、/api/device-group/accessible
- /api/switch-grant、/api/record、/api/devices/cli、/api/devices/deploy
- /api/audit/conn/active
"""

import json
import os
import re
import time
import uuid
import datetime

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _

from .tag_colors import normalize_color
from .models import (
    AddressBook,
    AddressBookPeer,
    AddressBookTag,
    ConnLog,
    DeviceGroup,
    DeviceGroupPeer,
    DeviceRecord,
    RustDesDevice,
    RustDeskPeer,
    RustDeskTag,
    RustDeskToken,
    SwitchGrant,
    UserProfile,
)

PAGE_SIZE_DEFAULT = 100


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


def _device_info_map():
    """rid -> 最近一次 sysinfo 上报的 platform/hostname/username。"""
    latest = {}
    for d in RustDesDevice.objects.order_by("rid", "-update_time", "-id"):
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


def token_user(token):
    """校验 token 是否仍有效，返回用户；无效时返回 None。

    旧数据没有 expires_at：首次使用时补写一个完整有效期，让老客户端平滑升级，
    之后按 expires_at 判断（不再永久有效）。
    """
    if not token:
        return None
    from .views_front import EFFECTIVE_SECONDS

    now = timezone.now()
    if token.expires_at is None:
        token.expires_at = now + datetime.timedelta(seconds=EFFECTIVE_SECONDS)
        token.save(update_fields=["expires_at"])
    elif token.expires_at < now:
        return None
    return UserProfile.objects.filter(id=token.uid, is_active=True).first()


def _auth(request):
    """返回 (token, user)，未登录/过期时返回 (None, None)。"""
    auth = request.META.get("HTTP_AUTHORIZATION", "") or ""
    if auth.startswith("Bearer "):
        auth = auth[len("Bearer ") :]
    auth = auth.strip()
    if not auth:
        return None, None
    token = RustDeskToken.objects.filter(access_token=auth).first()
    user = token_user(token)
    if not user:
        return None, None
    return token, user


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
    ab = AddressBook.objects.filter(owner=user, is_personal=True).first()
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


def _get_ab(user, guid):
    """按 guid 取地址簿；guid 为空时取个人地址簿。"""
    if not guid:
        return _personal_ab(user)
    ab = AddressBook.objects.filter(guid=guid).first()
    if ab is None:
        return None
    if ab.owner_id != user.id and ab.rule <= 0:
        return None
    return ab


def _peer_json(peer, group_names=None, dev_info=None):
    tags = [t for t in (peer.tags or "").split(",") if t]
    info = (dev_info or {}).get(peer.rid) or {}
    return {
        "id": peer.rid,
        "hash": peer.rhash or "",
        "password": peer.password or "",
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
        "same_server": True,
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
    ab = AddressBook.objects.filter(owner=user, is_personal=True).first()
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
    dev_info = _device_info_map()
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
    ab = _get_ab(user, guid)
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
            "rhash": str(data.get("hash", "")),
            "password": str(data.get("password", "")),
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
        _apply_peer_fields(peer, data)
        peer.save()
    return _empty_ok()


def ab_peer_update(request, guid):
    """PUT /api/ab/peer/update/<guid>，body {id, ...要改的字段}。"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    ab = _get_ab(user, guid)
    if ab is None:
        return JsonResponse({"error": _("地址簿不存在")}, status=404)
    data = _body(request)
    rid = str(data.get("id", "")).strip()
    peer = ab.peers.filter(rid=rid).first() if rid else None
    if peer is None:
        return JsonResponse({"error": _("设备不存在")}, status=404)
    _apply_peer_fields(peer, data)
    peer.save()
    return _empty_ok()


def _apply_peer_fields(peer, data):
    if "hash" in data:
        peer.rhash = str(data.get("hash") or "")
    if "password" in data:
        peer.password = str(data.get("password") or "")
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
    ab = _get_ab(user, guid)
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
    ab = _get_ab(user, guid)
    if ab is None:
        return JsonResponse({"error": _("地址簿不存在")}, status=404)
    data = _body(request)
    name = str(data.get("name", "")).strip()
    if not name:
        return JsonResponse({"error": _("缺少标签名")}, status=400)
    AddressBookTag.objects.update_or_create(
        ab=ab, name=name, defaults={"color": normalize_color(data.get("color"), name)}
    )
    return _empty_ok()


def ab_tag_rename(request, guid):
    """PUT /api/ab/tag/rename/<guid>，body {old, new}。"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    ab = _get_ab(user, guid)
    if ab is None:
        return JsonResponse({"error": _("地址簿不存在")}, status=404)
    data = _body(request)
    old = str(data.get("old", ""))
    new = str(data.get("new", ""))
    tag = ab.tags.filter(name=old).first()
    if tag is None:
        return JsonResponse({"error": _("标签不存在")}, status=404)
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
    ab = _get_ab(user, guid)
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
    ab = _get_ab(user, guid)
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
        qs = UserProfile.objects.filter(id=user.id)
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
    uid_names = {str(u.id): u.username for u in UserProfile.objects.all()}
    for rid, uid in RustDeskPeer.objects.values_list("rid", "uid"):
        if rid not in owner_by_rid and uid in uid_names:
            owner_by_rid[rid] = uid_names[uid]

    dev_info = _device_info_map()
    data = [_peer_payload(p, group_names, owner_by_rid.get(p.rid, ""), dev_info) for p in rows]
    visible_rids = set(owner_by_rid)
    for dev in RustDesDevice.objects.all().order_by("-update_time"):
        if dev.rid in seen:
            continue
        # 非管理员只看到自己/共享地址簿里的设备，未归属设备仅管理员可见
        if not user.is_admin and dev.rid not in visible_rids:
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
    """POST /api/switch-grant，返回 {accepted, server_time}。"""
    data = _body(request)
    now = int(time.time())
    rid = str(data.get("id", ""))
    SwitchGrant.objects.create(
        rid=rid,
        verifier=str(data.get("switch_code_verifier", ""))[:128],
        timestamp=str(data.get("timestamp", ""))[:32],
        signature=str(data.get("signature", "")),
    )
    return JsonResponse({"accepted": True, "server_time": now})


def record_upload(request):
    """POST /api/record?type=new|part|tail|remove&file=&offset=&length="""
    typ = request.GET.get("type", "")
    filename = os.path.basename((request.GET.get("file", "") or "").replace("\\", "/"))
    if not filename or filename in (".", ".."):
        return JsonResponse({"error": "missing file"}, status=400)
    # 只保留安全字符，避免路径穿越与非法文件名
    filename = re.sub(r"[^0-9A-Za-z._\- ()\[\]]", "_", filename)[:200]
    if filename.strip(". ") == "":
        return JsonResponse({"error": "invalid file"}, status=400)

    record_dir = str(getattr(settings, "RECORD_ROOT", os.path.join(str(settings.BASE_DIR), "records")))
    os.makedirs(record_dir, exist_ok=True)
    path = os.path.join(record_dir, filename)
    if typ in ("new", "part", "tail"):
        # 这个接口没有认证（客户端协议如此），至少给目录设配额，避免被匿名写满磁盘。
        quota = getattr(settings, "RECORD_MAX_TOTAL_MB", 2048) * 1024 * 1024
        used = 0
        for entry in os.scandir(record_dir):
            if entry.is_file():
                used += entry.stat().st_size
        if used >= quota:
            return JsonResponse({"error": "record storage quota exceeded"}, status=507)
    # 先看 Content-Length，避免把超大请求体读进内存
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        declared = 0
    if declared > 8 * 1024 * 1024:
        return JsonResponse({"error": "chunk too large"}, status=413)
    if request.body and len(request.body) > 8 * 1024 * 1024:
        return JsonResponse({"error": "chunk too large"}, status=413)

    if typ == "new":
        DeviceRecord.objects.filter(file=filename).delete()
        DeviceRecord.objects.create(file=filename, path=path, size=0)
        with open(path, "wb") as f:
            pass
    elif typ in ("part", "tail"):
        # part: offset 处续写；tail: offset=0 回写文件头（客户端用它标记上传完成）
        try:
            offset = int(request.GET.get("offset", 0) or 0)
        except (TypeError, ValueError):
            offset = 0
        chunk = request.body or b""
        mode = "r+b" if os.path.isfile(path) else "wb"
        with open(path, mode) as f:
            f.seek(offset)
            f.write(chunk)
        size = os.path.getsize(path)
        DeviceRecord.objects.filter(file=filename).update(size=size)
    elif typ == "remove":
        if os.path.isfile(path):
            os.remove(path)
        DeviceRecord.objects.filter(file=filename).delete()
    return JsonResponse({"code": 1})


def devices_cli(request):
    """POST /api/devices/cli：把当前设备分配到用户/地址簿/分组。"""
    token, user = _auth(request)
    if user is None:
        return _unauthorized()
    data = _body(request)
    rid = str(data.get("id", "")).strip()
    if not rid:
        return JsonResponse({"error": "missing id"}, status=400)

    owner = user
    user_name = str(data.get("user_name", "")).strip()
    if user_name and user.is_admin:
        owner = UserProfile.objects.filter(username=user_name).first() or user

    ab_name = str(data.get("address_book_name", "")).strip()
    if ab_name:
        ab = AddressBook.objects.filter(owner=owner, name=ab_name).first()
        if ab is None:
            ab = AddressBook.objects.create(guid=uuid.uuid4().hex, owner=owner, name=ab_name, is_personal=True)
        peer, _created = AddressBookPeer.objects.get_or_create(ab=ab, rid=rid)
        tag = str(data.get("address_book_tag", "")).strip()
        if tag:
            AddressBookTag.objects.get_or_create(ab=ab, name=tag)
            peer.tags = tag
        if data.get("address_book_alias"):
            peer.alias = str(data["address_book_alias"])
        if data.get("address_book_password"):
            peer.rhash = str(data["address_book_password"])
        if data.get("address_book_note"):
            peer.note = str(data["address_book_note"])
        peer.save()

    group_name = str(data.get("device_group_name", "")).strip()
    if group_name:
        group = DeviceGroup.objects.filter(owner=owner, name=group_name).first()
        if group is None:
            group = DeviceGroup.objects.create(guid=uuid.uuid4().hex, owner=owner, name=group_name)
        DeviceGroupPeer.objects.get_or_create(group=group, rid=rid)

    dev = RustDesDevice.objects.filter(rid=rid).first()
    if dev:
        if data.get("device_name"):
            dev.hostname = str(data["device_name"])
        if data.get("device_username"):
            dev.username = str(data["device_username"])
        dev.save()

    # CLI 以“空正文”判定成功并打印 Done!
    return HttpResponse(status=200)


def devices_deploy(request):
    """POST /api/devices/deploy  body {id, uuid, pk} -> {result: OK}"""
    data = _body(request)
    rid = str(data.get("id", "")).strip()
    uuid_str = str(data.get("uuid", "")).strip()
    pk = str(data.get("pk", "")).strip()
    if not rid or not uuid_str or not pk:
        return JsonResponse({"result": "INVALID_INPUT"})
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
    """GET /api/login-options -> JSON 数组（字符串）。"""
    return JsonResponse([], safe=False)


def oidc_auth(request):
    return JsonResponse({"error": _("未配置 OIDC 登录")})


def oidc_auth_query(request):
    return JsonResponse({"error": _("未配置 OIDC 登录")})


# --------------------------------------------------------------------------
# 审计
# --------------------------------------------------------------------------


def audit_active(request):
    """GET /api/audit/conn/active?id=&session_id=&conn_type= -> JSON 字符串 guid"""
    rid = request.GET.get("id", "")
    session_id = request.GET.get("session_id", "")
    conn = None
    if session_id:
        conn = ConnLog.objects.filter(rid=rid, session_id=session_id).order_by("-id").first()
    if conn is None and rid:
        conn = ConnLog.objects.filter(rid=rid).order_by("-id").first()
    if conn is None:
        conn = ConnLog.objects.create(rid=rid, action="new", session_id=session_id, conn_start=datetime.datetime.now())
    return JsonResponse(str(conn.id), safe=False)


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
    payload = {
        "status": status,
        "version": APP_VERSION,
        "database": "ok" if db_ok else "error",
        "cache": "ok" if cache_ok else "error",
        "cache_backend": getattr(settings, "CACHE_BACKEND", "unknown"),
        "debug": bool(settings.DEBUG),
    }
    return JsonResponse(payload, status=200 if db_ok else 503)
