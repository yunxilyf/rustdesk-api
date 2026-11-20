# -*- coding: utf-8 -*-
"""生产部署安全自检（Django checks）。

运行 `python manage.py check` 会看到 W 级警告；`python manage.py check --deploy`
会把它们当作部署问题提示。不影响开发环境（DEBUG=True 时不提示）。
"""

from django.conf import settings
from django.core.checks import Warning, register

DEFAULT_SECRET = "j%7yjvygpih=6b%qf!q%&ixpn+27dngzdu-i3xh-^3xgy3^nnc"


@register()
def production_secrets_check(app_configs, **kwargs):
    """仅在 `manage.py check --deploy` 时检查生产安全项。"""
    issues = []
    if not kwargs.get("deploy", False):
        return issues

    if getattr(settings, "SECRET_KEY", "") == DEFAULT_SECRET:
        issues.append(
            Warning(
                "SECRET_KEY 仍是仓库内的默认值，生产环境请通过环境变量 SECRET_KEY 覆盖。",
                id="api.W001",
                hint="export SECRET_KEY=\"$(python -c 'import secrets;print(secrets.token_urlsafe(50))')\"",
            )
        )

    hosts = list(getattr(settings, "ALLOWED_HOSTS", []))
    if "*" in hosts:
        issues.append(
            Warning(
                'ALLOWED_HOSTS 包含 "*"，生产环境应填写实际域名/IP。',
                id="api.W002",
                hint='export ALLOWED_HOSTS="rd.example.com,10.0.0.10"',
            )
        )
    return issues
