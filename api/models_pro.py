# -*- coding: utf-8 -*-
"""RustDesk 新版客户端（1.5.x）数据模型。

与旧版 models_work.py / models_user.py 分开放：这里承载多地址簿、设备分组、
设备录像与切换授权等新接口所需的数据；models.py 会 `from .models_pro import *`
把它挂到 app 上。
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class AddressBook(models.Model):
    """一个地址簿（个人地址簿 / 共享地址簿）。"""

    guid = models.CharField(_("地址簿 GUID"), max_length=64, unique=True)
    owner = models.ForeignKey(
        "UserProfile",
        verbose_name=_("所有者"),
        on_delete=models.CASCADE,
        related_name="address_books",
        null=True,
        blank=True,
    )
    name = models.CharField(_("名称"), max_length=64, default="")
    note = models.CharField(_("备注"), max_length=200, blank=True, default="")
    # 客户端原样保存的 info 字段（JSON 字符串）
    info = models.TextField(_("扩展信息"), blank=True, default="")
    # 共享规则；0 = 仅自己
    rule = models.SmallIntegerField(_("共享规则"), default=0)
    is_personal = models.BooleanField(_("是否个人地址簿"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("地址簿")
        verbose_name_plural = _("地址簿列表")
        ordering = ["id"]

    def __str__(self):
        return "%s(%s)" % (self.name or self.guid, self.guid)


class AddressBookTag(models.Model):
    ab = models.ForeignKey(AddressBook, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(_("标签名"), max_length=64)
    color = models.BigIntegerField(_("颜色"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("地址簿标签")
        verbose_name_plural = _("地址簿标签")
        unique_together = (("ab", "name"),)
        ordering = ["id"]

    def save(self, *args, **kwargs):
        # 颜色统一存 ARGB（客户端 Color.value），避免后台/脚本写入调色板下标
        from .tag_colors import normalize_color

        self.color = normalize_color(self.color, self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class AddressBookPeer(models.Model):
    ab = models.ForeignKey(AddressBook, on_delete=models.CASCADE, related_name="peers")
    rid = models.CharField(_("RustDesk ID"), max_length=64, db_index=True)
    rhash = models.CharField(_("hash"), max_length=128, blank=True, default="")
    password = models.CharField(_("密码"), max_length=128, blank=True, default="")
    username = models.CharField(_("用户名"), max_length=64, blank=True, default="")
    hostname = models.CharField(_("主机名"), max_length=128, blank=True, default="")
    platform = models.CharField(_("平台"), max_length=64, blank=True, default="")
    alias = models.CharField(_("别名"), max_length=128, blank=True, default="")
    login_name = models.CharField(_("登录名"), max_length=64, blank=True, default="")
    # 逗号分隔的标签名
    tags = models.TextField(_("标签"), blank=True, default="")
    note = models.CharField(_("备注"), max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("地址簿设备")
        verbose_name_plural = _("地址簿设备")
        unique_together = (("ab", "rid"),)
        ordering = ["id"]

    def __str__(self):
        return "%s/%s" % (self.ab_id, self.rid)


class DeviceGroup(models.Model):
    """设备分组（用户可访问的分组）。"""

    guid = models.CharField(_("分组 GUID"), max_length=64, unique=True)
    owner = models.ForeignKey(
        "UserProfile",
        verbose_name=_("所有者"),
        on_delete=models.CASCADE,
        related_name="device_groups",
        null=True,
        blank=True,
    )
    name = models.CharField(_("名称"), max_length=64, default="")
    note = models.CharField(_("备注"), max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("设备分组")
        verbose_name_plural = _("设备分组")
        ordering = ["id"]

    def __str__(self):
        return self.name or self.guid


class DeviceGroupPeer(models.Model):
    group = models.ForeignKey(DeviceGroup, on_delete=models.CASCADE, related_name="members")
    rid = models.CharField(_("RustDesk ID"), max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("分组设备")
        verbose_name_plural = _("分组设备")
        unique_together = (("group", "rid"),)
        ordering = ["id"]


class DeviceRecord(models.Model):
    """历史录像记录，供 Django 管理后台访问。"""

    rid = models.CharField(_("RustDesk ID"), max_length=64, db_index=True)
    peer_id = models.CharField(_("对端 ID"), max_length=64, blank=True, default="")
    file = models.CharField(_("文件名"), max_length=255, blank=True, default="")
    path = models.CharField(_("路径"), max_length=512, blank=True, default="")
    size = models.BigIntegerField(_("大小"), default=0)
    note = models.CharField(_("备注"), max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("会话录像")
        verbose_name_plural = _("会话录像")
        ordering = ["-id"]


class SwitchGrant(models.Model):
    """设备切换授权（switch code）记录。"""

    rid = models.CharField(_("RustDesk ID"), max_length=64, db_index=True)
    verifier = models.CharField(_("校验值"), max_length=128, blank=True, default="")
    timestamp = models.CharField(_("时间戳"), max_length=32, blank=True, default="")
    signature = models.TextField(_("签名"), blank=True, default="")
    accepted = models.BooleanField(_("是否接受"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("切换授权")
        verbose_name_plural = _("切换授权")
        ordering = ["-id"]


class SystemSetting(models.Model):
    """运行时可改的系统设置（键值对）。"""

    key = models.CharField(_("键"), max_length=64, unique=True)
    value = models.CharField(_("值"), max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(_("更新时间"), auto_now=True)

    class Meta:
        verbose_name = _("系统设置")
        verbose_name_plural = _("系统设置")
        ordering = ["key"]

    def __str__(self):
        return self.key


class OidcLogin(models.Model):
    """一次 OIDC 登录请求的临时状态（客户端轮询取回 token，控制台则建立会话）。"""

    FLOW_CLIENT = "client"
    FLOW_CONSOLE = "console"
    FLOW_CHOICES = ((FLOW_CLIENT, _("客户端")), (FLOW_CONSOLE, _("控制台")))

    state = models.CharField(_("状态"), max_length=64, unique=True)
    flow = models.CharField(_("流程"), max_length=16, blank=True, default=FLOW_CLIENT, choices=FLOW_CHOICES)
    rid = models.CharField(_("RustDesk ID"), max_length=100, blank=True, default="")
    uuid = models.CharField(_("设备 UUID"), max_length=100, blank=True, default="")
    api_domain = models.CharField(_("API 域名"), max_length=255, blank=True, default="")
    op = models.CharField(_("登录选项"), max_length=64, blank=True, default="")
    code_verifier = models.CharField(_("PKCE 校验值"), max_length=128, blank=True, default="")
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    completed_at = models.DateTimeField(_("完成时间"), null=True, blank=True)
    access_token = models.CharField(_("访问令牌"), max_length=64, blank=True, default="")
    user = models.ForeignKey(
        "UserProfile",
        verbose_name=_("用户"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="oidc_logins",
    )

    class Meta:
        verbose_name = _("OIDC 登录")
        verbose_name_plural = _("OIDC 登录")
        ordering = ["-id"]


class OauthProvider(models.Model):
    """第三方登录提供方（可配置多个，客户端按列表渲染按钮）。

    oauth_type 决定认证方式：
    - github：OAuth2（无 discovery / id_token，用户信息取 api.github.com）
    - google：标准 OIDC，issuer 固定 https://accounts.google.com
    - oidc：任意兼容 OIDC 的 IdP（Keycloak / Authentik / Entra ID 等）
    """

    TYPES = ("github", "google", "oidc")

    op = models.CharField(_("标识"), max_length=32, unique=True)
    name = models.CharField(_("显示名称"), max_length=64, blank=True, default="")
    oauth_type = models.CharField(_("类型"), max_length=16, default="oidc")
    client_id = models.CharField(_("客户端 ID"), max_length=255, blank=True, default="")
    client_secret = models.CharField(_("客户端密钥"), max_length=255, blank=True, default="")
    issuer = models.CharField(_("Issuer"), max_length=255, blank=True, default="")
    scopes = models.CharField(_("Scope"), max_length=255, blank=True, default="")
    auto_register = models.BooleanField(_("自动注册"), default=True)
    pkce_enable = models.BooleanField(_("启用 PKCE"), default=True)
    sort = models.IntegerField(_("排序"), default=0)
    enabled = models.BooleanField(_("启用"), default=True)
    updated_at = models.DateTimeField(_("更新时间"), auto_now=True)

    class Meta:
        verbose_name = _("第三方登录")
        verbose_name_plural = _("第三方登录")
        ordering = ["sort", "id"]

    def __str__(self):
        return self.op

    def label(self):
        return (self.name or self.op).strip()


class UserOauth(models.Model):
    """第三方身份与本地账号的绑定关系（一个账号可绑定多个 provider）。"""

    user = models.ForeignKey(
        "UserProfile",
        verbose_name=_("用户"),
        on_delete=models.CASCADE,
        related_name="oauth_links",
    )
    op = models.CharField(_("登录方式"), max_length=32)
    openid = models.CharField(_("第三方主体"), max_length=191)
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)

    class Meta:
        verbose_name = _("第三方账号绑定")
        verbose_name_plural = _("第三方账号绑定")
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["op", "openid"], name="uniq_user_oauth_op_openid"),
        ]
        indexes = [models.Index(fields=["user", "op"], name="idx_user_oauth_user_op")]

    def __str__(self):
        return "{}:{}".format(self.op, self.openid)
