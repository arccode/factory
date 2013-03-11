#!/usr/bin/python
# pylint: disable=W0212
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


# Keys that may not be logged (in VPDs or device data).
BLACKLIST_KEYS = [
  'ubind_attribute',
  'gbind_attribute'
]


def FilterDict(data):
  """Redacts values of any keys in BLACKLIST_KEYS.

  Args:
    data: A dictionary to redact.
  """
  def FilterItem(k, v):
    if v is None:
      return None
    return '<redacted %d chars>' % len(v) if k in BLACKLIST_KEYS else v

  return dict((k, FilterItem(k, v)) for k, v in data.iteritems())
