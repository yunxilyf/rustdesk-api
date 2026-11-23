# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：生成 Linux / Windows 单文件可执行程序。"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH 由 PyInstaller 注入

import sys  # noqa: E402

sys.path.insert(0, str(ROOT))

hiddenimports = sorted(
    set(
        collect_submodules("api")
        + collect_submodules("rustdesk_server_api")
        + collect_submodules("django")
        + [
            "waitress",
            "rustdesk_server_api.settings",
            "rustdesk_server_api.urls",
            "rustdesk_server_api.wsgi",
            "api.apps",
            "api.urls",
            "api.views",
            "api.views_api",
            "api.views_pro",
            "api.views_front",
            "api.console_api",
            "api.models",
            "api.models_user",
            "api.models_work",
            "api.models_pro",
            "api.admin",
            "api.admin_user",
            "api.admin_pro",
            "api.client_auth",
            "api.throttle",
            "api.tag_colors",
            "api.settings_store",
            "api.db_pragmas",
            "api.checks",
            "django.contrib.admin",
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sessions",
            "django.contrib.messages",
            "django.contrib.staticfiles",
        ]
    )
)

datas = [
    (str(ROOT / "static"), "static"),
    (str(ROOT / "api" / "templates"), "api/templates"),
    (str(ROOT / ".env.example"), "."),
    (str(ROOT / "deploy" / "web"), "deploy/web"),
]

a = Analysis(  # noqa: F821
    [str(ROOT / "deploy" / "standalone.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "PyQt5", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="rustdesk-api-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="rustdesk-api-server",
)
