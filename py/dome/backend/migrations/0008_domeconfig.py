# -*- coding: utf-8 -*-
# Generated by Django 1.10.1 on 2017-08-02 06:35
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
      ('backend', '0007_auto_20170411_0943'),
  ]

  operations = [
      migrations.CreateModel(
          name='DomeConfig',
          fields=[
              ('id', models.IntegerField(
                  default=0, primary_key=True, serialize=False)),
              ('tftp_enabled', models.BooleanField(default=False)),
          ],),
  ]
