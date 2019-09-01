#!/usr/bin/env python2
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper for EDID data parsing and loading.

See for more info:
  http://en.wikipedia.org/wiki/Extended_display_identification_data
"""

import os
import sys

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v2 import hwid_tool
from cros.factory.probe.functions import edid


def CompactProbeStrDecorator(func):
  """Decorator which adds the legacy "COMPACT_STR" result."""
  def Wrap(content):
    ret = func(content)
    if ret is None:
      return None
    ret[hwid_tool.COMPACT_PROBE_STR] = (
        '%s:%s [%sx%s]' % (ret['vendor'], ret['product_id'],
                           ret['width'], ret['height']))
    return ret
  return Wrap

# Legacy functions.
Parse = CompactProbeStrDecorator(edid.Parse)
LoadFromI2c = CompactProbeStrDecorator(edid.LoadFromI2C)


if __name__ == '__main__':
  # For debugging, print parse result for specified i2c bus or raw file.
  if len(sys.argv) != 2:
    sys.exit('Usage: %s [i2c_bus_number | EDID_file]' % sys.argv[0])
  source = sys.argv[1]
  if os.path.exists(source):
    print repr(Parse(open(source).read()))
  else:
    print repr(LoadFromI2c(int(source)))
