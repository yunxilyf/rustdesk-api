# -*- coding: utf-8 -*-
"""冒烟测试公共工具：JSON 调用、登录、造数。"""

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache

from api.models_pro import AddressBook, AddressBookPeer, DeviceGroup, DeviceGroupPeer
from api.models_work import RustDeskPeer, RustDesDevice

User = get_user_model()

CLIENT_USER = "smoke-client"
CLIENT_PWD = "Smoke@2026"
CLIENT_RID = "900000001"
CLIENT_UUID = "c21va2UtdXVpZA=="


def json_call(client, method, path, payload=None, token=None, raw=None, **extra):
    """发 JSON 请求，返回 (status, text)。raw 用于发送原始字节（录像分片）。"""
    if raw is not None:
        body = raw
        ctype = "application/octet-stream"
    elif payload is not None:
        body = json.dumps(payload)
        ctype = "application/json"
    else:
        body = ""
        ctype = "application/json"
    kwargs = {"content_type": ctype, **extra}
    if token:
        kwargs["HTTP_AUTHORIZATION"] = "Bearer " + token
    fn = getattr(client, method.lower())
    resp = fn(path, data=body, **kwargs)
    return resp.status_code, resp.content.decode("utf-8", "replace")


def jload(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def client_login(client, username=CLIENT_USER, password=CLIENT_PWD, rid=CLIENT_RID, uuid=CLIENT_UUID):
    """RustDesk 客户端登录，返回 access_token。"""
    status, body = json_call(
        client,
        "POST",
        "/api/login",
        {
            "username": username,
            "password": password,
            "id": rid,
            "uuid": uuid,
            "autoLogin": True,
            "type": "account",
            "deviceInfo": {"os": "windows"},
        },
    )
    data = jload(body) or {}
    return status, data.get("access_token"), data, body


def make_user(username, password, is_admin=False, **fields):
    user = User(username=username, is_admin=is_admin, is_superuser=is_admin, is_active=True, **fields)
    user.set_password(password)
    user.save()
    return user


def bind_device(user, rid, hostname="PC-1"):
    """设备归属：RustDeskPeer(uid=user.id) + 个人地址簿联系人。"""
    RustDeskPeer.objects.update_or_create(
        uid=str(user.id),
        rid=rid,
        defaults={"username": user.username, "hostname": hostname, "rhash": "h" + rid},
    )
    ab, _ = AddressBook.objects.get_or_create(
        owner=user,
        is_personal=True,
        defaults={"guid": "ab" + str(user.id), "name": user.username + " 的地址簿"},
    )
    AddressBookPeer.objects.update_or_create(
        ab=ab,
        rid=rid,
        defaults={"hostname": hostname, "username": user.username, "rhash": "h" + rid},
    )
    return ab


def make_device(rid, hostname="PC-1", **fields):
    return RustDesDevice.objects.create(rid=rid, hostname=hostname, **fields)


def make_group(owner, name, rids=()):
    group = DeviceGroup.objects.create(guid="g" + name, owner=owner, name=name)
    for rid in rids:
        DeviceGroupPeer.objects.create(group=group, rid=rid)
    return group


def reset_throttle():
    cache.clear()


class TokenedClientMixin:
    """为测试类准备一个已登录的客户端 token。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user(CLIENT_USER, CLIENT_PWD)

    def setUp(self):
        reset_throttle()
        self.token = client_login(self.client)[1]
        self.assertIsNotNone(self.token, "client login failed")
