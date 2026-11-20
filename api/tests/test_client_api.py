# -*- coding: utf-8 -*-
"""RustDesk 客户端 API 契约冒烟测试（对应 1.5.x 客户端真实调用）。"""

import datetime
import json
import tempfile

from django.test import TestCase, override_settings
from django.utils import timezone

from api.models_pro import AddressBook
from api.models_user import UserProfile
from api.models_work import FileLog, RustDesDevice, RustDeskToken

from api.tests.utils import (
    CLIENT_RID,
    CLIENT_USER,
    CLIENT_UUID,
    TokenedClientMixin,
    bind_device,
    client_login,
    jload,
    json_call,
    make_device,
)


class ClientLoginTests(TokenedClientMixin, TestCase):
    def test_login_options_is_json_array(self):
        status, body = json_call(self.client, "GET", "/api/login-options")
        self.assertEqual(status, 200)
        self.assertIsInstance(jload(body), list)

    def test_login_returns_token_and_user_payload(self):
        status, token, data, body = client_login(self.client)
        self.assertEqual(status, 200, body)
        self.assertTrue(token)
        self.assertEqual(data.get("type"), "access_token")
        user = data.get("user") or {}
        self.assertEqual(user.get("name"), CLIENT_USER)
        # 客户端 UserPayload 字段（缺省可以，但不能缺 name）
        for key in ("display_name", "is_admin"):
            self.assertIn(key, user)

    def test_login_rejects_bad_password(self):
        status, token, data, body = client_login(self.client, password="wrong-pass")
        self.assertEqual(status, 200)
        self.assertIsNone(token)
        self.assertIn("error", data)

    def test_login_rejects_malformed_json(self):
        resp = self.client.post("/api/login", data="{not json", content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertIsNotNone(resp.json().get("error"))

    def test_current_user_and_invalid_token(self):
        status, body = json_call(
            self.client, "POST", "/api/currentUser", {"id": CLIENT_RID, "uuid": CLIENT_UUID}, token=self.token
        )
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        self.assertEqual(data.get("name"), CLIENT_USER)
        self.assertIn("status", data)

        status, body = json_call(
            self.client, "POST", "/api/currentUser", {"id": CLIENT_RID, "uuid": CLIENT_UUID}, token="bad-token"
        )
        self.assertEqual(status, 401)

    def test_logout_invalidates_token(self):
        status, body = json_call(self.client, "POST", "/api/logout", {"id": CLIENT_RID, "uuid": CLIENT_UUID})
        self.assertEqual(status, 200, body)
        self.assertEqual((jload(body) or {}).get("code"), 1)
        status, body = json_call(
            self.client, "POST", "/api/currentUser", {"id": CLIENT_RID, "uuid": CLIENT_UUID}, token=self.token
        )
        self.assertEqual(status, 401)


class LegacyAddressBookTests(TokenedClientMixin, TestCase):
    def test_legacy_ab_roundtrip(self):
        status, body = json_call(self.client, "GET", "/api/ab", token=self.token)
        self.assertEqual(status, 200, body)
        wrapper = jload(body) or {}
        data = jload(wrapper.get("data") or "null")
        self.assertIsInstance(data, dict)
        self.assertIn("peers", data)

        payload = {
            "tags": ["office", "home"],
            "peers": [
                {
                    "id": "111",
                    "hash": "h1",
                    "username": "u1",
                    "hostname": "pc1",
                    "platform": "Windows",
                    "alias": "a1",
                    "tags": ["office"],
                }
            ],
            "tag_colors": json.dumps({"office": 1, "home": 2}),
        }
        status, body = json_call(self.client, "POST", "/api/ab", {"data": json.dumps(payload)}, token=self.token)
        self.assertEqual(status, 200, body)
        self.assertEqual((jload(body) or {}).get("code"), 1)

        status, body = json_call(self.client, "GET", "/api/ab", token=self.token)
        data = jload((jload(body) or {}).get("data") or "null") or {}
        self.assertIn("office", data.get("tags", []))
        peers = data.get("peers", [])
        self.assertEqual(len(peers), 1)
        self.assertEqual(peers[0]["id"], "111")

    def test_legacy_ab_requires_token(self):
        status, _body = json_call(self.client, "GET", "/api/ab")
        self.assertIn(status, (401, 403))


class NewAddressBookTests(TokenedClientMixin, TestCase):
    def setUp(self):
        super().setUp()
        status, body = json_call(self.client, "POST", "/api/ab/personal", {}, token=self.token)
        self.assertEqual(status, 200, body)
        self.ab_guid = (jload(body) or {}).get("guid")
        self.assertTrue(self.ab_guid)

    def test_settings_and_shared_profiles(self):
        status, body = json_call(self.client, "POST", "/api/ab/settings", {}, token=self.token)
        self.assertEqual(status, 200, body)
        self.assertIn("max_peer_one_ab", jload(body) or {})

        status, body = json_call(
            self.client, "POST", "/api/ab/shared/profiles?current=1&pageSize=100", {}, token=self.token
        )
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        self.assertIn("total", data)
        self.assertIsInstance(data.get("data"), list)

    def test_own_book_appears_in_shared_profiles(self):
        # 控制台里自己建的地址簿（rule=0），客户端也必须能拿到
        own = AddressBook.objects.create(guid="ownbook001", owner=self.user, name="组1", is_personal=False, rule=0)
        other = UserProfile.objects.create_user(username="other1", password="Other@2026")
        hidden = AddressBook.objects.create(
            guid="hidden001", owner=other, name="别人的私有簿", is_personal=False, rule=0
        )
        shared = AddressBook.objects.create(guid="shared001", owner=other, name="只读共享簿", is_personal=False, rule=1)

        status, body = json_call(
            self.client, "POST", "/api/ab/shared/profiles?current=1&pageSize=100", {}, token=self.token
        )
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        by_guid = {p["guid"]: p for p in data.get("data") or []}
        self.assertIn(own.guid, by_guid)
        self.assertEqual(by_guid[own.guid]["rule"], 2)  # 本人视为可读写
        self.assertEqual(by_guid[own.guid]["name"], "组1")
        self.assertNotIn(hidden.guid, by_guid)  # 别人的私有簿不可见
        self.assertIn(shared.guid, by_guid)
        self.assertEqual(by_guid[shared.guid]["rule"], 1)  # 只读保持只读

    def test_peers_list_shape(self):
        status, body = json_call(
            self.client, "POST", "/api/ab/peers?current=1&pageSize=100&ab=" + self.ab_guid, {}, token=self.token
        )
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        self.assertIn("total", data)
        self.assertIsInstance(data.get("data"), list)

    def test_peer_crud_returns_empty_body(self):
        status, body = json_call(
            self.client,
            "POST",
            "/api/ab/peer/add/" + self.ab_guid,
            {
                "id": "222",
                "hash": "h2",
                "username": "u2",
                "hostname": "pc2",
                "platform": "Linux",
                "alias": "alias2",
                "tags": ["t1"],
                "note": "n2",
            },
            token=self.token,
        )
        self.assertEqual((status, body), (200, ""), body)

        status, body = json_call(
            self.client,
            "PUT",
            "/api/ab/peer/update/" + self.ab_guid,
            {"id": "222", "alias": "alias2-new", "tags": ["t1", "t2"]},
            token=self.token,
        )
        self.assertEqual((status, body), (200, ""), body)

        status, body = json_call(
            self.client, "POST", "/api/ab/peers?current=1&pageSize=100&ab=" + self.ab_guid, {}, token=self.token
        )
        peers = (jload(body) or {}).get("data") or []
        self.assertEqual(peers[0]["alias"], "alias2-new")

        status, body = json_call(self.client, "DELETE", "/api/ab/peer/" + self.ab_guid, ["222"], token=self.token)
        self.assertEqual((status, body), (200, ""), body)

    def test_tag_crud_returns_empty_body(self):
        status, body = json_call(
            self.client, "POST", "/api/ab/tag/add/" + self.ab_guid, {"name": "tagA", "color": 3}, token=self.token
        )
        self.assertEqual((status, body), (200, ""), body)
        json_call(
            self.client, "POST", "/api/ab/tag/add/" + self.ab_guid, {"name": "tagB", "color": 4}, token=self.token
        )

        status, body = json_call(self.client, "POST", "/api/ab/tags/" + self.ab_guid, {}, token=self.token)
        tags = jload(body) or []
        self.assertEqual(status, 200, body)
        self.assertEqual(sorted(t["name"] for t in tags), ["tagA", "tagB"])
        self.assertTrue(all(isinstance(t["color"], int) for t in tags))

        status, body = json_call(
            self.client, "PUT", "/api/ab/tag/rename/" + self.ab_guid, {"old": "tagB", "new": "tagB2"}, token=self.token
        )
        self.assertEqual((status, body), (200, ""), body)
        status, body = json_call(
            self.client, "PUT", "/api/ab/tag/update/" + self.ab_guid, {"name": "tagA", "color": 9}, token=self.token
        )
        self.assertEqual((status, body), (200, ""), body)
        status, body = json_call(self.client, "DELETE", "/api/ab/tag/" + self.ab_guid, ["tagB2"], token=self.token)
        self.assertEqual((status, body), (200, ""), body)


class DeviceListTests(TokenedClientMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        make_device(CLIENT_RID, hostname="CLI-PC", username="tester", os="Windows 11", version="1.5.3")

    def test_users_list(self):
        status, body = json_call(
            self.client, "GET", "/api/users?current=1&pageSize=100&accessible=&status=1", token=self.token
        )
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        self.assertIn("total", data)
        self.assertIsInstance(data.get("data"), list)
        self.assertTrue({"name", "display_name", "is_admin"} <= set(data["data"][0]))

    def test_peers_list(self):
        bind_device(self.user, "PEER-1", hostname="PEER-PC")
        status, body = json_call(self.client, "GET", "/api/peers?current=1&pageSize=100", token=self.token)
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        self.assertIn("total", data)
        self.assertTrue(data.get("data"))
        info = data["data"][0].get("info") or {}
        self.assertIn("username", info)
        self.assertIn("device_name", info)
        self.assertIn("os", info)
        owned = [p for p in data["data"] if p.get("id") == "PEER-1"]
        self.assertTrue(owned, "bound peer missing from /api/peers")
        # 客户端设备分组页按 loginName 归属设备（peers_view.dart:591）
        self.assertEqual(owned[0].get("loginName"), self.user.username)

    def test_peers_keep_real_names_for_card_title(self):
        """设备分组页走 PeerPayload.toPeer()，不映射 alias；标题仍是 username@hostname。"""
        from api.models_pro import AddressBookPeer

        bind_device(self.user, "PEER-ALIAS", hostname="ALIAS-PC")
        AddressBookPeer.objects.filter(rid="PEER-ALIAS").update(alias="机房机器")
        status, body = json_call(self.client, "GET", "/api/peers?current=1&pageSize=100", token=self.token)
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        item = next(p for p in data["data"] if p.get("id") == "PEER-ALIAS")
        self.assertEqual(item["info"]["username"], self.user.username)
        self.assertEqual(item["info"]["device_name"], "ALIAS-PC")
        self.assertEqual(item["alias"], "机房机器")

    def test_peers_hide_unowned_devices_for_normal_user(self):
        make_device("ORPHAN-1", hostname="ORPHAN-PC")
        status, body = json_call(self.client, "GET", "/api/peers?current=1&pageSize=100", token=self.token)
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        rids = {p.get("id") for p in data.get("data", [])}
        self.assertNotIn("ORPHAN-1", rids)

    def test_peers_dedupe_across_address_books(self):
        from api.models_pro import AddressBookPeer

        ab = AddressBook.objects.create(guid="dup-ab-1", owner=self.user, name="组1", rule=0)
        AddressBookPeer.objects.create(ab=ab, rid="DUP-1", username="u", hostname="h", rhash="x")
        bind_device(self.user, "DUP-1", hostname="DUP-PC")
        status, body = json_call(self.client, "GET", "/api/peers?current=1&pageSize=100", token=self.token)
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        ids = [p.get("id") for p in data.get("data", [])]
        self.assertEqual(ids.count("DUP-1"), 1, ids)

    def test_accessible_device_groups(self):
        status, body = json_call(
            self.client, "GET", "/api/device-group/accessible?current=1&pageSize=100", token=self.token
        )
        self.assertEqual(status, 200, body)
        self.assertIn("total", jload(body) or {})


class PlatformFillTests(TokenedClientMixin, TestCase):
    """地址簿里的设备如果没有 platform，用 sysinfo 的 os 兜底（否则客户端不画系统图标）。"""

    def test_new_ab_peer_platform_from_sysinfo(self):
        bind_device(self.user, "OS-1", hostname="")
        make_device("OS-1", hostname="linux-pc", os="Ubuntu 24.04", username="u1")
        ab = AddressBook.objects.get(owner=self.user, is_personal=True)
        status, body = json_call(
            self.client, "POST", "/api/ab/peers?current=1&pageSize=50&ab=" + ab.guid, token=self.token
        )
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        row = [p for p in data.get("data", []) if p["id"] == "OS-1"][0]
        self.assertEqual(row["platform"], "Linux")
        self.assertEqual(row["hostname"], "linux-pc")

    def test_group_peer_platform_and_legacy_ab(self):
        bind_device(self.user, "OS-2", hostname="")
        make_device("OS-2", hostname="mac-pc", os="macOS 15.1", username="u2")
        status, body = json_call(self.client, "GET", "/api/peers?current=1&pageSize=100", token=self.token)
        data = jload(body) or {}
        row = [p for p in data.get("data", []) if p.get("id") == "OS-2"][0]
        self.assertEqual(row["platform"], "Mac OS")

        status, body = json_call(self.client, "GET", "/api/ab", token=self.token)
        payload = json.loads((jload(body) or {}).get("data") or "{}")
        legacy = [p for p in payload.get("peers", []) if p["id"] == "OS-2"][0]
        self.assertEqual(legacy["platform"], "Mac OS")
        self.assertEqual(legacy["hostname"], "mac-pc")


class SysinfoTests(TokenedClientMixin, TestCase):
    def payload(self, **extra):
        data = {
            "id": CLIENT_RID,
            "uuid": CLIENT_UUID,
            "version": "1.5.3",
            "cpu": "AMD Ryzen 7, 3.2GHz, 16/8 cores",
            "memory": "32GB",
            "os": "Windows 11",
            "hostname": "test-pc",
            "username": "tester",
        }
        data.update(extra)
        return data

    def test_sysinfo_new_and_existing_device(self):
        status, body = json_call(self.client, "POST", "/api/sysinfo", self.payload())
        self.assertEqual((status, body.strip()), (200, "SYSINFO_UPDATED"), body)

        status, body = json_call(self.client, "POST", "/api/sysinfo", self.payload())
        self.assertEqual((status, body.strip()), (200, "SYSINFO_UPDATED"), body)

    def test_sysinfo_accepts_client_preset_keys(self):
        payload = self.payload(
            **{
                "preset-address-book-name": "presetAB",
                "preset-address-book-tag": "pt",
                "preset-device-name": "preset-pc",
                "preset-device-username": "preset-user",
                "preset-note": "n",
            }
        )
        status, body = json_call(self.client, "POST", "/api/sysinfo", payload)
        self.assertEqual((status, body.strip()), (200, "SYSINFO_UPDATED"), body)

        # 第二次（设备已存在）不能再 500
        status, body = json_call(self.client, "POST", "/api/sysinfo", payload)
        self.assertEqual((status, body.strip()), (200, "SYSINFO_UPDATED"), body)

    def test_sysinfo_uuid_change_keeps_single_device_row(self):
        status, body = json_call(self.client, "POST", "/api/sysinfo", self.payload())
        self.assertEqual((status, body.strip()), (200, "SYSINFO_UPDATED"), body)

        changed = self.payload(uuid="bmV3LXV1aWQ=")  # 客户端重装后 uuid 变化
        status, body = json_call(self.client, "POST", "/api/sysinfo", changed)
        self.assertEqual((status, body.strip()), (200, "SYSINFO_UPDATED"), body)

        rows = RustDesDevice.objects.filter(rid=CLIENT_RID)
        self.assertEqual(rows.count(), 1, list(rows.values("uuid")))
        self.assertEqual(rows.first().uuid, "bmV3LXV1aWQ=")

    def test_sysinfo_missing_id(self):
        status, body = json_call(self.client, "POST", "/api/sysinfo", {"id": "", "uuid": ""})
        self.assertEqual((status, body.strip()), (200, "ID_NOT_FOUND"), body)

    def test_sysinfo_ver_and_heartbeat(self):
        status, body = json_call(self.client, "POST", "/api/sysinfo_ver", {})
        self.assertEqual(status, 200)
        self.assertTrue(body.strip())

        status, body = json_call(
            self.client,
            "POST",
            "/api/heartbeat",
            {
                "id": CLIENT_RID,
                "uuid": CLIENT_UUID,
                "ver": 1503,
                "conns": [1],
                "modified_at": 1,
            },
        )
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        self.assertIsInstance(data, dict)
        # 出现 sysinfo 键会让客户端重新上传系统信息
        self.assertNotIn("sysinfo", data)


class AuditTests(TokenedClientMixin, TestCase):
    def test_conn_audit_lifecycle(self):
        status, body = json_call(
            self.client,
            "POST",
            "/api/audit/conn",
            {
                "ip": "1.2.3.4",
                "action": "new",
                "id": CLIENT_RID,
                "uuid": CLIENT_UUID,
                "conn_id": "c100",
                "session_id": "s100",
                "nonce": "n",
            },
        )
        self.assertEqual((status, body), (200, ""), body)

        status, body = json_call(
            self.client,
            "POST",
            "/api/audit/conn",
            {
                "id": CLIENT_RID,
                "uuid": CLIENT_UUID,
                "conn_id": "c100",
                "peer": ["999"],
                "session_id": "s100",
            },
        )
        self.assertEqual((status, body), (200, ""), body)

        status, body = json_call(
            self.client, "POST", "/api/audit/conn", {"id": CLIENT_RID, "action": "close", "conn_id": "c100"}
        )
        self.assertEqual((status, body), (200, ""), body)

    def test_active_conn_guid_and_note(self):
        status, body = json_call(
            self.client, "GET", "/api/audit/conn/active?id=%s&session_id=s100&conn_type=0" % CLIENT_RID
        )
        self.assertEqual(status, 200, body)
        guid = jload(body)
        self.assertIsInstance(guid, str)

        status, body = json_call(self.client, "PUT", "/api/audit", {"guid": guid, "note": "hello"})
        self.assertEqual(status, 200, body)

    def test_file_and_alarm_audit(self):
        status, body = json_call(
            self.client,
            "POST",
            "/api/audit/file",
            {
                "id": CLIENT_RID,
                "uuid": CLIENT_UUID,
                "peer_id": "999",
                "conn_id": "c100",
                "type": 0,
                "path": "C:/a.txt",
                "is_file": True,
                "info": json.dumps({"ip": "1.2.3.4", "name": "a.txt", "num": 1, "files": [["a.txt", 1024]]}),
            },
        )
        self.assertEqual((status, body), (200, ""), body)
        row = FileLog.objects.order_by("-id").first()
        self.assertEqual(row.file, "C:/a.txt")
        self.assertEqual(row.filesize, "1.0 KB")

        # 剪贴板传文件：path 为空，文件名在 info.files 里
        status, body = json_call(
            self.client,
            "POST",
            "/api/audit/file",
            {
                "id": CLIENT_RID,
                "uuid": CLIENT_UUID,
                "peer_id": "999",
                "conn_id": "c101",
                "type": 1,
                "path": "",
                "is_file": False,
                "info": json.dumps({"ip": "1.2.3.4", "num": 1, "files": [["report.pdf", 2048]]}),
            },
        )
        self.assertEqual((status, body), (200, ""), body)
        row = FileLog.objects.order_by("-id").first()
        self.assertEqual(row.file, "report.pdf")
        self.assertEqual(row.filesize, "2.0 KB")
        self.assertEqual(row.direction, 1)

        # 目录传输：path 是目录，多个文件显示数量
        status, body = json_call(
            self.client,
            "POST",
            "/api/audit/file",
            {
                "id": CLIENT_RID,
                "uuid": CLIENT_UUID,
                "peer_id": "999",
                "conn_id": "c102",
                "type": 0,
                "path": "D:/docs",
                "is_file": False,
                "info": json.dumps({"ip": "1.2.3.4", "num": 2, "files": [["a.txt", 1024], ["b.txt", 1024]]}),
            },
        )
        self.assertEqual((status, body), (200, ""), body)
        row = FileLog.objects.order_by("-id").first()
        self.assertEqual(row.file, "D:/docs/2 个文件")
        self.assertEqual(row.filesize, "2.0 KB")

        status, body = json_call(
            self.client,
            "POST",
            "/api/audit/alarm",
            {
                "id": CLIENT_RID,
                "uuid": CLIENT_UUID,
                "typ": 1,
                "info": json.dumps({"msg": "alarm"}),
                "conn_id": "c100",
            },
        )
        self.assertEqual((status, body), (200, ""), body)


class SwitchGrantTests(TokenedClientMixin, TestCase):
    def test_switch_grant_accepted(self):
        status, body = json_call(
            self.client,
            "POST",
            "/api/switch-grant",
            {
                "id": CLIENT_RID,
                "switch_code_verifier": "v",
                "timestamp": "1700000000",
                "signature": "sig",
            },
        )
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        self.assertIs(data.get("accepted"), True)


class RecordUploadTests(TokenedClientMixin, TestCase):
    def test_record_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(RECORD_ROOT=tmp):
                status, body = json_call(self.client, "POST", "/api/record?type=new&file=probe.bin", raw=b"")
                self.assertEqual(status, 200, body)
                self.assertIsInstance(jload(body), dict)

                status, body = json_call(
                    self.client, "POST", "/api/record?type=part&file=probe.bin&offset=0&length=5", raw=b"hello"
                )
                self.assertIsInstance(jload(body), dict)
                status, body = json_call(
                    self.client, "POST", "/api/record?type=part&file=probe.bin&offset=5&length=6", raw=b" world"
                )
                status, body = json_call(
                    self.client, "POST", "/api/record?type=tail&file=probe.bin&offset=0&length=5", raw=b"hello"
                )
                self.assertIsInstance(jload(body), dict)

                path = tmp + "/probe.bin"
                with open(path, "rb") as fh:
                    self.assertEqual(fh.read(), b"hello world")

                status, body = json_call(self.client, "POST", "/api/record?type=remove&file=probe.bin", raw=b"")
                self.assertIsInstance(jload(body), dict)


class DeployTests(TokenedClientMixin, TestCase):
    def test_devices_cli_returns_empty_body(self):
        status, body = json_call(
            self.client,
            "POST",
            "/api/devices/cli",
            {
                "id": "444",
                "uuid": "u444",
                "address_book_name": "cliAB",
                "device_group_name": "cliGroup",
            },
            token=self.token,
        )
        self.assertEqual((status, body), (200, ""), body)

    def test_devices_deploy(self):
        status, body = json_call(
            self.client, "POST", "/api/devices/deploy", {"id": "555", "uuid": "u555", "pk": "pk555"}, token=self.token
        )
        self.assertEqual((jload(body) or {}).get("result"), "OK", body)

        status, body = json_call(
            self.client, "POST", "/api/devices/deploy", {"id": "555", "uuid": "other", "pk": "pk555"}, token=self.token
        )
        self.assertEqual((jload(body) or {}).get("result"), "ID_TAKEN", body)


class HeartbeatWriteTests(TokenedClientMixin, TestCase):
    """心跳是全站 QPS 最高的接口，必须做到常态零写入。"""

    def setUp(self):
        super().setUp()
        make_device(
            CLIENT_RID, hostname="BEAT-1", uuid=CLIENT_UUID, cpu="x", memory="16G", os="Windows", version="1.5.3"
        )

    def _beat(self):
        status, body = json_call(
            self.client,
            "POST",
            "/api/heartbeat",
            {
                "id": CLIENT_RID,
                "uuid": CLIENT_UUID,
                "ver": 1503,
            },
        )
        self.assertEqual(status, 200, body)

    def test_repeated_heartbeat_does_not_write(self):
        self._beat()  # 首次心跳允许补写（正常情况下也不写）
        device = RustDesDevice.objects.get(rid=CLIENT_RID, uuid=CLIENT_UUID)
        token = RustDeskToken.objects.get(rid=CLIENT_RID, uuid=CLIENT_UUID)
        device_time, token_time = device.update_time, token.create_time

        self._beat()
        device.refresh_from_db()
        token.refresh_from_db()
        self.assertEqual(device.update_time, device_time, "设备时间戳不应每 15 秒重写")
        self.assertEqual(token.create_time, token_time, "token 不应每次心跳都续期")

    def test_heartbeat_follows_rid_when_uuid_changed(self):
        """客户端升级/重装后 uuid 会变；心跳必须仍按 rid 刷新设备，否则永远显示离线。"""
        stale = timezone.now() - datetime.timedelta(seconds=3600)
        RustDesDevice.objects.filter(rid=CLIENT_RID).update(update_time=stale)

        status, body = json_call(
            self.client,
            "POST",
            "/api/heartbeat",
            {
                "id": CLIENT_RID,
                "uuid": "CHANGED-UUID-0001",
                "ver": 1504,
            },
        )
        self.assertEqual(status, 200, body)

        device = RustDesDevice.objects.get(rid=CLIENT_RID)
        self.assertGreater(device.update_time, stale, "换了 uuid 的设备也必须刷新在线时间")

    def test_heartbeat_touches_stale_device_and_token(self):
        stale = timezone.now() - datetime.timedelta(seconds=3600)
        RustDesDevice.objects.filter(rid=CLIENT_RID, uuid=CLIENT_UUID).update(update_time=stale)
        RustDeskToken.objects.filter(rid=CLIENT_RID, uuid=CLIENT_UUID).update(create_time=stale)

        self._beat()

        device = RustDesDevice.objects.get(rid=CLIENT_RID, uuid=CLIENT_UUID)
        token = RustDeskToken.objects.get(rid=CLIENT_RID, uuid=CLIENT_UUID)
        self.assertGreater(device.update_time, stale)
        self.assertGreater(token.create_time, timezone.now())
