# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-03-31 16:13
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('glintwebui', '0013_auto_20170328_1247'),
    ]

    operations = [
        migrations.RenameField(
            model_name='project',
            old_name='project_name',
            new_name='account_name',
        ),
    ]