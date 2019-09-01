#!/usr/bin/env python2
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.base32 import Base32


class Base32Test(unittest.TestCase):

  def testGetPaddingLength(self):
    self.assertEquals(0, Base32.GetPaddingLength(0))
    self.assertEquals(0, Base32.GetPaddingLength(5))
    self.assertEquals(1, Base32.GetPaddingLength(4))
    self.assertEquals(2, Base32.GetPaddingLength(3))

  def testEncode(self):
    self.assertEquals('A', Base32.Encode('00000'))
    self.assertEquals('7', Base32.Encode('11111'))
    self.assertEquals('FI', Base32.Encode('0010101000'))

  def testDecode(self):
    self.assertEquals('00000', Base32.Decode('a'))
    self.assertEquals('0010101000', Base32.Decode('FI'))

  def testChecksum(self):
    self.assertEquals('5L', Base32.Checksum('FOO'))
    self.assertEquals('4C', Base32.Checksum('CHROMEBOOK ASDFQWERZXCV'))
    self.assertEquals('MP', Base32.Checksum('SOMETHING RANDOM'))

if __name__ == '__main__':
  unittest.main()
