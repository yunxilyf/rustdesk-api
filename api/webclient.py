"""网页远控（Web 客户端）的会话鉴权与静态兜底。

访问 /web/、/web/rd-config.js、/ws/id、/ws/relay 均直接校验控制台 Django Session，
不再依赖全局共享的静态 Cookie：
- Docker 部署：内置 nginx 通过 auth_request 调用 /api/webclient/auth 逐请求校验；
- 免安装/裸机部署：Django 直接在 webclient_file 中校验会话并提供静态文件；
- 登录共享：/web/rd-config.js 为当前控制台会话签发/复用绑定该会话的 RustDesk Bearer
  令牌与用户信息，Web 客户端打开即可自动登录，退出控制台或禁用账号时自动吊销。
"""

import hashlib

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.views.static import serve as static_serve

from api import client_auth
from api.models import RustDeskToken

WEB_TOKEN_UUID = "web-session"


def _active_console_user(request):
    """返回已登录且处于启用状态的控制台用户，否则返回 None。"""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_active:
        return None
    return user


def _web_token_rid(session_key: str) -> str:
    """将 Django session_key 映射为 16 位 web 令牌标识（不与数字设备 ID 冲突）。"""
    return "w" + hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:15]


def ensure_web_token(request, user):
    """为当前控制台会话签发或复用独立的 RustDesk 客户端令牌。"""
    if not request.session.session_key:
        request.session.save()
    rid = _web_token_rid(request.session.session_key)
    return client_auth.issue_token(user, rid, WEB_TOKEN_UUID)


def revoke_web_token(request, user=None) -> None:
    """控制台退出登录时吊销当前会话对应的 Web 端令牌（需在 auth.logout 清空 session 前调用）。"""
    session = getattr(request, "session", None)
    session_key = getattr(session, "session_key", None)
    target = user or getattr(request, "user", None)
    uid = getattr(target, "pk", None)
    if not session_key or not uid:
        return
    RustDeskToken.objects.filter(uid=str(uid), rid=_web_token_rid(session_key)).delete()


def is_current_session_web_token(request, token) -> bool:
    """判断客户端登出的令牌是否属于当前浏览器控制台会话的 Web 端令牌。"""
    user = _active_console_user(request)
    if user is None or token is None:
        return False
    if token.uuid != WEB_TOKEN_UUID or str(token.uid) != str(user.pk):
        return False
    session_key = getattr(getattr(request, "session", None), "session_key", None)
    if not session_key:
        return False
    return token.rid == _web_token_rid(session_key)


def webclient_auth(request):
    """供 nginx auth_request 与前端登录态探测使用：有效会话返回 204，否则返回 401。"""
    if request.method not in ("GET", "HEAD"):
        return HttpResponse(status=405)
    user = _active_console_user(request)
    if user is None:
        resp = HttpResponse(status=401)
        resp["Cache-Control"] = "no-store"
        return resp
    resp = HttpResponse(status=204)
    resp["Cache-Control"] = "no-store"
    session_key = getattr(getattr(request, "session", None), "session_key", None)
    if session_key:
        resp["X-Webclient-Session"] = _web_token_rid(session_key)
    return resp


def webclient_login(request):
    """兼容旧入口 /web-login：已登录跳 /web/，未登录跳控制台登录页。"""
    if _active_console_user(request) is None:
        return HttpResponseRedirect("/console/?next=/web/")
    resp = HttpResponseRedirect("/web/")
    # 清理旧版本遗留的静态 rdweb Cookie（现在统一走 Django Session）
    if "rdweb" in request.COOKIES:
        clear_webclient_cookie(resp)
    return resp


def clear_webclient_cookie(response):
    """清理旧版本可能遗留在浏览器中的 rdweb Cookie。"""
    response.delete_cookie("rdweb", path="/")
    return response


def webclient_file(request, path: str):
    """独立运行（无 nginx）时直接校验控制台会话并提供 /web/ 下的静态文件。

    Docker 部署由内置 nginx + auth_request 接管 /web/，不会走到这里；
    Windows/Linux 免安装包没有 nginx，由 Django 兜底。
    """
    if _active_console_user(request) is None:
        return HttpResponseRedirect("/console/?next=/web/")
    if path in ("", "/"):
        path = "index.html"
    resp = static_serve(request, path, document_root=str(getattr(settings, "WEBCLIENT_ROOT", "")))
    resp["Cache-Control"] = "no-store"
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Referrer-Policy"] = "same-origin"
    return resp
