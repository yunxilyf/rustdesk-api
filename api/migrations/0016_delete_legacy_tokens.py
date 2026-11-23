from django.db import migrations


def delete_legacy_tokens(apps, schema_editor):
    """Drop predictable 32-character md5 tokens issued by older versions."""
    RustDeskToken = apps.get_model("api", "RustDeskToken")
    legacy_ids = [row.pk for row in RustDeskToken.objects.only("pk", "access_token") if len(row.access_token or "") != 43]
    if legacy_ids:
        RustDeskToken.objects.filter(pk__in=legacy_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0015_rustdesktoken_expires_at"),
    ]

    operations = [
        migrations.RunPython(delete_legacy_tokens, migrations.RunPython.noop),
    ]
