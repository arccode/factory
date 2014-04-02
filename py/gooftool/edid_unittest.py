#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for edid.py"""


import binascii
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

  def testParser(self):
    # Public data from E-EDID spec,
    # http://read.pudn.com/downloads110/ebook/456020/E-EDID%20Standard.pdf
    edid_data = """
      00 FF FF FF FF FF FF 00 10 AC AB 50 00 00 00 00 2A 09 01 03 0E 26 1D 96 EF
      EE 91 A3 54 4C 99 26 0F 50 54 A5 43 00 A9 4F A9 59 71 59 61 59 45 59 31 59
      C2 8F 01 01 86 3D 00 C0 51 00 30 40 40 A0 13 00 7C 22 11 00 00 1E 00 00 00
      FF 00 35 35 33 34 37 42 4F 4E 5A 48 34 37 0A 00 00 00 FC 00 44 45 4C 4C 20
      55 52 31 31 31 0A 20 20 00 00 00 FD 00 30 A0 1E 79 1C 02 00 28 50 10 0E 80
      46 00 8D
      """
    edid_bin = binascii.unhexlify(''.join(edid_data.strip().split()))
    result = edid.Parse(edid_bin)
    self.assertEqual(result['width'], '1280')
    self.assertEqual(result['height'], '1024')
    self.assertEqual(result['vendor'], 'DEL')
    self.assertEqual(result['product_id'], '50ab')


if __name__ == '__main__':
  unittest.main()

