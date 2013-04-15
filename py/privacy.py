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

  Recursively filters value in data as well if value is a dict.
  Example: data = {'BLACK1': 1,
                   'WHITE1': {'BLACK2': 2}}
  FilterDict(data) = {'BLACK1': <redacted 1 chars>,
                      'WHITE1': {'BLACK2': <redacted 1 chars>}
  Args:
    data: A dictionary to redact.
  """
  ret = dict(data)
  for k, v in ret.iteritems():
    if v is None:
      continue
    if k in BLACKLIST_KEYS:
      if isinstance(v, str):
        ret[k] = '<redacted %d chars>' % len(v)
      else:
        ret[k] = '<redacted type %s>' % v.__class__.__name__
    elif isinstance(v, dict):
      ret[k] = FilterDict(v)
  return ret
