# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2018-04-01 15:21
from __future__ import unicode_literals

from django.db import migrations


def remove_middle_gender(apps, schema_editor):
    apps.get_model("heroes", "Hero").objects.filter(gender=2).update(gender=0)


class Migration(migrations.Migration):

    dependencies = [
        ('heroes', '0022_auto_20180325_1656'),
    ]

    operations = [
        migrations.RunPython(
            remove_middle_gender,
        ),
    ]
