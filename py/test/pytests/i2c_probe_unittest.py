#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.pytests import i2c_probe

DEVICE_EXIST_CASES = [
""" 0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:            UU
10:                        """,
""" 0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:
10:                      UU""",
""" 0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:            12
10:                        """,
""" 0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:
10:                      34""",
""" 0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:       --     UU  --
10:     --                   """,
""" 0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:            -- -- -- --
10:                      UU""",]
DEVICE_NONEXIST_CASES = [
""" 0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:
10:                        """,
""" 0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:            --
10:                      """,
""" 0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:            xx
10:                        """,
""" 0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:         1 2 U U   -- -- -- --
10:                      """,]


class I2CProbeUnitTest(unittest.TestCase):
  def testIsDeviceExist(self):
    prober = i2c_probe.I2CProbeTest()
    for c in DEVICE_EXIST_CASES:
      self.assertTrue(prober.DeviceExists(c))
    for c in DEVICE_NONEXIST_CASES:
      self.assertFalse(prober.DeviceExists(c))


if __name__ == '__main__':
  unittest.main()

