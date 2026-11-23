# -*- coding: utf-8 -*-
"""项目特有的 Django 部署检查。"""

from django.conf import settings
from django.core.checks import Warning, register


@register(deploy=True)
def production_settings_check(app_configs, **kwargs):
    issues = []
    if "*" in settings.ALLOWED_HOSTS:
        issues.append(
            Warning(
                'ALLOWED_HOSTS 包含 "*"，生产环境应填写实际域名/IP。',
                id="api.W002",
                hint='export ALLOWED_HOSTS="rd.example.com,10.0.0.10"',
            )
        )
    if settings.WEB_SETUP_TOKEN:
        issues.append(Warning("网页初始化密钥已配置，完成初始化后请清除 WEB_SETUP_TOKEN。", id="api.W003"))
    return issues
