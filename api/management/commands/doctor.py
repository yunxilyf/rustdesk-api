# -*- coding: utf-8 -*-
"""部署自检：类似 `manage.py check --deploy`，但覆盖本项目实际依赖的运行时条件。

用法：
    python manage.py doctor          # 人类可读
    python manage.py doctor --json   # 机器可读（CI/监控）

退出码 0 表示没有 FAIL（WARN 不影响退出码）。
"""

import json
import os

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = "检查生产部署配置与运行环境（密钥、域名、缓存、数据库、目录、静态资源）"

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="输出 JSON")

    def handle(self, *args, **options):
        checks = []
        checks.append(self._secret_key())
        checks.append(self._allowed_hosts())
        checks.append(self._debug())
        checks.append(self._cache())
        checks.append(self._database())
        checks.append(self._writable("录像目录", settings.RECORD_ROOT))
        checks.append(self._writable("日志目录", os.path.dirname(settings.LOGGING["handlers"]["file"]["filename"])))
        checks.append(self._console())
        checks.append(self._users())

        if options["json"]:
            self.stdout.write(json.dumps({"checks": checks}, ensure_ascii=False, indent=2))
        else:
            for item in checks:
                self.stdout.write("%-5s %-12s %s" % (item["level"], item["name"], item["detail"]))
            failed = [c for c in checks if c["level"] == "FAIL"]
            warned = [c for c in checks if c["level"] == "WARN"]
            self.stdout.write("")
            self.stdout.write(
                "结果：%d 项通过，%d 项警告，%d 项失败"
                % (len(checks) - len(failed) - len(warned), len(warned), len(failed))
            )

        if any(c["level"] == "FAIL" for c in checks):
            raise SystemExit(1)

    # ------------------------------------------------------------------
    @staticmethod
    def _item(name, level, detail):
        return {"name": name, "level": level, "detail": detail}

    def _secret_key(self):
        default = "j%7yjvygpih=6b%qf!q%&ixpn+27dngzdu-i3xh-^3xgy3^nnc"
        if settings.SECRET_KEY == default:
            return self._item("SECRET_KEY", "FAIL", "仍在使用仓库默认值，生产必须通过环境变量替换")
        if len(settings.SECRET_KEY) < 32:
            return self._item("SECRET_KEY", "WARN", "长度偏短（建议 ≥50 字符随机串）")
        return self._item("SECRET_KEY", "OK", "已自定义（长度 %d）" % len(settings.SECRET_KEY))

    def _allowed_hosts(self):
        hosts = settings.ALLOWED_HOSTS or []
        if not hosts:
            return self._item("ALLOWED_HOSTS", "FAIL", "为空，请求会被拒绝")
        if "*" in hosts:
            return self._item("ALLOWED_HOSTS", "WARN", "包含 *，生产建议写真实域名/IP")
        return self._item("ALLOWED_HOSTS", "OK", ", ".join(hosts))

    def _debug(self):
        if settings.DEBUG:
            return self._item("DEBUG", "FAIL", "调试模式已开启，会泄露堆栈与配置")
        return self._item("DEBUG", "OK", "已关闭")

    def _cache(self):
        backend = getattr(settings, "CACHE_BACKEND", "unknown")
        try:
            cache.set("doctor:ping", "1", 5)
            ok = cache.get("doctor:ping") == "1"
            cache.delete("doctor:ping")
        except Exception as exc:  # pragma: no cover - 依赖外部服务
            return self._item("缓存", "FAIL", "%s 不可用：%s" % (backend, exc))
        if not ok:
            return self._item("缓存", "FAIL", "%s 读写异常" % backend)
        if backend.startswith("locmem"):
            return self._item("缓存", "WARN", "进程内缓存；多进程/多实例部署请配置 CACHE_URL（Redis）")
        return self._item("缓存", "OK", backend)

    def _database(self):
        try:
            with connections["default"].cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        except Exception as exc:
            return self._item("数据库", "FAIL", "连接失败：%s" % exc)
        engine = connections["default"].settings_dict.get("ENGINE", "")
        return self._item("数据库", "OK", engine.rsplit(".", 1)[-1])

    @staticmethod
    def _writable(name, path):
        try:
            os.makedirs(path, exist_ok=True)
            probe = os.path.join(path, ".doctor-probe")
            with open(probe, "w", encoding="utf-8") as handle:
                handle.write("ok")
            os.remove(probe)
        except OSError as exc:
            return {"name": name, "level": "FAIL", "detail": "%s 不可写：%s" % (path, exc)}
        return {"name": name, "level": "OK", "detail": path}

    def _console(self):
        index_path = os.path.join(str(settings.BASE_DIR), "static", "console", "index.html")
        if not os.path.exists(index_path):
            return self._item("控制台", "WARN", "static/console/index.html 不存在，需构建前端")
        return self._item("控制台", "OK", "static/console 已就绪")

    def _users(self):
        from api.models import UserProfile

        total = UserProfile.objects.count()
        admins = UserProfile.objects.filter(is_admin=True).count()
        if total == 0:
            return self._item("账号", "WARN", "暂无用户，可通过 /console/ 初始化或 ensure_admin 创建")
        if admins == 0:
            return self._item("账号", "FAIL", "有用户但没有管理员，请用 ensure_admin 补建")
        return self._item("账号", "OK", "%d 个用户，其中 %d 个管理员" % (total, admins))
