# -*- coding: utf-8 -*-
"""安全与边界冒烟测试：未授权访问矩阵、登录节流、密码策略、上传路径穿越。"""

import os
import shutil
import tempfile

from django.test import TestCase, override_settings

from api.tests.utils import jload, json_call, make_user, reset_throttle
from api.models import UserProfile

ANON_CONSOLE_GET = [
    "/api/console/me",
    "/api/console/stats",
    "/api/console/users",
    "/api/console/devices",
    "/api/console/addressbooks",
    "/api/console/groups",
    "/api/console/logs/conn",
    "/api/console/logs/file",
]
ANON_CONSOLE_POST = [
    ("/api/console/users", {"username": "x", "password": "Xx@20260"}),
    ("/api/console/groups", {"name": "g"}),
    ("/api/console/addressbooks", {"name": "ab"}),
]


class HealthTests(TestCase):
    def test_health_endpoint(self):
        status, body = json_call(self.client, "GET", "/api/health")
        data = jload(body) or {}
        self.assertEqual(status, 200, body)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["database"], "ok")
        self.assertTrue(data["version"].startswith("v"))


class AnonymousAccessTests(TestCase):
    """未登录访问控制台/客户端 API 必须 401，不能泄露数据。"""

    def test_console_get_requires_login(self):
        for path in ANON_CONSOLE_GET:
            status, body = json_call(self.client, "GET", path)
            self.assertEqual(status, 401, "%s -> %s %s" % (path, status, body))
            self.assertNotIn("list", body)

    def test_console_write_requires_login(self):
        for path, payload in ANON_CONSOLE_POST:
            status, body = json_call(self.client, "POST", path, payload)
            self.assertEqual(status, 401, "%s -> %s %s" % (path, status, body))

    def test_client_api_requires_token(self):
        status, body = json_call(self.client, "POST", "/api/currentUser", {"id": "1", "uuid": "u"})
        self.assertEqual(status, 401, body)
        for path in ("/api/users", "/api/peers", "/api/device-group/accessible"):
            status, body = json_call(self.client, "GET", path)
            self.assertEqual(status, 401, "%s -> %s %s" % (path, status, body))
        status, body = json_call(self.client, "GET", "/api/ab")
        self.assertEqual(status, 401, body)

    def test_bad_token_rejected(self):
        status, body = json_call(
            self.client, "POST", "/api/currentUser", {"id": "1", "uuid": "x"}, token="not-a-real-token"
        )
        self.assertEqual(status, 401, body)


@override_settings(LOGIN_MAX_ATTEMPTS=3, LOGIN_LOCK_SECONDS=60)
class LoginThrottleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("throttle-user", "Throttle@2026")

    def setUp(self):
        reset_throttle()

    def test_client_login_lockout(self):
        for _ in range(3):
            status, body = json_call(
                self.client,
                "POST",
                "/api/login",
                {
                    "username": "throttle-user",
                    "password": "wrong",
                    "id": "1",
                    "uuid": "u",
                    "autoLogin": False,
                    "type": "account",
                },
            )
            self.assertEqual(status, 200, body)
            self.assertIn("错误", (jload(body) or {}).get("error", ""))
        status, body = json_call(
            self.client,
            "POST",
            "/api/login",
            {
                "username": "throttle-user",
                "password": "Throttle@2026",
                "id": "1",
                "uuid": "u",
                "autoLogin": False,
                "type": "account",
            },
        )
        self.assertEqual(status, 429, body)
        self.assertIn("尝试次数过多", (jload(body) or {}).get("error", ""))

    def test_console_login_lockout(self):
        for _ in range(3):
            json_call(self.client, "POST", "/api/console/login", {"username": "throttle-user", "password": "wrong"})
        status, body = json_call(
            self.client, "POST", "/api/console/login", {"username": "throttle-user", "password": "Throttle@2026"}
        )
        self.assertEqual(status, 429, body)

    def test_success_resets_counter(self):
        json_call(self.client, "POST", "/api/console/login", {"username": "throttle-user", "password": "wrong"})
        status, body = json_call(
            self.client, "POST", "/api/console/login", {"username": "throttle-user", "password": "Throttle@2026"}
        )
        self.assertEqual(status, 200, body)
        reset_throttle()
        status, body = json_call(
            self.client, "POST", "/api/console/login", {"username": "throttle-user", "password": "Throttle@2026"}
        )
        self.assertEqual(status, 200, body)


class MalformedInputTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("mal-user", "Mal@20260")

    def test_login_malformed_json(self):
        status, body = json_call(self.client, "POST", "/api/login", raw=b"{not json")
        self.assertEqual(status, 400, body)
        self.assertIn("JSON", (jload(body) or {}).get("error", ""))

    def test_login_non_object_json(self):
        status, body = json_call(self.client, "POST", "/api/login", raw=b"[1,2,3]")
        self.assertEqual(status, 400, body)

    def test_audit_note_rejects_bad_guid(self):
        from api.tests.utils import client_login

        status, token, data, body = client_login(self.client)
        self.assertEqual(status, 200, body)
        status, body = json_call(self.client, "PUT", "/api/audit", {"guid": "abc", "note": "x"}, token=token)
        self.assertEqual(status, 400, body)


class RecordUploadSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("rec-user", "Rec@20260")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rec-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.override = override_settings(RECORD_ROOT=self.tmp)
        self.override.enable()
        self.addCleanup(self.override.disable)
        from api.tests.utils import client_login

        status, self.token, data, body = client_login(self.client)
        self.assertEqual(status, 200, body)

    def test_path_traversal_is_stripped(self):
        status, body = json_call(self.client, "POST", "/api/record?type=new&file=..%2F..%2Fevil.mp4", token=self.token)
        self.assertEqual(status, 200, body)
        self.assertEqual(sorted(os.listdir(self.tmp)), ["evil.mp4"])
        self.assertEqual(
            os.path.dirname(os.path.abspath(os.path.join(self.tmp, "evil.mp4"))), os.path.abspath(self.tmp)
        )
        status, body = json_call(
            self.client, "POST", "/api/record?type=new&file=..%2F..%2F..%2Ftmp%2Fpwned.bin", token=self.token
        )
        self.assertEqual(status, 200, body)
        for name in os.listdir(self.tmp):
            self.assertNotIn("..", name)
            self.assertNotIn("/", name)

    def test_invalid_names_rejected(self):
        for name in ("", ".", "..", "%2e%2e"):
            status, body = json_call(self.client, "POST", "/api/record?type=new&file=" + name, token=self.token)
            self.assertIn(status, (400,), "%r -> %s" % (name, status))

    def test_oversize_chunk_rejected(self):
        big = b"x" * (8 * 1024 * 1024 + 1)
        status, body = json_call(
            self.client, "POST", "/api/record?type=part&file=big.bin&offset=0", token=self.token, raw=big
        )
        self.assertEqual(status, 413, body)


@override_settings(ALLOW_REGISTRATION=True, PASSWORD_VALIDATION=True)
class RegistrationPolicyTests(TestCase):
    def test_weak_password_rejected(self):
        from django.test import Client

        c = Client()
        resp = c.post("/api/user_action?action=register", {"user": "newbie01", "pwd": "12345678"})
        data = jload(resp.content.decode("utf-8", "replace")) or {}
        self.assertEqual(data.get("code"), 0, resp.content)
        self.assertIn("密码", data.get("msg", ""))
        from django.contrib.auth import get_user_model

        self.assertFalse(get_user_model().objects.filter(username="newbie01").exists())

    def test_common_password_rejected(self):
        from django.test import Client

        c = Client()
        resp = c.post("/api/user_action?action=register", {"user": "newbie02", "pwd": "password123"})
        data = jload(resp.content.decode("utf-8", "replace")) or {}
        self.assertEqual(data.get("code"), 0, resp.content)


class CsrfProtectionTests(TestCase):
    """客户端 API 豁免 CSRF；控制台 Session 接口必须带 token。"""

    def test_client_api_is_csrf_exempt(self):
        from django.test import Client

        c = Client(enforce_csrf_checks=True)
        resp = c.post("/api/login", data="{}", content_type="application/json")
        self.assertNotEqual(resp.status_code, 403, resp.content[:200])

    def test_console_write_requires_csrf_token(self):
        from django.test import Client

        c = Client(enforce_csrf_checks=True)
        resp = c.post("/api/console/login", data='{"username":"a","password":"b"}', content_type="application/json")
        self.assertEqual(resp.status_code, 403, resp.content[:200])

    def test_console_index_sets_cookie_and_token_is_accepted(self):
        from django.test import Client

        c = Client(enforce_csrf_checks=True)
        resp = c.get("/console/")
        self.assertEqual(resp.status_code, 200)
        token = resp.cookies.get("csrftoken")
        self.assertIsNotNone(token, "控制台首页应下发 csrftoken Cookie")
        resp = c.post(
            "/api/console/login",
            data='{"username":"nobody","password":"bad"}',
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token.value,
        )
        # 凭证错误应返回 401/400，而不是 CSRF 403
        self.assertNotEqual(resp.status_code, 403, resp.content[:200])


class OldConsoleRemovedTests(TestCase):
    """旧版 LayUI 管理页已彻底移除，API 服务器入口只剩 /console/。"""

    def test_root_redirects_to_console(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/console/")

    def test_legacy_pages_are_gone(self):
        for path in ("/api/work", "/api/conn_log", "/api/file_log", "/api/share", "/api/down_peers"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 404, path)

    def test_web_control_terminal_removed(self):
        """旧 Flutter Web 控制端已下线：页面与静态资源都不再提供。"""
        for path in ("/webui/", "/webui", "/static/web_client/manifest.json"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 404, path)

    def test_user_action_get_redirects_to_console(self):
        for query in ("login", "register", "logout"):
            resp = self.client.get("/api/user_action?action=" + query)
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp["Location"], "/console/")

    def test_user_action_login_post_is_retired(self):
        resp = self.client.post("/api/user_action?action=login", {"account": "a", "password": "b"})
        self.assertEqual(resp.status_code, 410)

    @override_settings(ALLOW_REGISTRATION=True)
    def test_register_api_still_works(self):
        resp = self.client.post("/api/user_action?action=register", {"user": "legacy-reg", "pwd": "Reg@2026pass"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("code"), 1)
        self.assertTrue(UserProfile.objects.filter(username="legacy-reg").exists())
