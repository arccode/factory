# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.db import models


class Event(models.Model):
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
  # No primary_key for the Attr table for speed-up. Duplication check is
  # done using the Event table.
  event_id = models.TextField()
  attr     = models.TextField()
  value    = models.TextField()


class Test(models.Model):
  invocation     = models.TextField(primary_key=True)
  event_id       = models.TextField()
  device_id      = models.TextField()
  factory_md5sum = models.TextField()
  image_id       = models.TextField()
  path           = models.TextField()
  pytest_name    = models.TextField()
  status         = models.TextField()
  start_time     = models.TextField()
  end_time       = models.TextField()
  duration       = models.FloatField()
  dargs          = models.TextField()


class Device(models.Model):
  device_id        = models.TextField(primary_key=True)
  goofy_init_time  = models.TextField()
  serial           = models.TextField()
  mlb_serial       = models.TextField()
  hwid             = models.TextField()
  ips              = models.TextField()
  ips_time         = models.TextField()
  latest_test      = models.TextField()
  latest_test_time = models.TextField()
  minijack_status  = models.TextField()


class Component(models.Model):
  device_id = models.TextField(primary_key=True)
  component = models.TextField(primary_key=True)
  symbolic  = models.TextField()
