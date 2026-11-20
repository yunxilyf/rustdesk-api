# -*- coding: utf-8 -*-
"""把历史标签颜色（调色板下标）转换成客户端可识别的 ARGB 整数。"""
from django.db import migrations

PALETTE = [
    0xFFF44336, 0xFF4CAF50, 0xFF2196F3, 0xFFFF9800,
    0xFF9C27B0, 0xFF9E9E9E, 0xFF00BCD4, 0xFFCDDC39,
    0xFF009688, 0xFFF48FB1, 0xFF3F51B5, 0xFF795548,
]


def forwards(apps, schema_editor):
    Tag = apps.get_model('api', 'AddressBookTag')
    for tag in Tag.objects.all().iterator():
        color = tag.color or 0
        if color >= 0x1000000:
            continue
        if 0 <= color < len(PALETTE):
            new = PALETTE[color]
        else:
            new = PALETTE[sum(ord(ch) for ch in (tag.name or '')) % len(PALETTE)]
        if new != color:
            Tag.objects.filter(pk=tag.pk).update(color=new)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_alter_addressbooktag_color'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
