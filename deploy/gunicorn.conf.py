"""gunicorn 配置（Linux 生产环境）。

    gunicorn -c deploy/gunicorn.conf.py rustdesk_server_api.wsgi:application

心跳接口是 I/O 型短请求，用 gthread（多线程 worker）比纯同步进程更省内存；
worker 数按 CPU/2 起步，压测后再调。多 worker 时缓存必须配 Redis，
否则登录节流与部分缓存会各自为政。
"""

import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:21114")
workers = int(os.environ.get("GUNICORN_WORKERS", max(2, multiprocessing.cpu_count() // 2)))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"

timeout = 60
graceful_timeout = 30
keepalive = 5
max_requests = 5000
max_requests_jitter = 500

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
