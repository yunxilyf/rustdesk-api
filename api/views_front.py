"""旧版注册、退出入口及控制台跳转。"""

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.hashers import make_password
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.translation import gettext as _

from api import throttle
from api.models import UserProfile


def index(request):
    # 新控制台是唯一入口；登录态由 /console/ 自己判断。
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
    if not UserProfile.objects.exists():
        result["msg"] = _("系统尚未初始化，请先创建管理员。")
        return JsonResponse(result)
    if throttle.too_many("register", request, settings.REGISTER_MAX_PER_HOUR, 3600):
        result["msg"] = _("注册过于频繁，请稍后再试")
        return JsonResponse(result, status=429)
    throttle.hit("register", request, 3600)

    username = request.POST.get("user", "")
    password1 = request.POST.get("pwd", "")

    if not 3 <= len(username) <= 50:
        result["msg"] = _("用户名长度需在 3~50 位之间")
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

    if UserProfile.objects.filter(username=username).exists():
        result["msg"] = _("用户名已存在。")
        return JsonResponse(result)

    UserProfile.objects.create(
        username=username,
        password=make_password(password1),
        is_active=True,
    )
    result["code"] = 1
    return JsonResponse(result)


def user_logout(request):
    auth.logout(request)
    return JsonResponse({"code": 1, "msg": "ok"})
