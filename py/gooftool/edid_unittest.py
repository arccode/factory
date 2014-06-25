#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for edid.py"""


import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.gooftool import edid

class EdidTest(unittest.TestCase):
  """Unittest for edid.py"""

  def setUp(self):
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(edid, '_I2cDump')

  def tearDown(self):
    self.mox.UnsetStubs()

  def testLoadFromI2c(self):
    # pylint: disable=W0212
    edid._I2cDump('/dev/i2c-0', edid.I2C_LVDS_ADDRESS,
                  edid.MINIMAL_SIZE).AndReturn(None)
    edid._I2cDump('/dev/i2c-0', edid.I2C_LVDS_ADDRESS,
                  edid.MINIMAL_SIZE).AndReturn(None)
    self.mox.ReplayAll()

    self.assertIsNone(edid.LoadFromI2c(0))
    self.assertIsNone(edid.LoadFromI2c('/dev/i2c-0'))
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()

