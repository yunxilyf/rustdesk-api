# -*- coding: utf-8 -*-
"""生产配置与运维接口测试：环境变量解析、节流键、健康检查、安全响应头。"""

import json
import os
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from api import throttle
from rustdesk_server_api.env import env_bool, env_int, env_list, env_str


class EnvHelpersTests(TestCase):
    def test_env_bool_accepts_common_spellings(self):
        for raw in ("1", "true", "TRUE", "yes", "on", " y "):
            with mock.patch.dict(os.environ, {"X_FLAG": raw}):
                self.assertTrue(env_bool("X_FLAG"), raw)
        for raw in ("0", "false", "False", "no", "off", ""):
            with mock.patch.dict(os.environ, {"X_FLAG": raw}):
                self.assertFalse(env_bool("X_FLAG"), raw)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(env_bool("X_MISSING", True))
            self.assertFalse(env_bool("X_MISSING"))

    def test_env_bool_does_not_treat_false_string_as_true(self):
        # 回归：旧写法 os.environ.get("DEBUG", False) 会把 "False" 当成真值
        with mock.patch.dict(os.environ, {"DEBUG": "False"}):
            self.assertFalse(env_bool("DEBUG", False))

    def test_env_int_and_list(self):
        with mock.patch.dict(os.environ, {"X_N": "42"}):
            self.assertEqual(env_int("X_N", 1), 42)
        with mock.patch.dict(os.environ, {"X_N": "abc"}):
            self.assertEqual(env_int("X_N", 7), 7)
        with mock.patch.dict(os.environ, {"X_LIST": "a.com, b.com ,,c.com"}):
            self.assertEqual(env_list("X_LIST"), ["a.com", "b.com", "c.com"])
        with mock.patch.dict(os.environ, {"X_S": "  hi  "}):
            self.assertEqual(env_str("X_S"), "hi")


class ThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def tearDown(self):
        cache.clear()

    @override_settings(LOGIN_MAX_ATTEMPTS=2, LOGIN_LOCK_SECONDS=60)
    def test_fail_then_block_then_reset(self):
        request = self.factory.post("/api/login")
        self.assertFalse(throttle.blocked("api", request, "alice"))
        throttle.fail("api", request, "alice")
        self.assertFalse(throttle.blocked("api", request, "alice"))
        throttle.fail("api", request, "alice")
        self.assertTrue(throttle.blocked("api", request, "alice"))
        throttle.reset("api", request, "alice")
        self.assertFalse(throttle.blocked("api", request, "alice"))

    def test_key_is_hashed_and_scoped(self):
        request = self.factory.post("/api/login", REMOTE_ADDR="10.0.0.9")
        key = throttle._key("api", request, "Alice@Example.com")
        self.assertTrue(key.startswith("login:fail:"))
        self.assertNotIn("alice", key.lower())
        self.assertNotIn("10.0.0.9", key)
        self.assertNotEqual(key, throttle._key("console", request, "Alice@Example.com"))
        self.assertNotEqual(key, throttle._key("api", request, "bob"))

    def test_scope_is_independent(self):
        request = self.factory.post("/api/login")
        with override_settings(LOGIN_MAX_ATTEMPTS=1, LOGIN_LOCK_SECONDS=60):
            throttle.fail("api", request, "bob")
            self.assertTrue(throttle.blocked("api", request, "bob"))
            self.assertFalse(throttle.blocked("console", request, "bob"))


class HealthTests(TestCase):
    def test_health_ok_reports_cache_and_database(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["database"], "ok")
        self.assertEqual(data["cache"], "ok")
        self.assertEqual(data["cache_backend"], "locmem")
        self.assertFalse(data["debug"])
        self.assertTrue(data["version"])

    def test_health_returns_503_when_database_down(self):
        with mock.patch("django.db.connections") as connections:
            connections.__getitem__.return_value.cursor.side_effect = RuntimeError("down")
            response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "error")

    def test_health_degrades_when_cache_down(self):
        with mock.patch.object(cache, "set", side_effect=RuntimeError("cache down")):
            response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["cache"], "error")
        self.assertEqual(data["database"], "ok")


class ProductionSettingsTests(TestCase):
    def test_defaults_are_production_safe(self):
        self.assertFalse(settings.DEBUG)
        self.assertIsInstance(settings.ALLOWED_HOSTS, list)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertTrue(settings.X_FRAME_OPTIONS)
        self.assertEqual(settings.CACHE_BACKEND, "locmem")
        self.assertIn("file", settings.LOGGING["handlers"])
        self.assertGreaterEqual(settings.LOGIN_MAX_ATTEMPTS, 3)
        self.assertTrue(settings.PASSWORD_VALIDATION)

    def test_security_headers_are_sent(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("Referrer-Policy"), "same-origin")


class EnvFileTests(TestCase):
    def test_load_env_file_keeps_existing_values(self):
        import pathlib
        import tempfile

        from rustdesk_server_api.env import load_env_file

        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / ".env"
            path.write_text(
                '# comment line\nFOO=bar\nQUOTED="a b"\nEXISTING=new\n',
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"EXISTING": "keep"}):
                load_env_file(str(path))
                self.assertEqual(os.environ["FOO"], "bar")
                self.assertEqual(os.environ["QUOTED"], "a b")
                self.assertEqual(os.environ["EXISTING"], "keep")


class DoctorCommandTests(TestCase):
    @override_settings(SECRET_KEY="t" * 50, ALLOWED_HOSTS=["testserver"])
    def test_doctor_json_output(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("doctor", "--json", stdout=out)
        data = json.loads(out.getvalue())
        checks = {item["name"]: item for item in data["checks"]}
        self.assertEqual(checks["SECRET_KEY"]["level"], "OK")
        self.assertEqual(checks["ALLOWED_HOSTS"]["level"], "OK")
        self.assertEqual(checks["DEBUG"]["level"], "OK")
        self.assertEqual(checks["数据库"]["level"], "OK")
        self.assertIn(checks["缓存"]["level"], ("OK", "WARN"))
        self.assertEqual(checks["控制台"]["level"], "OK")
