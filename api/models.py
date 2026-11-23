"""模型汇总入口：Django 只注册 api 一个 app，模型按用途分在三个模块里。"""

from .models_pro import (
    AddressBook,
    AddressBookPeer,
    AddressBookTag,
    DeviceGroup,
    DeviceGroupPeer,
    DeviceRecord,
    OidcLogin,
    SwitchGrant,
    SystemSetting,
)
from .models_user import MyUserManager, UserProfile
from .models_work import (
    ConnLog,
    ConnLogAdmin,
    FileLog,
    FileLogAdmin,
    RustDesDevice,
    RustDesDeviceAdmin,
    RustDeskPeer,
    RustDeskPeerAdmin,
    RustDeskTag,
    RustDeskTagAdmin,
    RustDeskToken,
    RustDeskTokenAdmin,
)

__all__ = [
    "AddressBook",
    "AddressBookPeer",
    "AddressBookTag",
    "ConnLog",
    "ConnLogAdmin",
    "DeviceGroup",
    "DeviceGroupPeer",
    "DeviceRecord",
    "FileLog",
    "FileLogAdmin",
    "MyUserManager",
    "OidcLogin",
    "RustDesDevice",
    "RustDesDeviceAdmin",
    "RustDeskPeer",
    "RustDeskPeerAdmin",
    "RustDeskTag",
    "RustDeskTagAdmin",
    "RustDeskToken",
    "RustDeskTokenAdmin",
    "SwitchGrant",
    "SystemSetting",
    "UserProfile",
]
