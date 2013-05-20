# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from django.db import models


class _NotManagedMeta(object):
  """A class to keep the table name and not managed tag."""
  def __init__(self, db_table):
    self.db_table = db_table
    # Make the table not managed by Django.
    self.managed = False


class _NotManagedModelBase(models.base.ModelBase):
  """A metaclass to create model classes, which not managed by Django."""
  def __new__(mcs, name, bases, attrs):
    super_new = super(_NotManagedModelBase, mcs).__new__
    # Make the table name same as the class name, i.e. Minijack convention.
    attrs['Meta'] = _NotManagedMeta(name)
    return super_new(mcs, name, bases, attrs)


# TODO(waihong): Make the model definitions in a single place.

# The following model definitions should be the same as Minijack, i.e.
#   cros.factory.minijack.models

class Event(models.Model):
  __metaclass__ = _NotManagedModelBase

  event_id       = models.TextField(primary_key=True)
  device_id      = models.TextField()
  time           = models.TextField()
  event          = models.TextField()
  seq            = models.IntegerField()
  log_id         = models.TextField()
  prefix         = models.TextField()
  boot_id        = models.TextField()
  boot_sequence  = models.IntegerField()
  factory_md5sum = models.TextField()
  image_id       = models.TextField()


class Attr(models.Model):
  __metaclass__ = _NotManagedModelBase

  # Django needs the primary key for the table. Otherwise, it causes errors.
  event_id = models.TextField(primary_key=True)
  attr     = models.TextField(primary_key=True)
  value    = models.TextField()


class Test(models.Model):
  __metaclass__ = _NotManagedModelBase

  invocation     = models.TextField(primary_key=True)
  event_id       = models.TextField()
  event_seq      = models.IntegerField()
  device_id      = models.TextField()
  factory_md5sum = models.TextField()
  image_id       = models.TextField()
  path           = models.TextField()
  pytest_name    = models.TextField()
  status         = models.TextField()
  start_time     = models.TextField()
  end_time       = models.TextField()
  duration       = models.FloatField()


class Device(models.Model):
  __metaclass__ = _NotManagedModelBase

  device_id           = models.TextField(primary_key=True)
  goofy_init_time     = models.TextField()
  serial              = models.TextField()
  mlb_serial          = models.TextField()
  hwid                = models.TextField()
  ips                 = models.TextField()
  ips_time            = models.TextField()
  latest_test         = models.TextField()
  latest_test_time    = models.TextField()
  latest_ended_test   = models.TextField()
  latest_ended_status = models.TextField()
  count_passed        = models.IntegerField()
  count_failed        = models.IntegerField()
  minijack_status     = models.TextField()
  latest_note_level   = models.TextField()
  latest_note_name    = models.TextField()
  latest_note_text    = models.TextField()
  latest_note_time    = models.TextField()


class Component(models.Model):
  __metaclass__ = _NotManagedModelBase

  device_id = models.TextField(primary_key=True)
  component = models.TextField(primary_key=True)
  symbolic  = models.TextField()
