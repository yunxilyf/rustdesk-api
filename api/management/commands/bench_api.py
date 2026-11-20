# -*- coding: utf-8 -*-
"""对运行中的 API 服务做一次快速压测（读路径 vs 心跳写路径）。

用法：
    # 先启动服务，例如
    #   python manage.py runserver 127.0.0.1:21114 --noreload
    python manage.py bench_api --threads 16 --seconds 8

脚本会创建临时用户/设备/token，压测结束后删除（--keep 可保留）。
"""

import http.client
import json
import secrets
import statistics
import threading
import time
import urllib.parse

from django.core.management.base import BaseCommand, CommandError

from api.models_user import UserProfile
from api.models_work import RustDesDevice, RustDeskToken


class Command(BaseCommand):
    help = "压测 /api/currentUser（读）与 /api/heartbeat（写），输出吞吐与延迟"
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--base", default="http://127.0.0.1:21114", help="服务地址")
        parser.add_argument("--threads", type=int, default=16)
        parser.add_argument("--seconds", type=float, default=8.0)
        parser.add_argument("--keep", action="store_true", help="保留压测用的临时账号")

    def handle(self, *args, **options):
        base = options["base"].rstrip("/")
        parsed = urllib.parse.urlparse(base)
        if not parsed.hostname:
            raise CommandError("--base 需要形如 http://127.0.0.1:21114")
        host, port = parsed.hostname, parsed.port or 80

        suffix = str(int(time.time()))[-6:]
        username = "bench" + suffix
        user = UserProfile.objects.create_user(username=username, password=secrets.token_urlsafe(12))
        user.is_active = True
        user.save()
        rid, uuid = "bench-" + suffix, "bench-uuid-" + suffix
        RustDesDevice.objects.create(
            rid=rid, uuid=uuid, hostname="BENCH", cpu="bench", memory="16G", os="Windows", version="1.5.3"
        )
        token_value = secrets.token_hex(16)
        RustDeskToken.objects.create(username=username, uid=str(user.id), rid=rid, uuid=uuid, access_token=token_value)

        body = json.dumps({"id": rid, "uuid": uuid, "ver": "1.5.3"})
        try:
            self._run(
                "currentUser (read)",
                host,
                port,
                "/api/currentUser",
                body,
                {"Content-Type": "application/json", "Authorization": "Bearer " + token_value},
                options["threads"],
                options["seconds"],
            )
            self._run(
                "heartbeat (no-write steady state)",
                host,
                port,
                "/api/heartbeat",
                body,
                {"Content-Type": "application/json"},
                options["threads"],
                options["seconds"],
            )
        finally:
            if not options["keep"]:
                RustDeskToken.objects.filter(access_token=token_value).delete()
                RustDesDevice.objects.filter(rid=rid).delete()
                user.delete()

    def _run(self, name, host, port, path, body, headers, threads, seconds):
        stats = []
        stop = threading.Event()

        def worker():
            conn = http.client.HTTPConnection(host, port, timeout=20)
            local = []
            while not stop.is_set():
                start = time.perf_counter()
                try:
                    conn.request("POST", path, body=body, headers=headers)
                    response = conn.getresponse()
                    response.read()
                    local.append((time.perf_counter() - start, response.status))
                except Exception as exc:  # noqa: BLE001
                    local.append((time.perf_counter() - start, type(exc).__name__))
                    conn.close()
                    conn = http.client.HTTPConnection(host, port, timeout=20)
            stats.append(local)

        workers = [threading.Thread(target=worker) for _ in range(threads)]
        for t in workers:
            t.start()
        time.sleep(seconds)
        stop.set()
        for t in workers:
            t.join()

        flat = [item for chunk in stats for item in chunk]
        codes = {}
        for _, code in flat:
            codes[code] = codes.get(code, 0) + 1
        latencies = sorted(d for d, code in flat if isinstance(code, int)) or [0.0]
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
        self.stdout.write(
            "%s: %6.1f req/s  n=%d  p50=%.1fms  p95=%.1fms  codes=%s"
            % (name, len(flat) / seconds, len(flat), statistics.median(latencies) * 1000, p95 * 1000, codes)
        )
