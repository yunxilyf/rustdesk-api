from django.db import migrations


def normalize_personal_books(apps, schema_editor):
    """每个账号只保留最早的一条个人地址簿，其余转成共享簿（rule=2）。

    历史版本里 preset-address-book-name / devices CLI 会错误地创建
    is_personal=True 的地址簿。客户端只会把一个个人簿当作「我的地址簿」，
    共享列表又排除个人簿，导致那些簿在客户端不可见。
    """
    AddressBook = apps.get_model("api", "AddressBook")
    owner_ids = (
        AddressBook.objects.filter(is_personal=True)
        .values_list("owner_id", flat=True)
        .distinct()
    )
    for owner_id in owner_ids:
        books = list(AddressBook.objects.filter(owner_id=owner_id, is_personal=True).order_by("id"))
        for extra in books[1:]:
            extra.is_personal = False
            if extra.rule < 2:
                extra.rule = 2
            extra.save(update_fields=["is_personal", "rule"])


class Migration(migrations.Migration):
    dependencies = [("api", "0018_rustdesdevice_pending_at_rustdesdevice_pending_uuid")]
    operations = [migrations.RunPython(normalize_personal_books, migrations.RunPython.noop)]
