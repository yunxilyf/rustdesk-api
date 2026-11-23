from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = "api"

    def ready(self):
        from . import (
            checks,  # noqa: F401  注册部署安全检查
            db_pragmas,  # noqa: F401  注册 SQLite WAL/busy_timeout
        )
