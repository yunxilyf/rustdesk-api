"""RustDesk API Server 的根 URL 配置。

- /console/  管理控制台（TDesign 单页应用）
- /api/      RustDesk 客户端与控制台 JSON 接口
- /admin/    Django 管理后台
- /static/   静态资源（collectstatic 产物 + 控制台构建产物）
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from api.console_api import console_index
from api.views import index

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("admin/", admin.site.urls),
    path("", index),
    path("console/", console_index),
    path("api/", include("api.urls")),
    re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT}),
]
