import datetime

from django.contrib import admin, messages
from django.db import models, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext as _


class RustDeskToken(models.Model):
    """Token"""

    username = models.CharField(verbose_name=_("用户名"), max_length=20)
    rid = models.CharField(verbose_name=_("RustDesk ID"), max_length=16)
    uid = models.CharField(verbose_name=_("用户ID"), max_length=16)
    uuid = models.CharField(verbose_name=_("uuid"), max_length=60)
    access_token = models.CharField(verbose_name=_("access_token"), max_length=60, blank=True, db_index=True)
    create_time = models.DateTimeField(verbose_name=_("登录时间"), auto_now_add=True)
    expires_at = models.DateTimeField(verbose_name=_("过期时间"), null=True, blank=True, db_index=True)

    class Meta:
        ordering = ("-username",)
        verbose_name = "Token"
        verbose_name_plural = _("Token列表")
        indexes = [
            models.Index(fields=["rid", "uuid"], name="idx_token_rid_uuid"),
        ]


class RustDeskTokenAdmin(admin.ModelAdmin):
    list_display = ("username", "uid", "create_time", "expires_at")
    search_fields = ("username", "uid")
    list_filter = ("create_time", "expires_at")


class RustDeskTag(models.Model):
    """Tags"""

    uid = models.CharField(verbose_name=_("所属用户ID"), max_length=16)
    tag_name = models.CharField(verbose_name=_("标签名称"), max_length=60)
    tag_color = models.CharField(verbose_name=_("标签颜色"), max_length=60, blank=True)

    class Meta:
        ordering = ("-uid",)
        verbose_name = "Tags"
        verbose_name_plural = _("Tags列表")


class RustDeskTagAdmin(admin.ModelAdmin):
    list_display = ("tag_name", "uid", "tag_color")
    search_fields = ("tag_name", "uid")
    list_filter = ("uid",)


class RustDeskPeer(models.Model):
    """Pees"""

    uid = models.CharField(verbose_name=_("用户ID"), max_length=16, db_index=True)
    rid = models.CharField(verbose_name=_("客户端ID"), max_length=60, db_index=True)
    username = models.CharField(verbose_name=_("系统用户名"), max_length=20)
    hostname = models.CharField(verbose_name=_("操作系统名"), max_length=30)
    alias = models.CharField(verbose_name=_("别名"), max_length=30)
    platform = models.CharField(verbose_name=_("平台"), max_length=30)
    tags = models.CharField(verbose_name=_("标签"), max_length=30)
    rhash = models.CharField(verbose_name=_("设备链接密码"), max_length=60)

    class Meta:
        ordering = ("-username",)
        verbose_name = "Peers"
        verbose_name_plural = _("Peers列表")


class RustDeskPeerAdmin(admin.ModelAdmin):
    list_display = ("rid", "uid", "username", "hostname", "platform", "alias", "tags")
    search_fields = ("deviceid", "alias")
    list_filter = (
        "rid",
        "uid",
    )


class RustDesDevice(models.Model):
    rid = models.CharField(verbose_name=_("客户端ID"), max_length=60, blank=True, db_index=True)
    cpu = models.CharField(verbose_name="CPU", max_length=100)
    hostname = models.CharField(verbose_name=_("主机名"), max_length=100)
    memory = models.CharField(verbose_name=_("内存"), max_length=100)
    os = models.CharField(verbose_name=_("操作系统"), max_length=100)
    uuid = models.CharField(verbose_name="uuid", max_length=100)
    username = models.CharField(verbose_name=_("系统用户名"), max_length=100, blank=True)
    version = models.CharField(verbose_name=_("客户端版本"), max_length=100)
    create_time = models.DateTimeField(verbose_name=_("设备注册时间"), auto_now_add=True)
    update_time = models.DateTimeField(verbose_name=("设备更新时间"), auto_now=True, blank=True)
    reregister_until = models.DateTimeField(verbose_name=_("允许重新登记截止"), null=True, blank=True)
    pending_uuid = models.CharField(verbose_name=_("待确认的新 uuid"), max_length=100, blank=True)
    pending_at = models.DateTimeField(verbose_name=_("待确认时间"), null=True, blank=True)

    class Meta:
        ordering = ("-rid",)
        verbose_name = _("设备")
        verbose_name_plural = _("设备列表")
        indexes = [
            models.Index(fields=["rid", "uuid"], name="idx_device_rid_uuid"),
        ]


def approve_pending_uuid(device_id, expected_uuid):
    """确认管理员在页面上核对过的候选 uuid；候选变化、窗口过期或无候选都返回 False。"""
    expected = str(expected_uuid or "")
    if not expected:
        return False
    with transaction.atomic():
        row = RustDesDevice.objects.select_for_update().filter(pk=device_id).first()
        if row is None or not row.pending_uuid or row.pending_uuid != expected:
            return False
        if row.reregister_until is None or row.reregister_until < timezone.now():
            return False
        row.uuid = expected
        row.pending_uuid = ""
        row.pending_at = None
        row.reregister_until = None
        row.save(update_fields=["uuid", "pending_uuid", "pending_at", "reregister_until"])
        return True


class RustDesDeviceAdmin(admin.ModelAdmin):
    list_display = (
        "rid",
        "hostname",
        "memory",
        "uuid",
        "pending_uuid",
        "reregister_confirm",
        "version",
        "update_time",
        "reregister_until",
    )
    search_fields = ("hostname", "memory")
    list_filter = ("rid",)
    actions = ("allow_reregister",)

    @admin.action(description=_("允许所选设备重新登记（10 分钟）"))
    def allow_reregister(self, request, queryset):
        """设备重装会换 uuid，客户端后台上报不带令牌，这里开一个短期窗口接收新身份。"""
        until = timezone.now() + datetime.timedelta(minutes=10)
        updated = queryset.update(reregister_until=until, pending_uuid="", pending_at=None)
        self.message_user(request, _("已允许 %(count)d 台设备在 10 分钟内重新登记。") % {"count": updated})

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/confirm-reregister/",
                self.admin_site.admin_view(self.confirm_reregister_view),
                name="api_rustdesdevice_confirm_reregister",
            )
        ]
        return custom + urls

    @admin.display(description=_("待确认身份"))
    def reregister_confirm(self, obj):
        if not obj.pending_uuid:
            return "-"
        url = reverse("admin:api_rustdesdevice_confirm_reregister", args=[obj.pk])
        return format_html('<a class="button" href="{}">{}</a>', url, _("核对并确认…"))

    def confirm_reregister_view(self, request, object_id):
        """确认页展示候选 uuid，并在提交时校验候选未被替换。"""
        device = get_object_or_404(RustDesDevice, pk=object_id)
        changelist = reverse("admin:api_rustdesdevice_changelist")
        if request.method == "POST":
            expected = request.POST.get("pending_uuid", "")
            if approve_pending_uuid(device.pk, expected):
                self.message_user(request, _("已确认设备 %(rid)s 的新身份。") % {"rid": device.rid})
                return redirect(changelist)
            self.message_user(
                request,
                _("候选身份已变化或窗口已失效，请刷新后重新核对。"),
                level=messages.ERROR,
            )
            return redirect(request.path)
        if not device.pending_uuid:
            self.message_user(request, _("该设备没有待确认的新身份。"), level=messages.WARNING)
            return redirect(changelist)
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "device": device,
            "title": _("确认设备新身份"),
        }
        return render(request, "admin/api/rustdesdevice/confirm_reregister.html", context)


class ConnLog(models.Model):
    id = models.AutoField(verbose_name="ID", primary_key=True)
    action = models.CharField(verbose_name="Action", max_length=20, null=True)
    conn_id = models.CharField(verbose_name="Connection ID", max_length=10, null=True)
    from_ip = models.CharField(verbose_name="From IP", max_length=30, null=True)
    from_id = models.CharField(verbose_name="From ID", max_length=20, null=True)
    rid = models.CharField(verbose_name="To ID", max_length=20, null=True)
    conn_start = models.DateTimeField(verbose_name="Connected", null=True)
    conn_end = models.DateTimeField(verbose_name="Disconnected", null=True)
    session_id = models.CharField(verbose_name="Session ID", max_length=60, null=True)
    uuid = models.CharField(verbose_name="uuid", max_length=60, null=True)
    note = models.CharField(verbose_name="备注", max_length=500, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["rid", "conn_start"], name="idx_conn_rid_start"),
            models.Index(fields=["conn_start"], name="idx_conn_start"),
        ]


class ConnLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "action",
        "conn_id",
        "from_ip",
        "from_id",
        "rid",
        "conn_start",
        "conn_end",
        "session_id",
        "uuid",
    )
    search_fields = ("from_ip", "rid")
    list_filter = ("id", "from_ip", "from_id", "rid", "conn_start", "conn_end")


class FileLog(models.Model):
    id = models.AutoField(verbose_name="ID", primary_key=True)
    file = models.CharField(verbose_name="Path", max_length=500)
    remote_id = models.CharField(verbose_name="Remote ID", max_length=20, default="0")
    user_id = models.CharField(verbose_name="User ID", max_length=20, default="0")
    user_ip = models.CharField(verbose_name="User IP", max_length=20, default="0")
    filesize = models.CharField(verbose_name="Filesize", max_length=500, default="")
    direction = models.IntegerField(verbose_name="Direction", default=0)
    logged_at = models.DateTimeField(verbose_name="Logged At", null=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["user_id", "logged_at"], name="idx_file_user_time"),
        ]


class FileLogAdmin(admin.ModelAdmin):
    list_display = ("id", "file", "remote_id", "user_id", "user_ip", "filesize", "direction", "logged_at")
    search_fields = ("file", "remote_id", "user_id", "user_ip")
    list_filter = ("id", "file", "remote_id", "user_id", "user_ip", "filesize", "direction", "logged_at")
