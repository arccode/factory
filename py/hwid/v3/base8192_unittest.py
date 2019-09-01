#!/usr/bin/env python2
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.base8192 import Base8192


class Base8192Test(unittest.TestCase):

  def testGetPaddingLength(self):
    self.assertEquals(5, Base8192.GetPaddingLength(0))
    self.assertEquals(5, Base8192.GetPaddingLength(13))
    self.assertEquals(0, Base8192.GetPaddingLength(5))
    self.assertEquals(0, Base8192.GetPaddingLength(18))
    self.assertEquals(1, Base8192.GetPaddingLength(4))
    self.assertEquals(1, Base8192.GetPaddingLength(17))
    self.assertEquals(2, Base8192.GetPaddingLength(3))

  def testEncode(self):
    self.assertEquals('E', Base8192.Encode('00100'))
    self.assertEquals('C', Base8192.Encode('00010'))
    self.assertEquals('A2AA', Base8192.Encode('000000000000000000'))
    self.assertEquals('76AA', Base8192.Encode('111111000000000000'))
    self.assertEquals('F4AA', Base8192.Encode('001010100000000000'))
    self.assertEquals('F67D', Base8192.Encode('001011001111100011'))

  def testDecode(self):
    self.assertEquals('001011001111100000', Base8192.Decode('F67A'))
    self.assertEquals('001000000000000000', Base8192.Decode('E2AA'))

  def testChecksum(self):
    self.assertEquals('7L', Base8192.Checksum('FOO'))
    self.assertEquals('6C', Base8192.Checksum('CHROMEBOOK ASDFQWERZXCV'))
    self.assertEquals('6P', Base8192.Checksum('SOMETHING RANDOM'))

if __name__ == '__main__':
  unittest.main()
