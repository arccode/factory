# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.minijack import db

class Event(db.Model):
  device_id      = db.TextField(primary_key=True)
  # We store time in TEXT as sqlite3 does not support milliseconds.
  # Without milliseconds, we can't use time as key when joinning tables.
  time           = db.TextField(primary_key=True)
  preamble_time  = db.TextField()
  event          = db.TextField()
  event_seq      = db.IntegerField()
  preamble_seq   = db.IntegerField()
  boot_id        = db.TextField()
  boot_sequence  = db.IntegerField()
  factory_md5sum = db.TextField()
  filename       = db.TextField()
  image_id       = db.TextField()
  log_id         = db.TextField()

class Attr(db.Model):
  # No primary_key for the Attr table for speed-up. Duplication check is
  # done using the Event table.
  device_id = db.TextField()
  time      = db.TextField()
  attr      = db.TextField()
  value     = db.TextField()

class Test(db.Model):
  invocation     = db.TextField(primary_key=True)
  device_id      = db.TextField()
  factory_md5sum = db.TextField()
  image_id       = db.TextField()
  path           = db.TextField()
  pytest_name    = db.TextField()
  status         = db.TextField()
  start_time     = db.TextField()
  end_time       = db.TextField()
  duration       = db.RealField()
  dargs          = db.TextField()

class Device(db.Model):
  device_id       = db.TextField(primary_key=True)
  goofy_init_time = db.TextField()
  serial          = db.TextField()
  serial_time     = db.TextField()
  mlb_serial      = db.TextField()
  mlb_serial_time = db.TextField()
  hwid            = db.TextField()
  hwid_time       = db.TextField()
  ip              = db.TextField()

class Component(db.Model):
  device_id = db.TextField(primary_key=True)
  time      = db.TextField(primary_key=True)
  component = db.TextField(primary_key=True)
  symbolic  = db.TextField()
