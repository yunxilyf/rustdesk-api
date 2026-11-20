# -*- coding: utf-8 -*-
"""控制台 JSON API 冒烟测试：认证、权限隔离、CRUD、分页、校验。"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from api.models_pro import AddressBook, AddressBookPeer
from api.models_work import ConnLog, FileLog, RustDeskPeer, RustDesDevice
from api.tests.utils import (
    bind_device,
    jload,
    json_call,
    make_device,
    make_group,
    make_user,
    reset_throttle,
)

User = get_user_model()
ADMIN_PWD = "Admin@2026"
OPS_PWD = "Ops@2026"


class ConsoleTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("smoke-admin", ADMIN_PWD, is_admin=True, display_name="管理员")
        cls.ops = make_user("smoke-ops", OPS_PWD, display_name="运维")
        make_device("d-ops-1", hostname="OPS-PC", username="ops", os="Windows 11")
        make_device("d-adm-1", hostname="ADM-PC", username="admin", os="macOS 15")
        make_device("d-adm-2", hostname="ADM-PC-2", username="admin", os="Ubuntu 24.04")
        bind_device(cls.ops, "d-ops-1", "OPS-PC")
        bind_device(cls.admin, "d-adm-1", "ADM-PC")
        bind_device(cls.admin, "d-adm-2", "ADM-PC-2")
        cls.shared = AddressBook.objects.create(guid="shared01", owner=cls.admin, name="共享地址簿", rule=0)
        AddressBookPeer.objects.create(ab=cls.shared, rid="d-adm-1", hostname="ADM-PC")
        cls.group = make_group(cls.admin, "运维组", ["d-adm-1"])
        cls.conn = ConnLog.objects.create(
            action="new",
            conn_id="c1",
            from_ip="10.0.0.1",
            from_id="d-ops-1",
            rid="d-adm-1",
            session_id="s1",
            note="远程协助",
        )
        cls.filelog = FileLog.objects.create(
            file="a.txt", remote_id="d-adm-1", user_id="admin", user_ip="10.0.0.9", filesize="100", direction=1
        )

    def setUp(self):
        reset_throttle()

    def login(self, username, password):
        status, body = json_call(
            self.client, "POST", "/api/console/login", {"username": username, "password": password}
        )
        self.assertEqual(status, 200, body)
        return jload(body)

    def logout(self):
        json_call(self.client, "POST", "/api/console/logout")


class AuthTests(ConsoleTestCase):
    def test_login_me_logout(self):
        data = self.login("smoke-admin", ADMIN_PWD)
        self.assertTrue(data["ok"])
        self.assertEqual(data["user"]["username"], "smoke-admin")
        self.assertTrue(data["user"]["is_admin"])

        status, body = json_call(self.client, "GET", "/api/console/me")
        self.assertEqual(status, 200, body)
        self.assertEqual((jload(body) or {})["user"]["username"], "smoke-admin")

        self.logout()
        status, body = json_call(self.client, "GET", "/api/console/me")
        self.assertEqual(status, 401, body)

    def test_wrong_password(self):
        status, body = json_call(
            self.client, "POST", "/api/console/login", {"username": "smoke-admin", "password": "bad"}
        )
        self.assertEqual(status, 400, body)
        self.assertFalse((jload(body) or {}).get("ok"))

    def test_setup_only_allowed_on_empty_database(self):
        status, body = json_call(self.client, "GET", "/api/console/setup")
        self.assertEqual(status, 200)
        self.assertFalse((jload(body) or {})["needs_setup"])

        status, body = json_call(
            self.client, "POST", "/api/console/setup", {"username": "late-admin", "password": "Late@2026"}
        )
        self.assertEqual(status, 403, body)

        User.objects.all().delete()
        status, body = json_call(self.client, "GET", "/api/console/setup")
        self.assertTrue((jload(body) or {})["needs_setup"])

        status, body = json_call(
            self.client, "POST", "/api/console/setup", {"username": "first-admin", "password": "First@2026"}
        )
        self.assertEqual(status, 200, body)
        self.assertTrue((jload(body) or {})["user"]["is_admin"])
        self.assertTrue(User.objects.get(username="first-admin").is_admin)

    def test_password_change(self):
        self.login("smoke-ops", OPS_PWD)
        status, body = json_call(
            self.client, "PUT", "/api/console/me/password", {"old": "wrong", "password": "New@2026"}
        )
        self.assertEqual(status, 400, body)
        status, body = json_call(
            self.client, "PUT", "/api/console/me/password", {"old": OPS_PWD, "password": "12345678"}
        )
        self.assertEqual(status, 400, body)
        status, body = json_call(
            self.client, "PUT", "/api/console/me/password", {"old": OPS_PWD, "password": "New@2026"}
        )
        self.assertEqual(status, 200, body)
        self.logout()
        self.login("smoke-ops", "New@2026")


class ProfileTests(ConsoleTestCase):
    def test_update_own_profile(self):
        self.login("smoke-admin", ADMIN_PWD)
        status, body = json_call(
            self.client, "PATCH", "/api/console/me", {"display_name": "运维小王", "email": "ops@example.com"}
        )
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        self.assertEqual(data["user"]["display_name"], "运维小王")
        self.assertEqual(data["user"]["email"], "ops@example.com")
        user = User.objects.get(username="smoke-admin")
        self.assertEqual(user.display_name, "运维小王")
        self.assertEqual(user.email, "ops@example.com")

    def test_update_profile_validation(self):
        self.login("smoke-admin", ADMIN_PWD)
        status, body = json_call(self.client, "PATCH", "/api/console/me", {"email": "not-an-email"})
        self.assertEqual(status, 400, body)
        status, body = json_call(self.client, "PATCH", "/api/console/me", {"display_name": "x" * 65})
        self.assertEqual(status, 400, body)

    def test_update_profile_requires_login(self):
        status, body = json_call(self.client, "PATCH", "/api/console/me", {"display_name": "x"})
        self.assertEqual(status, 401, body)


class SettingsTests(ConsoleTestCase):
    def test_registration_toggle(self):
        self.login("smoke-admin", ADMIN_PWD)
        status, body = json_call(self.client, "GET", "/api/console/settings")
        self.assertEqual(status, 200, body)
        self.assertTrue((jload(body) or {}).get("allow_registration"))

        status, body = json_call(self.client, "PUT", "/api/console/settings", {"allow_registration": False})
        self.assertEqual(status, 200, body)

        resp = self.client.post("/api/user_action?action=register", {"user": "newbie-x", "pwd": "Str0ng@2026"})
        self.assertEqual((jload(resp.content.decode()) or {}).get("code"), 0)
        self.assertFalse(User.objects.filter(username="newbie-x").exists())

        json_call(self.client, "PUT", "/api/console/settings", {"allow_registration": True})
        resp = self.client.post("/api/user_action?action=register", {"user": "newbie-y", "pwd": "Str0ng@2026"})
        self.assertEqual((jload(resp.content.decode()) or {}).get("code"), 1, resp.content)
        self.assertTrue(User.objects.filter(username="newbie-y").exists())

    def test_settings_write_requires_admin(self):
        self.login("smoke-ops", OPS_PWD)
        status, body = json_call(self.client, "PUT", "/api/console/settings", {"allow_registration": False})
        self.assertEqual(status, 403, body)

    def test_console_register_respects_switch(self):
        self.login("smoke-admin", ADMIN_PWD)
        json_call(self.client, "PUT", "/api/console/settings", {"allow_registration": False})
        self.client.post("/api/console/logout")
        status, body = json_call(
            self.client, "POST", "/api/console/register", {"username": "self-reg", "password": "Str0ng@2026"}
        )
        self.assertFalse((jload(body) or {}).get("ok"), body)
        self.assertFalse(User.objects.filter(username="self-reg").exists())

        self.login("smoke-admin", ADMIN_PWD)
        json_call(self.client, "PUT", "/api/console/settings", {"allow_registration": True})
        self.client.post("/api/console/logout")
        status, body = json_call(
            self.client, "POST", "/api/console/register", {"username": "self-reg", "password": "Str0ng@2026"}
        )
        self.assertEqual(status, 200, body)
        self.assertTrue((jload(body) or {}).get("ok"))
        self.assertTrue(User.objects.filter(username="self-reg").exists())

    def test_console_register_rejects_weak_password(self):
        self.login("smoke-admin", ADMIN_PWD)
        json_call(self.client, "PUT", "/api/console/settings", {"allow_registration": True})
        self.client.post("/api/console/logout")
        status, body = json_call(
            self.client, "POST", "/api/console/register", {"username": "weak-pw", "password": "123"}
        )
        self.assertIn(status, (200, 400), body)
        self.assertFalse((jload(body) or {}).get("ok"))
        self.assertFalse(User.objects.filter(username="weak-pw").exists())


class PermissionTests(ConsoleTestCase):
    def test_admin_sees_all_devices(self):
        self.login("smoke-admin", ADMIN_PWD)
        status, body = json_call(self.client, "GET", "/api/console/devices")
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        self.assertEqual(data["total"], 3)

    def test_user_sees_only_own_devices(self):
        self.login("smoke-ops", OPS_PWD)
        status, body = json_call(self.client, "GET", "/api/console/devices")
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["list"][0]["rid"], "d-ops-1")

    def test_user_cannot_access_admin_endpoints(self):
        self.login("smoke-ops", OPS_PWD)
        for path in ("/api/console/users", "/api/console/stats/x"):
            status, body = json_call(self.client, "GET", path)
            self.assertIn(status, (403, 404), "%s -> %s" % (path, status))
        status, body = json_call(
            self.client, "POST", "/api/console/users", {"username": "hacker", "password": "Hack@2026"}
        )
        self.assertEqual(status, 403, body)

    def test_user_cannot_edit_other_address_book(self):
        self.login("smoke-ops", OPS_PWD)
        status, body = json_call(
            self.client, "POST", "/api/console/addressbooks/shared01/peers", {"id": "x1", "hostname": "evil"}
        )
        self.assertEqual(status, 403, body)

    def test_user_cannot_reassign_devices(self):
        self.login("smoke-ops", OPS_PWD)
        status, body = json_call(self.client, "PUT", "/api/console/devices/d-adm-1/owner", {"user_id": self.ops.id})
        self.assertEqual(status, 403, body)

    def test_logs_are_scoped(self):
        self.login("smoke-ops", OPS_PWD)
        status, body = json_call(self.client, "GET", "/api/console/logs/conn")
        self.assertEqual((jload(body) or {})["total"], 1)  # 只看到自己发起的连接
        status, body = json_call(self.client, "GET", "/api/console/logs/file")
        self.assertEqual(status, 200)
        self.assertEqual((jload(body) or {})["total"], 0)


class DeviceTests(ConsoleTestCase):
    def test_device_filters(self):
        self.login("smoke-admin", ADMIN_PWD)
        status, body = json_call(self.client, "GET", "/api/console/devices?keyword=ADM-PC")
        self.assertEqual((jload(body) or {})["total"], 2)
        status, body = json_call(self.client, "GET", "/api/console/devices?status=offline")
        self.assertEqual(status, 200)

    def test_online_window_survives_heartbeat_throttle(self):
        """心跳每 HEARTBEAT_DEVICE_TOUCH_SECONDS 秒才写一次库，在线窗口必须更宽，
        否则设备会在两次写库之间闪成离线。"""
        self.login("smoke-admin", ADMIN_PWD)
        rid = "d-adm-1"

        def is_online():
            status, body = json_call(self.client, "GET", "/api/console/devices?keyword=ADM-PC")
            rows = [r for r in (jload(body) or {}).get("list", []) if r["rid"] == rid]
            self.assertTrue(rows, body)
            return rows[0]["online"]

        RustDesDevice.objects.filter(rid=rid).update(update_time=timezone.now() - datetime.timedelta(seconds=200))
        self.assertTrue(is_online())

        RustDesDevice.objects.filter(rid=rid).update(update_time=timezone.now() - datetime.timedelta(seconds=400))
        self.assertFalse(is_online())

    def test_reassign_device(self):
        self.login("smoke-admin", ADMIN_PWD)
        status, body = json_call(self.client, "PUT", "/api/console/devices/d-adm-2/owner", {"user_id": self.ops.id})
        self.assertEqual(status, 200, body)
        self.assertTrue(RustDeskPeer.objects.filter(rid="d-adm-2", uid=str(self.ops.id)).exists())
        status, body = json_call(self.client, "DELETE", "/api/console/devices/d-adm-2/owner")
        self.assertEqual(status, 200, body)
        self.assertFalse(RustDeskPeer.objects.filter(rid="d-adm-2").exists())


class AddressBookTests(ConsoleTestCase):
    def setUp(self):
        super().setUp()
        self.login("smoke-admin", ADMIN_PWD)

    def personal_guid(self):
        status, body = json_call(self.client, "GET", "/api/console/addressbooks")
        data = jload(body) or {}
        for item in data["list"]:
            if item["is_personal"]:
                return item["guid"]
        self.fail("personal address book missing: %s" % body)

    def test_shared_password_flag_not_plaintext(self):
        """共享地址簿保存连接密码，但接口只回 has_password，不回明文。"""
        from api.models_pro import AddressBook

        AddressBook.objects.create(guid="shared1", owner=self.admin, name="共享组", rule=2)
        status, body = json_call(
            self.client, "POST", "/api/console/addressbooks/shared1/peers", {"id": "p3", "password": "s3cret"}
        )
        self.assertEqual(status, 200, body)
        body = json_call(self.client, "GET", "/api/console/addressbooks/shared1/peers?keyword=p3")[1]
        row = (jload(body) or {})["list"][0]
        self.assertTrue(row["has_password"])
        self.assertNotIn("password", row)

        json_call(self.client, "POST", "/api/console/addressbooks/shared1/peers", {"id": "p3", "password": ""})
        body = json_call(self.client, "GET", "/api/console/addressbooks/shared1/peers?keyword=p3")[1]
        self.assertFalse((jload(body) or {})["list"][0]["has_password"])

    def test_peer_row_fills_device_info(self):
        """联系人没自带主机名/平台时，用 sysinfo 上报的设备信息补全展示。"""
        from api.tests.utils import make_device

        guid = self.personal_guid()
        make_device("p2", hostname="MERGED-PC", os="Windows 11")
        status, body = json_call(self.client, "POST", "/api/console/addressbooks/%s/peers" % guid, {"id": "p2"})
        self.assertEqual(status, 200, body)
        status, body = json_call(self.client, "GET", "/api/console/addressbooks/%s/peers?keyword=p2" % guid)
        row = (jload(body) or {})["list"][0]
        self.assertEqual(row["hostname"], "MERGED-PC")
        self.assertEqual(row["platform"], "Windows")

    def test_personal_address_book_autocreated(self):
        status, body = json_call(self.client, "GET", "/api/console/addressbooks")
        self.assertEqual(status, 200, body)
        self.assertTrue(any(i["is_personal"] for i in (jload(body) or {})["list"]))

    def test_peer_and_tag_crud(self):
        guid = self.personal_guid()
        status, body = json_call(self.client, "GET", "/api/console/addressbooks/%s/peers" % guid)
        before = (jload(body) or {}).get("total", 0)
        status, body = json_call(
            self.client,
            "POST",
            "/api/console/addressbooks/%s/peers" % guid,
            {"id": "p1", "hostname": "NEW-PC", "alias": "新机器", "tags": ["生产"]},
        )
        self.assertEqual(status, 200, body)

        status, body = json_call(self.client, "GET", "/api/console/addressbooks/%s/peers?keyword=NEW" % guid)
        data = jload(body) or {}
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["list"][0]["alias"], "新机器")

        status, body = json_call(self.client, "DELETE", "/api/console/addressbooks/%s/peers" % guid, {"ids": ["p1"]})
        self.assertEqual(status, 200, body)
        self.assertEqual(
            (jload(json_call(self.client, "GET", "/api/console/addressbooks/%s/peers" % guid)[1]) or {})["total"],
            before,
        )

        status, body = json_call(
            self.client, "POST", "/api/console/addressbooks/%s/tags" % guid, {"name": "机房A", "color": 3}
        )
        self.assertEqual(status, 200, body)
        status, body = json_call(
            self.client, "POST", "/api/console/addressbooks/%s/tags" % guid, {"name": "客户端色", "color": 0xFF00BCD4}
        )
        self.assertEqual(status, 200, body)
        status, body = json_call(self.client, "GET", "/api/console/addressbooks/%s/tags" % guid)
        tags = {t["name"]: t["color"] for t in ((jload(body) or {}).get("list") or [])}
        self.assertEqual(tags.get("机房A"), 0xFFFF9800)
        self.assertEqual(tags.get("客户端色"), 0xFF00BCD4)
        self.assertNotIn(tags.get("机房A"), (0, 1, 2, 3))


class GroupTests(ConsoleTestCase):
    def setUp(self):
        super().setUp()
        self.login("smoke-admin", ADMIN_PWD)

    def test_duplicate_addressbook_name_rejected(self):
        status, body = json_call(self.client, "POST", "/api/console/addressbooks", {"name": "重名簿"})
        self.assertEqual(status, 200, body)
        status, body = json_call(self.client, "POST", "/api/console/addressbooks", {"name": "重名簿"})
        self.assertEqual(status, 400, body)
        self.assertIn("已存在", (jload(body) or {}).get("msg", ""))

    def test_personal_addressbook_name_is_readonly(self):
        status, body = json_call(self.client, "GET", "/api/console/addressbooks")
        self.assertEqual(status, 200, body)
        books = (jload(body) or {}).get("list") or []
        personal = next(b for b in books if b.get("is_personal"))
        status, body = json_call(
            self.client, "PUT", "/api/console/addressbooks/%s" % personal["guid"], {"name": "我想改个名"}
        )
        self.assertEqual(status, 400, body)
        self.assertIn("我的地址簿", (jload(body) or {}).get("msg", ""))
        status, body = json_call(
            self.client, "PUT", "/api/console/addressbooks/%s" % personal["guid"], {"note": "备注可以改"}
        )
        self.assertEqual(status, 200, body)

    def test_group_crud_and_members(self):
        status, body = json_call(self.client, "POST", "/api/console/groups", {"name": "新分组", "note": "备注"})
        self.assertEqual(status, 200, body)
        guid = (jload(body) or {}).get("guid")
        self.assertTrue(guid)

        status, body = json_call(self.client, "POST", "/api/console/groups/%s/members" % guid, {"rids": ["d-adm-2"]})
        self.assertEqual(status, 200, body)

        status, body = json_call(self.client, "GET", "/api/console/groups/%s/members" % guid)
        self.assertEqual((jload(body) or {}).get("total"), 1)

        status, body = json_call(self.client, "PUT", "/api/console/groups/%s" % guid, {"name": "改名分组"})
        self.assertEqual(status, 200, body)
        self.assertEqual((jload(body) or {}).get("name", "改名分组"), "改名分组")

        status, body = json_call(self.client, "DELETE", "/api/console/groups/%s" % guid)
        self.assertEqual(status, 200, body)

    def test_group_validation(self):
        status, body = json_call(self.client, "POST", "/api/console/groups", {"name": ""})
        self.assertEqual(status, 400, body)


class UserTests(ConsoleTestCase):
    def setUp(self):
        super().setUp()
        self.login("smoke-admin", ADMIN_PWD)

    def test_create_and_update_user(self):
        status, body = json_call(
            self.client,
            "POST",
            "/api/console/users",
            {"username": "newbie", "password": "Newbie@2026", "display_name": "新人"},
        )
        self.assertEqual(status, 200, body)
        uid = (jload(body) or {})["id"]

        status, body = json_call(
            self.client, "PUT", "/api/console/users/%s" % uid, {"display_name": "新名字", "is_active": False}
        )
        self.assertEqual(status, 200, body)
        user = User.objects.get(id=uid)
        self.assertEqual(user.display_name, "新名字")
        self.assertFalse(user.is_active)

        status, body = json_call(self.client, "DELETE", "/api/console/users/%s" % uid)
        self.assertEqual(status, 200, body)
        self.assertFalse(User.objects.filter(id=uid).exists())

    def test_user_validation(self):
        status, body = json_call(
            self.client, "POST", "/api/console/users", {"username": "weak", "password": "12345678"}
        )
        self.assertEqual(status, 400, body)
        self.assertIn("密码", (jload(body) or {}).get("msg", ""))

        status, body = json_call(
            self.client, "POST", "/api/console/users", {"username": "smoke-admin", "password": "Dup@2026"}
        )
        self.assertEqual(status, 400, body)

        status, body = json_call(self.client, "POST", "/api/console/users", {"username": "x", "password": "Short@2026"})
        self.assertEqual(status, 400, body)

    def test_cannot_disable_or_delete_self(self):
        status, body = json_call(self.client, "PUT", "/api/console/users/%s" % self.admin.id, {"is_active": False})
        self.assertEqual(status, 400, body)
        status, body = json_call(self.client, "PUT", "/api/console/users/%s" % self.admin.id, {"is_admin": False})
        self.assertEqual(status, 400, body)
        status, body = json_call(self.client, "DELETE", "/api/console/users/%s" % self.admin.id)
        self.assertEqual(status, 400, body)

    def test_admin_password_reset(self):
        status, body = json_call(self.client, "PUT", "/api/console/users/%s" % self.ops.id, {"password": "Reset@2026"})
        self.assertEqual(status, 200, body)
        self.logout()
        self.login("smoke-ops", "Reset@2026")


class LogAndStatsTests(ConsoleTestCase):
    def setUp(self):
        super().setUp()
        self.login("smoke-admin", ADMIN_PWD)

    def test_conn_logs(self):
        status, body = json_call(self.client, "GET", "/api/console/logs/conn?keyword=远程")
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["list"][0]["note"], "远程协助")

    def test_pagination(self):
        for i in range(5):
            ConnLog.objects.create(
                action="new",
                conn_id="cx%d" % i,
                from_ip="10.1.0.%d" % i,
                from_id="d-ops-1",
                rid="d-adm-1",
                session_id="s%d" % i,
            )
        status, body = json_call(self.client, "GET", "/api/console/logs/conn?current=1&pageSize=2")
        data = jload(body) or {}
        self.assertEqual(len(data["list"]), 2)
        self.assertEqual(data["total"], 6)

    def test_devices_are_deduplicated_by_rid(self):
        from api.models_work import RustDesDevice
        from django.db import connection

        dup = make_device("d-ops-1", hostname="OLD-ROW", username="ops")
        with connection.cursor() as cur:
            cur.execute("UPDATE api_rustdesdevice SET update_time='2020-01-01 00:00:00' WHERE id=%s", [dup.id])
        status, body = json_call(self.client, "GET", "/api/console/devices?current=1&pageSize=50")
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        self.assertEqual(data.get("total"), 3, body)
        rows = [r for r in data.get("list", []) if r.get("rid") == "d-ops-1"]
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0].get("hostname"), "OPS-PC")

        status, body = json_call(self.client, "GET", "/api/console/stats")
        self.assertEqual((jload(body) or {})["devices"]["total"], 3)
        self.assertEqual(RustDesDevice.objects.filter(rid="d-ops-1").count(), 2)

    def test_stats(self):
        status, body = json_call(self.client, "GET", "/api/console/stats")
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        for key in ("devices", "users", "addressbooks"):
            self.assertIn(key, data, body)
        self.assertEqual(data["devices"]["total"], 3)
