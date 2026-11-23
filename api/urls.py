from django.urls import re_path as url
from django.views.decorators.csrf import csrf_exempt

from api import console_api, views, views_pro, webclient


def client(view):
    """RustDesk 客户端/旧版页面走的接口：无 Cookie 会话，按 token/dev 约定鉴权。

    这些接口不能要求 CSRF token（客户端不会带），因此显式豁免；
    控制台 `/api/console/*` 走浏览器 Session，必须保留 CSRF 校验。
    """
    return csrf_exempt(view)


urlpatterns = [
    # ================= 新版客户端 API（精确匹配，必须放在前缀路由之前） =================
    url(r"^health/?$", client(views_pro.health)),
    url(r"^webclient/auth/?$", client(webclient.webclient_auth)),
    url(r"^webclient/config\.js$", client(views_pro.webclient_config)),
    url(r"^login-options/?$", client(views_pro.login_options)),
    url(r"^oidc/auth-query/?$", client(views_pro.oidc_auth_query)),
    url(r"^oidc/console/auth/?$", client(views_pro.console_oauth_start)),
    url(r"^oidc/auth/?$", client(views_pro.oidc_auth)),
    url(r"^oidc/callback/?$", client(views_pro.oidc_callback)),
    url(r"^login/?$", client(views.login)),
    url(r"^logout/?$", client(views.logout)),
    url(r"^currentUser/?$", client(views.currentUser)),
    # ---- 多地址簿（新版 Ab 协议）----
    url(r"^ab/personal/?$", client(views_pro.ab_personal)),
    url(r"^ab/settings/?$", client(views_pro.ab_settings)),
    url(r"^ab/shared/profiles/?$", client(views_pro.ab_shared_profiles)),
    url(r"^ab/peers/?$", client(views_pro.ab_peers)),
    url(r"^ab/peer/add/(?P<guid>[0-9a-zA-Z]+)/?$", client(views_pro.ab_peer_add)),
    url(r"^ab/peer/update/(?P<guid>[0-9a-zA-Z]+)/?$", client(views_pro.ab_peer_update)),
    url(r"^ab/peer/(?P<guid>[0-9a-zA-Z]+)/?$", client(views_pro.ab_peer_delete)),
    url(r"^ab/tags/(?P<guid>[0-9a-zA-Z]+)/?$", client(views_pro.ab_tags)),
    url(r"^ab/tag/add/(?P<guid>[0-9a-zA-Z]+)/?$", client(views_pro.ab_tag_add)),
    url(r"^ab/tag/rename/(?P<guid>[0-9a-zA-Z]+)/?$", client(views_pro.ab_tag_rename)),
    url(r"^ab/tag/update/(?P<guid>[0-9a-zA-Z]+)/?$", client(views_pro.ab_tag_update)),
    url(r"^ab/tag/(?P<guid>[0-9a-zA-Z]+)/?$", client(views_pro.ab_tag_delete)),
    # ---- 旧版单地址簿（仅供 1.4.x 及更早客户端，新版客户端不会再调用）----
    url(r"^ab/get/?$", client(views.ab_get)),
    url(r"^ab/?$", client(views.ab)),
    url(r"^users/?$", client(views_pro.users)),
    url(r"^peers/online/?$", client(views_pro.peers_online)),
    url(r"^peers/?$", client(views_pro.peers)),
    url(r"^device-group/accessible/?$", client(views_pro.device_groups)),
    url(r"^sysinfo_ver/?$", client(views.sysinfo_ver)),
    url(r"^sysinfo/?$", client(views.sysinfo)),
    url(r"^heartbeat/?$", client(views.heartbeat)),
    url(r"^audit/conn/active/?$", client(views_pro.audit_active)),
    url(r"^audit/(?P<kind>conn|file|alarm)/?$", client(views.audit)),
    url(r"^audit/?$", client(views.audit_note)),
    url(r"^switch-grant/?$", client(views_pro.switch_grant)),
    url(r"^record/?$", client(views_pro.record_upload)),
    url(r"^devices/cli/?$", client(views_pro.devices_cli)),
    url(r"^devices/deploy/?$", client(views_pro.devices_deploy)),
    # ================= 控制台（TDesign 前端）JSON API（Session + CSRF） =================
    url(r"^console/setup/?$", console_api.setup),
    url(r"^console/register/?$", console_api.register),
    url(r"^console/login-options/?$", console_api.console_login_options),
    url(r"^console/login/?$", console_api.console_login),
    url(r"^console/logout/?$", console_api.console_logout),
    url(r"^console/me/password/?$", console_api.console_password),
    url(r"^console/me/?$", console_api.console_me),
    url(r"^console/stats/?$", console_api.stats),
    url(r"^console/settings/?$", console_api.console_settings),
    url(r"^console/version/?$", console_api.console_version),
    url(r"^console/users/?$", console_api.users),
    url(r"^console/users/(?P<uid>\d+)/?$", console_api.user_detail),
    url(r"^console/devices/?$", console_api.devices),
    url(r"^console/devices/(?P<rid>[^/]+)/owner/?$", console_api.device_owner),
    url(r"^console/addressbooks/?$", console_api.addressbooks),
    url(r"^console/addressbooks/(?P<guid>[0-9a-zA-Z]+)/?$", console_api.addressbook_detail),
    url(r"^console/addressbooks/(?P<guid>[0-9a-zA-Z]+)/peers/?$", console_api.ab_peers),
    url(r"^console/addressbooks/(?P<guid>[0-9a-zA-Z]+)/peers/(?P<rid>[^/]+)/?$", console_api.ab_peer_detail),
    url(r"^console/addressbooks/(?P<guid>[0-9a-zA-Z]+)/tags/?$", console_api.ab_tags),
    url(r"^console/addressbooks/(?P<guid>[0-9a-zA-Z]+)/tags/(?P<name>[^/]+)/?$", console_api.ab_tag_detail),
    url(r"^console/groups/?$", console_api.groups),
    url(r"^console/groups/(?P<guid>[0-9a-zA-Z]+)/?$", console_api.group_detail),
    url(r"^console/groups/(?P<guid>[0-9a-zA-Z]+)/members/?$", console_api.group_members),
    url(r"^console/logs/conn/?$", console_api.conn_logs),
    url(r"^console/logs/file/?$", console_api.file_logs),
    # 旧版注册/退出兼容入口；GET 请求统一 302 到控制台。
    # 客户端不携带 CSRF token，与其他客户端接口一致豁免；注册是否开放由运行时开关决定。
    url(r"^user_action/?$", client(views.user_action)),
]
