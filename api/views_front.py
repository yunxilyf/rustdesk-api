"""客户端令牌工具与旧版注册 / 退出兼容入口。

- ``getStrMd5`` / ``salt`` / ``EFFECTIVE_SECONDS``：客户端登录令牌签名；
- ``user_action``：自助注册、退出两个 POST 动作（GET 一律跳转控制台）。
"""

import hashlib

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.hashers import make_password
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.translation import gettext as _

from api.models import UserProfile

salt = "xiaomo"
EFFECTIVE_SECONDS = 7200


def getStrMd5(s):
    if not isinstance(s, (str,)):
        s = str(s)

    myHash = hashlib.md5()
    myHash.update(s.encode())

    return myHash.hexdigest()


def index(request):
    # 新控制台是唯一入口；登录态由 /console/ 自己判断。
    return HttpResponseRedirect("/console/")


def legacy_redirect(request):
    """旧地址兼容：一律 302 到新控制台。"""
    return HttpResponseRedirect("/console/")


def user_action(request):
    """仅保留注册/退出两个 POST 动作；页面型 GET 全部跳新控制台。"""
    if request.method != "POST":
        return HttpResponseRedirect("/console/")
    action = request.GET.get("action", "")
    if action == "register":
        return user_register(request)
    if action == "logout":
        return user_logout(request)
    if action == "login":
        return JsonResponse(
            {"code": 0, "msg": _("旧版登录页已下线，请使用 /console/ 登录。")},
            status=410,
        )
    return JsonResponse({"code": 0, "msg": "unknown action"}, status=400)


def user_register(request):
    from .settings_store import allow_registration

    result = {"code": 0, "msg": ""}
    if request.method != "POST":
        return HttpResponseRedirect("/console/")

    if not allow_registration():
        result["msg"] = _("当前未开放注册，请联系管理员！")
        return JsonResponse(result)

    username = request.POST.get("user", "")
    password1 = request.POST.get("pwd", "")

    if len(username) <= 3:
        result["msg"] = _("用户名不得小于3位")
        return JsonResponse(result)

    if len(password1) < 8 or len(password1) > 20:
        result["msg"] = _("密码长度不符合要求, 应在8~20位。")
        return JsonResponse(result)

    if getattr(settings, "PASSWORD_VALIDATION", True):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        try:
            validate_password(password1)
        except ValidationError as exc:
            result["msg"] = " ".join(exc.messages)
            return JsonResponse(result)

    if UserProfile.objects.filter(Q(username=username)).exists():
        result["msg"] = _("用户名已存在。")
        return JsonResponse(result)

    first = not UserProfile.objects.exists()
    UserProfile.objects.create(
        username=username,
        password=make_password(password1),
        is_admin=first,
        is_superuser=first,
        is_active=True,
    )
    result["code"] = 1
    return JsonResponse(result)


def user_logout(request):
    auth.logout(request)
    return JsonResponse({"code": 1, "msg": "ok"})
