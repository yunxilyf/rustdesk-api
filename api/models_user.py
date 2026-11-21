from django.db import models
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser, PermissionsMixin
from .models_work import *
from django.utils.translation import gettext as _


class MyUserManager(BaseUserManager):
    def create_user(self, username, password=None):
        if not username:
            raise ValueError("Users must have an username")

        user = self.model(
            username=username,
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password):
        user = self.create_user(
            username,
            password=password,
        )
        user.is_admin = True
        user.save(using=self._db)
        return user


class UserProfile(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(_("用户名"), unique=True, max_length=50)

    rid = models.CharField(verbose_name="RustDesk ID", max_length=16)
    uuid = models.CharField(verbose_name="uuid", max_length=60)
    autoLogin = models.BooleanField(verbose_name="autoLogin", default=True)
    rtype = models.CharField(verbose_name="rtype", max_length=20)
    deviceInfo = models.TextField(verbose_name=_("登录信息:"), blank=True)

    # 以下字段是 RustDesk 客户端 UserPayload 会读取的可选字段，
    # 旧版本没有，补上后 login / currentUser 才能返回完整用户信息。
    display_name = models.CharField(verbose_name=_("显示名"), max_length=64, blank=True, default="")
    email = models.EmailField(verbose_name=_("邮箱"), max_length=128, blank=True, default="")
    note = models.CharField(verbose_name=_("备注"), max_length=200, blank=True, default="")
    avatar = models.CharField(verbose_name=_("头像"), max_length=255, blank=True, default="")
    verifier = models.CharField(verbose_name=_("验证标识"), max_length=64, blank=True, default="")
    status = models.SmallIntegerField(verbose_name=_("状态"), default=1)

    is_active = models.BooleanField(verbose_name=_("是否激活"), default=True)
    is_admin = models.BooleanField(verbose_name=_("是否管理员"), default=False)

    objects = MyUserManager()

    USERNAME_FIELD = "username"  # 用作用户名的字段
    REQUIRED_FIELDS = ["password"]  # 必须填写的字段

    def get_full_name(self):
        # The user is identified by their email address
        return self.username

    def get_short_name(self):
        # The user is identified by their email address
        return self.username

    def __str__(self):  # __unicode__ on Python 2
        return self.username

    def has_perm(self, perm, obj=None):  # 有没有指定的权限
        "Does the user have a specific permission?"
        # Simplest possible answer: Yes, always
        return True

    def has_module_perms(self, app_label):
        "Does the user have permissions to view the app `app_label`?"
        # Simplest possible answer: Yes, always
        return True

    @property
    def is_staff(self):
        "Is the user a member of staff?"
        # Simplest possible answer: All admins are staff
        return self.is_admin

    class Meta:
        verbose_name = _("用户")
        verbose_name_plural = _("用户列表")
        permissions = (
            ("view_task", "Can see available tasks"),
            ("change_task_status", "Can change the status of tasks"),
            ("close_task", "Can remove a task by setting its status as closed"),
        )
