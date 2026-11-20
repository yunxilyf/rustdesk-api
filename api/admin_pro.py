# cython:language_level=3
"""新版客户端接口（1.5.x）相关模型的后台管理注册。

旧版模型（RustDeskToken/Tag/Peer/RustDesDevice/ConnLog/FileLog）仍由
api/admin_user.py 注册；这里只补充多地址簿、设备分组、录像与切换授权。
"""

from django.contrib import admin
from django.utils.translation import gettext as _

from api.models_pro import (
    AddressBook,
    AddressBookPeer,
    AddressBookTag,
    DeviceGroup,
    DeviceGroupPeer,
    DeviceRecord,
    SwitchGrant,
    SystemSetting,
)


class AddressBookTagInline(admin.TabularInline):
    model = AddressBookTag
    extra = 1
    fields = ("name", "color")


class AddressBookPeerInline(admin.TabularInline):
    model = AddressBookPeer
    extra = 1
    fields = ("rid", "alias", "username", "hostname", "platform", "tags", "note")


class AddressBookAdmin(admin.ModelAdmin):
    list_display = ("guid", "name", "owner", "rule", "is_personal", "peer_count", "updated_at")
    list_filter = ("is_personal", "rule")
    search_fields = ("guid", "name", "owner__username")
    readonly_fields = ("guid", "created_at", "updated_at")
    inlines = (AddressBookTagInline, AddressBookPeerInline)
    fieldsets = (
        (_("基本信息"), {"fields": ("guid", "name", "owner", "note", "rule", "is_personal")}),
        (_("扩展"), {"fields": ("info", "created_at", "updated_at")}),
    )

    @admin.display(description=_("联系人"))
    def peer_count(self, obj):
        return obj.peers.count()


class DeviceGroupPeerInline(admin.TabularInline):
    model = DeviceGroupPeer
    extra = 1
    fields = ("rid",)


class DeviceGroupAdmin(admin.ModelAdmin):
    list_display = ("guid", "name", "owner", "member_count", "updated_at")
    search_fields = ("guid", "name", "owner__username")
    readonly_fields = ("guid", "created_at", "updated_at")
    inlines = (DeviceGroupPeerInline,)

    @admin.display(description=_("设备数"))
    def member_count(self, obj):
        return obj.members.count()


class DeviceRecordAdmin(admin.ModelAdmin):
    list_display = ("rid", "peer_id", "file", "size", "created_at")
    search_fields = ("rid", "peer_id", "file")
    list_filter = ("created_at",)
    readonly_fields = ("created_at",)


class SwitchGrantAdmin(admin.ModelAdmin):
    list_display = ("rid", "accepted", "created_at")
    search_fields = ("rid", "verifier")
    list_filter = ("accepted",)
    readonly_fields = ("created_at",)


admin.site.register(AddressBook, AddressBookAdmin)
admin.site.register(DeviceGroup, DeviceGroupAdmin)
admin.site.register(DeviceRecord, DeviceRecordAdmin)
admin.site.register(SwitchGrant, SwitchGrantAdmin)
admin.site.register(AddressBookTag)
admin.site.register(AddressBookPeer)
admin.site.register(DeviceGroupPeer)


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "updated_at")
    search_fields = ("key",)
