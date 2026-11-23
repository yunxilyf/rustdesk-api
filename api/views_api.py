"""RustDesk 客户端核心接口：登录、旧版地址簿、sysinfo、心跳与审计。

登录状态使用 ``RustDeskToken.access_token``（Bearer），不使用 Cookie / Session。
"""

import datetime
import json
import math
import uuid as uuidlib

from django.conf import settings
from django.contrib import auth
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _

from api.client_auth import authenticate_client
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
from api.tag_colors import normalize_color

from . import client_auth, throttle, views_pro


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
    auto_login = data.get("autoLogin", True)
    login_type = data.get("type", "")
    device_info = data.get("deviceInfo", "")
    if not all(isinstance(value, str) for value in (username, password, rid, uuid, login_type)):
        return JsonResponse({"error": _("登录字段格式错误")}, status=400)
    if not isinstance(auto_login, bool) or len(rid) > 16 or len(uuid) > 60 or len(login_type) > 20:
        return JsonResponse({"error": _("登录字段过长")}, status=400)
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
    user.autoLogin = auto_login
    user.rtype = login_type
    user.deviceInfo = json.dumps(device_info)
    user.save(update_fields=["rid", "uuid", "autoLogin", "rtype", "deviceInfo"])

    token = client_auth.issue_token(user, rid, uuid)

    result["access_token"] = token.access_token
    result["type"] = "access_token"
    result["user"] = views_pro._user_json(user)
    return JsonResponse(result)


def logout(request):
    if request.method != "POST":
        return JsonResponse({"error": _("请求方式错误！")})

    token, _user = authenticate_client(request, renew=False)
    if token is None:
        return views_pro._unauthorized()
    RustDeskToken.objects.filter(pk=token.pk, access_token=token.access_token).delete()
    return JsonResponse({"code": 1})


def currentUser(request):
    result = {}
    if request.method == "GET":
        result["error"] = _("错误的提交方式！")
        return JsonResponse(result)

    token, user = authenticate_client(request)

    if not user:
        result["error"] = _("未登录或登录已过期")
        return JsonResponse(result, status=401)

    result["access_token"] = token.access_token
    result["type"] = "access_token"
    result.update(views_pro._user_json(user))
    return JsonResponse(result)


def ab(request):
    """旧版地址簿接口：GET 拉取 / POST 覆盖提交。"""
    _token, user = authenticate_client(request)
    if not user:
        return JsonResponse({"error": _("未登录或登录已过期")}, status=401)

    ab_obj = views_pro._legacy_to_ab(user)

    if request.method == "GET":
        tags = list(ab_obj.tags.all().order_by("id"))
        tag_names = [t.name for t in tags]
        tag_colors = {t.name: normalize_color(t.color, t.name) for t in tags}

        dev_info = views_pro._device_info_map(user)
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
        seen_tags = set()
        for name in tagnames:
            name = str(name).strip()[:64]
            if not name or name in seen_tags:
                continue
            seen_tags.add(name)
            AddressBookTag.objects.create(ab=ab_obj, name=name, color=normalize_color(tag_colors.get(name, 0), name))

    if "peers" in data:
        peers = data.get("peers") or []
        ab_obj.peers.all().delete()
        seen_peers = set()
        for one in peers:
            rid = str(one.get("id", "")).strip()
            if not rid or rid in seen_peers:
                continue
            seen_peers.add(rid)
            AddressBookPeer.objects.create(
                ab=ab_obj,
                rid=rid,
                rhash=one.get("hash", ""),
                # 旧版 /api/ab 永远是个人地址簿，不接收共享密码字段。
                password="",
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
    if request.method != "POST":
        return HttpResponse(status=405)

    try:
        postdata = json.loads(request.body.decode() or "{}")
    except ValueError:
        return HttpResponse("ID_NOT_FOUND", content_type="text/plain")

    if not isinstance(postdata, dict):
        return HttpResponse("ID_NOT_FOUND", content_type="text/plain")
    rid = str(postdata.get("id") or "").strip()
    uuid = str(postdata.get("uuid") or "").strip()
    if not rid or not uuid or len(rid) > 60 or len(uuid) > 100:
        return HttpResponse("ID_NOT_FOUND", content_type="text/plain")

    device = RustDesDevice.objects.filter(rid=rid).order_by("-update_time", "-id").first()
    has_identity = device is not None and bool(device.uuid)
    assigned = views_pro.device_is_assigned(rid)
    uuid_changed = bool(has_identity and device.uuid != uuid)
    reregister_open = bool(
        uuid_changed and device.reregister_until is not None and device.reregister_until >= timezone.now()
    )
    if uuid_changed:
        token, user = authenticate_client(request)
        authorized = user is not None and views_pro.can_manage_device(user, rid, token)
        if not authorized:
            if reregister_open:
                # 窗口内只记录待确认的新身份，由管理员在后台确认后才生效。
                RustDesDevice.objects.filter(
                    pk=device.pk, uuid=device.uuid, reregister_until__gte=timezone.now()
                ).update(pending_uuid=uuid, pending_at=timezone.now())
            return HttpResponse("ID_NOT_FOUND", content_type="text/plain")
    elif not has_identity and assigned:
        token, user = authenticate_client(request)
        if user is None or not views_pro.can_manage_device(user, rid, token):
            return HttpResponse("ID_NOT_FOUND", content_type="text/plain")
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
        if uuid_changed:
            fields.update(pending_uuid="", pending_at=None, reregister_until=None)
        updated = RustDesDevice.objects.filter(pk=device.pk, uuid=device.uuid).update(**fields)
        if not updated:
            return HttpResponse("ID_NOT_FOUND", content_type="text/plain")

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
        dev = RustDesDevice.objects.filter(rid=rid).order_by("-update_time", "-id").first()
        if dev is not None:
            RustDesDevice.objects.filter(pk=dev.pk).update(**device_fields)

    user = UserProfile.objects.filter(Q(rid=rid) & Q(uuid=uuid)).first()
    if user is None:
        return

    ab_name = str(postdata.get("preset-address-book-name", "")).strip()
    if ab_name:
        ab_obj = AddressBook.objects.filter(owner=user, name=ab_name, is_personal=False).order_by("id").first()
        if ab_obj is None:
            # preset 指定的是“把设备放进某个地址簿”，属于共享/团队簿；
            # 个人簿只有一个（客户端固定显示「我的地址簿」），不能在这里创建。
            ab_obj = AddressBook.objects.create(
                guid=uuidlib.uuid4().hex, owner=user, name=ab_name, is_personal=False, rule=2
            )
        peer, _created = AddressBookPeer.objects.get_or_create(ab=ab_obj, rid=rid)
        tag = str(postdata.get("preset-address-book-tag", "")).strip()
        if tag:
            tag = tag[:60]
            AddressBookTag.objects.get_or_create(ab=ab_obj, name=tag)
            existing = [t for t in (peer.tags or "").split(",") if t]
            if tag not in existing:
                peer.tags = ",".join(existing + [tag])
        alias = str(postdata.get("preset-address-book-alias", "")).strip()
        if alias:
            peer.alias = alias
        password = str(postdata.get("preset-address-book-password", "")).strip()
        if password:
            if ab_obj.is_personal:
                peer.rhash = password
            else:
                peer.password = password[:128]
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
    - 携带有效令牌的请求可在临近过期时续期。
    写操作从「每次心跳 2 条 UPDATE」降到「每台设备几分钟 1 条」，
    否则数据库写锁会先于 Python 成为瓶颈。
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        postdata = json.loads(request.body.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": _("请求体不是合法的 JSON")}, status=400)
    if not isinstance(postdata, dict):
        return JsonResponse({"error": _("请求体格式错误")}, status=400)
    rid = str(postdata.get("id") or "")
    uuid = str(postdata.get("uuid") or "")
    if rid and uuid:
        now = timezone.now()
        stale_before = now - datetime.timedelta(seconds=settings.HEARTBEAT_DEVICE_TOUCH_SECONDS)
        device = (
            RustDesDevice.objects.filter(rid=rid)
            .only("id", "uuid", "update_time")
            .order_by("-update_time", "-id")
            .first()
        )
        if device and device.uuid == uuid and device.update_time <= stale_before:
            RustDesDevice.objects.filter(pk=device.pk, uuid=uuid, update_time__lte=stale_before).update(update_time=now)
        if device is None or device.uuid != uuid:
            return JsonResponse({"sysinfo": True})
        # 设备心跳不带 Authorization，但设备身份已由 rid+uuid 确认：
        # 临近过期时顺手续期，避免客户端长期在线却因没调用其它接口而过期。
        renew_before = now + datetime.timedelta(seconds=settings.HEARTBEAT_TOKEN_REFRESH_SECONDS)
        RustDeskToken.objects.filter(rid=rid, uuid=uuid, expires_at__gt=now, expires_at__lt=renew_before).update(
            expires_at=now + datetime.timedelta(seconds=settings.TOKEN_TTL_SECONDS)
        )

    authenticate_client(request)
    return JsonResponse({"data": _("在线")})


def audit(request, kind=None):
    """POST /api/audit[/conn|/file|/alarm]"""
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        postdata = json.loads(request.body.decode() or "{}")
    except ValueError:
        return JsonResponse({"error": _("数据格式错误")}, status=400)
    if not isinstance(postdata, dict):
        return JsonResponse({"error": _("数据格式错误")}, status=400)
    rid = str(postdata.get("id") or "").strip()
    uuid = str(postdata.get("uuid") or "").strip()
    if not rid or not uuid or len(rid) > 20 or len(uuid) > 60:
        return JsonResponse({"error": _("缺少有效的设备标识")}, status=400)
    registered = (
        RustDesDevice.objects.filter(rid=rid).order_by("-update_time", "-id").values_list("uuid", flat=True).first()
    )
    if registered != uuid:
        return HttpResponse(status=403)

    conn_id = str(postdata.get("conn_id") or "")[:10]
    connection = ConnLog.objects.filter(rid=rid, uuid=uuid, conn_id=conn_id, action="new")
    audit_type = postdata.get("action", "")
    if audit_type == "new":
        ConnLog.objects.create(
            action="new",
            conn_id=conn_id or None,
            from_ip=str(postdata.get("ip") or "")[:30],
            from_id="",
            rid=rid,
            conn_start=timezone.now(),
            session_id=str(postdata.get("session_id", "") or "")[:60] or None,
            uuid=uuid,
        )
    elif audit_type == "close":
        if conn_id:
            connection.filter(conn_end__isnull=True).update(conn_end=timezone.now())
    elif "typ" in postdata:
        # 告警审计（alarm）：没有独立表时记录在 ConnLog 里
        ConnLog.objects.create(
            action="alarm",
            conn_id=conn_id or None,
            rid=rid,
            uuid=uuid,
            session_id=str(postdata.get("typ", ""))[:60],
            conn_start=timezone.now(),
            note=str(postdata.get("info", ""))[:500],
        )
    elif "is_file" in postdata:
        info = postdata.get("info") or "{}"
        if isinstance(info, str):
            try:
                info = json.loads(info)
            except ValueError:
                info = {}
        if not isinstance(info, dict):
            return JsonResponse({"error": _("文件审计信息格式错误")}, status=400)
        files = info.get("files") or []
        if not isinstance(files, list):
            return JsonResponse({"error": _("文件列表格式错误")}, status=400)
        names = []
        total = 0
        for item in files[:10]:
            name, size = "", 0
            if isinstance(item, (list, tuple)) and item:
                name = str(item[0] or "")
                if len(item) > 1:
                    try:
                        size = min(max(int(item[1] or 0), 0), 2**63 - 1)
                    except (TypeError, ValueError, OverflowError):
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
        try:
            direction = int(postdata.get("type") or 0)
        except (TypeError, ValueError, OverflowError):
            return JsonResponse({"error": _("文件传输方向格式错误")}, status=400)
        if not 0 <= direction <= 2**31 - 1:
            return JsonResponse({"error": _("文件传输方向超出范围")}, status=400)
        FileLog.objects.create(
            file=display[:500],
            user_id=str(postdata.get("peer_id") or "")[:20],
            user_ip=str(info.get("ip") or "")[:20],
            remote_id=rid,
            filesize=convert_filesize(total),
            direction=direction,
            logged_at=timezone.now(),
        )
    elif conn_id:
        updates = {"session_id": str(postdata.get("session_id") or "")[:60]}
        peer = postdata.get("peer")
        if isinstance(peer, (list, tuple)) and peer:
            updates["from_id"] = str(peer[0] or "")[:20]
        connection.filter(conn_end__isnull=True).update(**updates)

    # 客户端要求 2xx + 空正文，返回 JSON 会被判为失败并重试
    return HttpResponse(status=200)


def audit_note(request):
    """PUT /api/audit，body {guid, note}；需要 Bearer token。"""
    if request.method != "PUT":
        return JsonResponse({"error": _("请求方式错误！")}, status=405)
    token, user = authenticate_client(request)
    if user is None:
        return views_pro._unauthorized()
    try:
        postdata = json.loads(request.body.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": _("请求体不是合法的 JSON")}, status=400)
    if not isinstance(postdata, dict):
        return JsonResponse({"error": _("请求体格式错误")}, status=400)
    guid = str(postdata.get("guid") or "")
    note = postdata.get("note", "")
    if not guid.isascii() or not guid.isdecimal() or len(guid) > 10:
        return JsonResponse({"error": _("无效的审计记录")}, status=400)
    if not isinstance(note, str) or len(note) > 500:
        return JsonResponse({"error": _("备注最多 500 字符")}, status=400)
    updated = views_pro.visible_connection_logs(user, token).filter(pk=int(guid)).update(note=note)
    if not updated:
        return JsonResponse({"error": _("审计记录不存在")}, status=404)
    return JsonResponse({"code": 1, "data": "ok"})


def convert_filesize(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])
