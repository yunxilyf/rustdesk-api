from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0021_oauthprovider_useroauth"),
    ]

    operations = [
        migrations.AddField(
            model_name="oidclogin",
            name="flow",
            field=models.CharField(
                blank=True,
                choices=[("client", "客户端"), ("console", "控制台")],
                default="client",
                max_length=16,
                verbose_name="流程",
            ),
        ),
    ]
