# -*- coding: utf-8 -*-
"""在部署时创建初始管理员。"""

import getpass
import os
import secrets
import sys

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models_user import UserProfile
from api.models_work import RustDeskToken


class Command(BaseCommand):
    help = "创建初始管理员：交互时输入密码；非交互时生成随机密码并打印一次"

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.environ.get("SMOKE_ADMIN_USER", "admin"))
        parser.add_argument("--password", default=os.environ.get("SMOKE_ADMIN_PASSWORD"))
        parser.add_argument("--noinput", "--no-input", action="store_false", dest="interactive")
        parser.add_argument("--force", action="store_true", help="已有用户时也创建/提权该账号")

    @transaction.atomic
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
        generated = False
        if not password:
            if options["interactive"] and sys.stdin and sys.stdin.isatty():
                password = getpass.getpass("管理员密码: ")
            else:
                # 非交互部署（Docker/CI）不能卡在输入上，也不能写死公开默认密码：
                # 生成一个随机初始密码并打印一次，部署者据此登录后立即修改。
                password = secrets.token_urlsafe(12)
                generated = True
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc

        user.is_admin = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()
        RustDeskToken.objects.filter(uid=user.pk).delete()
        if generated:
            self.stdout.write(
                self.style.SUCCESS(
                    "管理员已创建：%s\n初始密码：%s\n（仅本次显示，请登录后立即修改；也可用 --password 或 SMOKE_ADMIN_PASSWORD 指定）"
                    % (username, password)
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("管理员已就绪：%s" % username))
