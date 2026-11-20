# -*- coding: utf-8 -*-
"""确保存在一个管理员账号（幂等）：部署与冒烟测试用。

python manage.py ensure_admin                      # 默认 admin / Admin@2026
python manage.py ensure_admin --username root --password 'S3cret!pass'
python manage.py ensure_admin --force              # 已有用户时也补建/提权
"""

import os

from django.core.management.base import BaseCommand

from api.models_user import UserProfile


class Command(BaseCommand):
    help = "确保系统里有一个管理员账号（默认 admin/Admin@2026，可用参数或环境变量覆盖）"

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.environ.get("SMOKE_ADMIN_USER", "admin"))
        parser.add_argument("--password", default=os.environ.get("SMOKE_ADMIN_PASSWORD", "Admin@2026"))
        parser.add_argument("--force", action="store_true", help="已有用户时也创建/提权该账号")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        force = options["force"]

        if UserProfile.objects.exists() and not force:
            self.stdout.write("已有用户，跳过 ensure_admin（--force 可强制）")
            return

        user = UserProfile.objects.filter(username=username).first()
        if user is None:
            user = UserProfile(username=username)
        user.is_admin = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS("管理员已就绪：%s" % username))
