"""RustDesk 客户端核心接口：登录、旧版地址簿、sysinfo、心跳与审计。

登录状态使用 ``RustDeskToken.access_token``（Bearer），不使用 Cookie / Session。
"""

import datetime
import json
import logging
import math
import time
import uuid as uuidlib

from django.conf import settings
from django.contrib import auth
from django.db.models import Q
from django.http import HttpResponse, JsonResponse

from api.models import (
    AddressBook,
    AddressBookPeer,
    AddressBookTag,
    ConnLog,
    DeviceGroup,
    DeviceGroupPeer,
    FileLog,
    RustDesDevice,
    RustDeskToken,
    UserProfile,
)
from . import views_pro
from . import throttle
from api.tag_colors import normalize_color
from .views_front import EFFECTIVE_SECONDS, getStrMd5, salt

logger = logging.getLogger(__name__)
from django.utils.translation import gettext as _


def login(request):
    result = {}
    if request.method != "POST":
        result["error"] = _("请求方式错误！请使用POST方式。")
        return JsonResponse(result)

    try:
        data = json.loads(request.body.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": _("请求体不是合法的 JSON")}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": _("请求体格式错误")}, status=400)

    username = data.get("username", "")
    password = data.get("password", "")
    rid = data.get("id", "")
    uuid = data.get("uuid", "")
    autoLogin = data.get("autoLogin", True)
    rtype = data.get("type", "")
    deviceInfo = data.get("deviceInfo", "")
    if throttle.blocked("api", request, username):
        return JsonResponse({"error": _("尝试次数过多，请稍后再试。")}, status=429)
    user = auth.authenticate(username=username, password=password)
    if not user:
        throttle.fail("api", request, username)
        result["error"] = _("帐号或密码错误！请重试，多次重试后将被锁定IP！")
        return JsonResponse(result)
    throttle.reset("api", request, username)
    if not user.is_active:
        result["error"] = _("该帐号已被禁用！")
        return JsonResponse(result)
    user.rid = rid
    user.uuid = uuid
    user.autoLogin = autoLogin
    user.rtype = rtype
    user.deviceInfo = json.dumps(deviceInfo)
    user.save()

    now = datetime.datetime.now()
    ttl = datetime.timedelta(seconds=EFFECTIVE_SECONDS)
    token = RustDeskToken.objects.filter(Q(uid=user.id) & Q(username=user.username) & Q(rid=user.rid)).first()
    if token and token.expires_at is not None and token.expires_at < now:
        token.delete()
        token = None
    if token:
        # 同一账号重新登录：续满有效期，并同步设备 uuid。
        token.uuid = user.uuid
        token.expires_at = now + ttl
        token.save(update_fields=["uuid", "expires_at"])
    else:
        token = RustDeskToken(
            username=user.username,
            uid=user.id,
            uuid=user.uuid,
            rid=user.rid,
            access_token=getStrMd5(str(time.time()) + salt + username),
            expires_at=now + ttl,
        )
        token.save()

    result["access_token"] = token.access_token
    result["type"] = "access_token"
    result["user"] = views_pro._user_json(user)
    return JsonResponse(result)


def logout(request):
    if request.method != "POST":
        return JsonResponse({"error": _("请求方式错误！")})

    try:
        data = json.loads(request.body.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": _("请求体不是合法的 JSON")}, status=400)
    rid = data.get("id", "")
    uuid = data.get("uuid", "")
    user = UserProfile.objects.filter(Q(rid=rid) & Q(uuid=uuid)).first()
    if not user:
        return JsonResponse({"error": _("异常请求！")})
    token = RustDeskToken.objects.filter(Q(uid=user.id) & Q(rid=user.rid)).first()
    if token:
        token.delete()

    return JsonResponse({"code": 1})


def currentUser(request):
    result = {}
    if request.method == "GET":
        result["error"] = _("错误的提交方式！")
        return JsonResponse(result)

    access_token = request.META.get("HTTP_AUTHORIZATION", "")
    if access_token.startswith("Bearer "):
        access_token = access_token[len("Bearer ") :]
    token = RustDeskToken.objects.filter(access_token=access_token).first()
    user = views_pro.token_user(token)

    if not user:
        result["error"] = _("未登录或登录已过期")
        return JsonResponse(result, status=401)

    if token:
        result["access_token"] = token.access_token
    result["type"] = "access_token"
    result.update(views_pro._user_json(user))
    return JsonResponse(result)


def ab(request):
    """旧版地址簿接口：GET 拉取 / POST 覆盖提交。"""
    access_token = request.META.get("HTTP_AUTHORIZATION", "")
    if access_token.startswith("Bearer "):
        access_token = access_token[len("Bearer ") :]
    token = RustDeskToken.objects.filter(access_token=access_token).first()
    user = views_pro.token_user(token)
    if not user:
        return JsonResponse({"error": _("未登录或登录已过期")}, status=401)

    ab_obj = views_pro._legacy_to_ab(user)

    if request.method == "GET":
        tags = list(ab_obj.tags.all().order_by("id"))
        tag_names = [t.name for t in tags]
        tag_colors = {t.name: normalize_color(t.color, t.name) for t in tags}

        dev_info = views_pro._device_info_map()
        peers_result = []
        for peer in ab_obj.peers.all().order_by("id"):
            info = dev_info.get(peer.rid) or {}
            peers_result.append(
                {
                    "id": peer.rid,
                    "username": peer.username or info.get("username", ""),
                    "hostname": peer.hostname or info.get("hostname", ""),
                    "alias": peer.alias,
                    "platform": peer.platform or info.get("platform", ""),
                    "tags": [t for t in (peer.tags or "").split(",") if t],
                    "hash": peer.rhash,
                }
            )

        data = {
            "tags": tag_names,
            "peers": peers_result,
            "tag_colors": json.dumps(tag_colors),
        }
        return JsonResponse({"updated_at": datetime.datetime.now(), "data": json.dumps(data)})

    try:
        postdata = json.loads(request.body.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": _("请求体不是合法的 JSON")}, status=400)
    if not isinstance(postdata, dict):
        return JsonResponse({"error": _("请求体格式错误")}, status=400)
    data = postdata.get("data", "")
    try:
        data = {} if not data else json.loads(data)
    except (ValueError, TypeError):
        return JsonResponse({"error": _("data 字段不是合法的 JSON")}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": _("data 字段格式错误")}, status=400)

    if "tags" in data:
        tagnames = data.get("tags") or []
        tag_colors = data.get("tag_colors") or ""
        if isinstance(tag_colors, str):
            try:
                tag_colors = json.loads(tag_colors) if tag_colors else {}
            except ValueError:
                return JsonResponse({"error": _("tag_colors 不是合法的 JSON")}, status=400)
        ab_obj.tags.all().delete()
        for name in tagnames:
            AddressBookTag.objects.create(ab=ab_obj, name=name, color=normalize_color(tag_colors.get(name, 0), name))

    if "peers" in data:
        peers = data.get("peers") or []
        ab_obj.peers.all().delete()
        for one in peers:
            AddressBookPeer.objects.create(
                ab=ab_obj,
                rid=str(one.get("id", "")),
                rhash=one.get("hash", ""),
                password=one.get("password", ""),
                username=one.get("username", ""),
                hostname=one.get("hostname", ""),
                platform=one.get("platform", ""),
                alias=one.get("alias", ""),
                tags=",".join(one.get("tags") or []),
                note=one.get("note", ""),
            )

    return JsonResponse({"code": 1, "data": "ok"})


def ab_get(request):
    # 兼容 x86-sciter 版客户端，此版客户端通过访问 "POST /api/ab/get" 来获取地址簿
    request.method = "GET"
    return ab(request)


def sysinfo(request):
    """POST /api/sysinfo，成功必须返回字面量 SYSINFO_UPDATED。"""
    if request.method == "GET":
        return JsonResponse({"error": _("错误的提交方式！")})

    try:
        postdata = json.loads(request.body.decode() or "{}")
    except ValueError:
        return HttpResponse("ID_NOT_FOUND", content_type="text/plain")

    rid = str(postdata.get("id", "")).strip()
    uuid = str(postdata.get("uuid", "")).strip()
    if not rid or not uuid:
        return HttpResponse("ID_NOT_FOUND", content_type="text/plain")

    device = RustDesDevice.objects.filter(rid=rid).order_by("-update_time", "-id").first()
    fields = {
        "rid": rid,
        "uuid": uuid,
        "cpu": str(postdata.get("cpu", ""))[:100],
        "hostname": str(postdata.get("hostname", ""))[:100],
        "memory": str(postdata.get("memory", ""))[:100],
        "os": str(postdata.get("os", ""))[:100],
        "username": str(postdata.get("username", "-"))[:100],
        "version": str(postdata.get("version", ""))[:100],
    }
    if device is None:
        device = RustDesDevice(**fields)
        device.save()
    else:
        RustDesDevice.objects.filter(id=device.id).update(**fields)

    _apply_presets(rid, uuid, postdata)
    return HttpResponse("SYSINFO_UPDATED", content_type="text/plain")


def _apply_presets(rid, uuid, postdata):
    """处理客户端 preset-* 字段：改名 / 自动加入地址簿 / 设备分组。

    1.5.x 客户端实际发送的键：preset-address-book-name/tag/alias/password/note、
    preset-device-name、preset-device-username、preset-note。
    """
    device_fields = {}
    if postdata.get("preset-device-name"):
        device_fields["hostname"] = str(postdata["preset-device-name"])[:100]
    if postdata.get("preset-device-username"):
        device_fields["username"] = str(postdata["preset-device-username"])[:100]
    if device_fields:
        RustDesDevice.objects.filter(Q(rid=rid) & Q(uuid=uuid)).update(**device_fields)

    user = UserProfile.objects.filter(Q(rid=rid) & Q(uuid=uuid)).first()
    if user is None:
        return

    ab_name = str(postdata.get("preset-address-book-name", "")).strip()
    if ab_name:
        ab_obj = AddressBook.objects.filter(owner=user, name=ab_name).first()
        if ab_obj is None:
            ab_obj = AddressBook.objects.create(guid=uuidlib.uuid4().hex, owner=user, name=ab_name, is_personal=True)
        peer, _created = AddressBookPeer.objects.get_or_create(ab=ab_obj, rid=rid)
        tag = str(postdata.get("preset-address-book-tag", "")).strip()
        if tag:
            AddressBookTag.objects.get_or_create(ab=ab_obj, name=tag)
            peer.tags = tag
        alias = str(postdata.get("preset-address-book-alias", "")).strip()
        if alias:
            peer.alias = alias
        password = str(postdata.get("preset-address-book-password", "")).strip()
        if password:
            peer.rhash = password
        note = str(postdata.get("preset-address-book-note", "") or postdata.get("preset-note", "")).strip()
        if note:
            peer.note = note[:200]
        peer.save()

    group_name = str(postdata.get("preset-device-group-name", "")).strip()
    if group_name:
        group = DeviceGroup.objects.filter(owner=user, name=group_name).first()
        if group is None:
            group = DeviceGroup.objects.create(guid=uuidlib.uuid4().hex, owner=user, name=group_name)
        DeviceGroupPeer.objects.get_or_create(group=group, rid=rid)


def sysinfo_ver(request):
    """POST /api/sysinfo_ver，返回服务端 sysinfo 版本号（任意字符串）。"""
    return HttpResponse("1", content_type="text/plain")


def heartbeat(request):
    """客户端每 15 秒一次的心跳。

    关键约束：这是全站 QPS 最高的接口，必须做到「常态零写入」。
    - 设备在线时间戳最多每 HEARTBEAT_DEVICE_TOUCH_SECONDS 秒写一次；
    - token 只在剩余有效期不足 HEARTBEAT_TOKEN_REFRESH_SECONDS 秒时续期。
    写操作从「每次心跳 2 条 UPDATE」降到「每台设备几分钟 1 条」，
    否则数据库写锁会先于 Python 成为瓶颈。
    """
    try:
        postdata = json.loads(request.body.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": _("请求体不是合法的 JSON")}, status=400)
    if not isinstance(postdata, dict):
        return JsonResponse({"error": _("请求体格式错误")}, status=400)
    rid = str(postdata.get("id", ""))
    uuid = str(postdata.get("uuid", ""))
    now = datetime.datetime.now()

    # 设备身份以 rid 为准：客户端升级/重装后 uuid 会变，
    # 旧写法按 rid+uuid 查找会找不到设备，导致在线状态永远不刷新。
    device = RustDesDevice.objects.filter(rid=rid).only("id", "update_time").order_by("-update_time", "-id").first()
    if device:
        last = device.update_time
        if not last or (now - last).total_seconds() >= settings.HEARTBEAT_DEVICE_TOUCH_SECONDS:
            RustDesDevice.objects.filter(pk=device.pk).update(update_time=now)

    token = RustDeskToken.objects.filter(Q(rid=rid) & Q(uuid=uuid)).only("id", "expires_at").first()
    if token:
        renew_before = now + datetime.timedelta(seconds=settings.HEARTBEAT_TOKEN_REFRESH_SECONDS)
        # 旧数据没有 expires_at：心跳时补写，避免老 token 永久有效。
        if token.expires_at is None or token.expires_at < renew_before:
            RustDeskToken.objects.filter(pk=token.pk).update(
                expires_at=now + datetime.timedelta(seconds=EFFECTIVE_SECONDS)
            )

    return JsonResponse({"data": _("在线")})


def audit(request, kind=None):
    """POST /api/audit[/conn|/file|/alarm]"""
    try:
        postdata = json.loads(request.body.decode() or "{}")
    except ValueError:
        return JsonResponse({"error": _("数据格式错误")})

    audit_type = postdata.get("action", "")
    if audit_type == "new":
        ConnLog.objects.create(
            action=postdata.get("action", ""),
            conn_id=str(postdata.get("conn_id", "") or "")[:10] or None,
            from_ip=postdata.get("ip", ""),
            from_id="",
            rid=postdata.get("id", ""),
            conn_start=datetime.datetime.now(),
            session_id=str(postdata.get("session_id", "") or "")[:60] or None,
            uuid=postdata.get("uuid", ""),
        )
    elif audit_type == "close":
        ConnLog.objects.filter(conn_id=str(postdata.get("conn_id", ""))).update(conn_end=datetime.datetime.now())
    elif "typ" in postdata:
        # 告警审计（alarm）：没有独立表时记录在 ConnLog 里
        ConnLog.objects.create(
            action="alarm",
            conn_id=str(postdata.get("conn_id", "") or "")[:10] or None,
            rid=postdata.get("id", ""),
            uuid=postdata.get("uuid", ""),
            session_id=str(postdata.get("typ", ""))[:60],
            conn_start=datetime.datetime.now(),
            note=str(postdata.get("info", ""))[:500],
        )
    elif "is_file" in postdata:
        info = postdata.get("info") or "{}"
        if isinstance(info, str):
            try:
                info = json.loads(info)
            except ValueError:
                info = {}
        files = info.get("files") or []
        names = []
        total = 0
        for item in files[:10]:
            name, size = "", 0
            if isinstance(item, (list, tuple)) and item:
                name = str(item[0] or "")
                if len(item) > 1:
                    try:
                        size = int(item[1] or 0)
                    except (TypeError, ValueError):
                        size = 0
            total += size
            if name:
                names.append(name)
        path = str(postdata.get("path") or "").strip()
        is_file = bool(postdata.get("is_file"))
        if is_file and path:
            display = path
        elif names:
            base = path.rstrip("/\\")
            if len(names) == 1:
                display = base + ("/" if base else "") + names[0]
            else:
                display = (base + "/" if base else "") + "%d 个文件" % len(names)
        else:
            display = path
        FileLog.objects.create(
            file=display[:500],
            user_id=postdata.get("peer_id", ""),
            user_ip=info.get("ip", ""),
            remote_id=postdata.get("id", ""),
            filesize=convert_filesize(total),
            direction=int(postdata.get("type", 0) or 0),
            logged_at=datetime.datetime.now(),
        )
    else:
        try:
            peer = postdata.get("peer") or []
            conn_id = str(postdata.get("conn_id", ""))
            if peer:
                ConnLog.objects.filter(Q(conn_id=conn_id)).update(from_id=peer[0])
            ConnLog.objects.filter(Q(conn_id=conn_id)).update(session_id=str(postdata.get("session_id", ""))[:60])
        except Exception:
            logger.exception("审计连接信息更新失败: conn_id=%s", postdata.get("conn_id"))

    # 客户端要求 2xx + 空正文，返回 JSON 会被判为失败并重试
    return HttpResponse(status=200)


def audit_note(request):
    """PUT /api/audit，body {guid, note}；需要 Bearer token。"""
    if request.method != "PUT":
        return JsonResponse({"error": _("请求方式错误！")}, status=405)
    access_token = request.META.get("HTTP_AUTHORIZATION", "")
    if access_token.startswith("Bearer "):
        access_token = access_token[len("Bearer ") :]
    token = RustDeskToken.objects.filter(access_token=access_token).first()
    if not views_pro.token_user(token):
        return JsonResponse({"error": _("未登录或登录已过期")}, status=401)
    try:
        postdata = json.loads(request.body.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": _("请求体不是合法的 JSON")}, status=400)
    guid = str(postdata.get("guid", "") or "")
    note = postdata.get("note", "")
    if not guid:
        return JsonResponse({"code": 1, "data": "ok"})
    if not guid.isdigit():
        return JsonResponse({"error": _("无效的审计记录")}, status=400)
    ConnLog.objects.filter(id=int(guid)).update(note=note)
    return JsonResponse({"code": 1, "data": "ok"})


def convert_filesize(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])
