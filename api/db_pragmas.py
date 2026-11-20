"""SQLite 连接级 PRAGMA：WAL + busy_timeout。

默认的 rollback journal 模式下，读写互斥，多个客户端同时心跳会频繁
`database is locked`。WAL 允许「多读 + 单写」并发，配合 busy_timeout
可以把偶发写冲突变成短暂等待，是单机 SQLite 部署的关键开关。

对 MySQL/Postgres 连接不做任何处理。
"""

from django.db.backends.signals import connection_created
from django.dispatch import receiver


@receiver(connection_created)
def _sqlite_pragmas(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        # 内存库会返回 memory，不影响测试
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=20000")
