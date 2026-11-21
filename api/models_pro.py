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
    """设备录像上传记录（协议保留：/api/record）。

    1.5.x 客户端不会主动上传录像，控制台也已移除该入口；
    保留模型是为了协议与历史数据兼容。
    """

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
