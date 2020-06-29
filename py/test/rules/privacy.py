# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


# Keys that may not be logged (in VPDs or device data).

import copy


BLOCKLIST_KEYS = [
    'ubind_attribute',
    'gbind_attribute',
    'stable_device_secret_DO_NOT_SHARE',
]


def FilterDict(data):
  """Redacts values of any keys in BLOCKLIST_KEYS.

  If data is a list or a set, filter all its elements.
  If data is a dict and some keys in data match BLOCKLIST_KEYS,
  filter the values. For other values that is dict, set, or list,
  recursively filter them.
  If data is not a list nor a set nor a dict, just return data.

  Example: data = {'BLACK1': '1',
                   'WHITE1': {'BLACK2': 2}}
  FilterDict(data) = {'BLACK1': <redacted 1 chars>,
                      'WHITE1': {'BLACK2': <redacted type int>}
  Args:
    data: A data to redact.
  """
  ret = copy.deepcopy(data)
  if isinstance(data, (list, set)):
    ret = [FilterDict(x) for x in data]
  elif isinstance(data, dict):
    for k, v in ret.items():
      if v is None:
        continue
      if str(k) in BLOCKLIST_KEYS:
        if isinstance(v, str):
          ret[k] = '<redacted %d chars>' % len(v)
        else:
          ret[k] = '<redacted type %s>' % v.__class__.__name__
      elif isinstance(v, (dict, list, set)):
        ret[k] = FilterDict(v)
  return ret
