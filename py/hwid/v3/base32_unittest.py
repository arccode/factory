#!/usr/bin/env python3
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

from cros.factory.hwid.v3.base32 import Base32


class Base32Test(unittest.TestCase):

  def testGetPaddingLength(self):
    self.assertEqual(0, Base32.GetPaddingLength(0))
    self.assertEqual(0, Base32.GetPaddingLength(5))
    self.assertEqual(1, Base32.GetPaddingLength(4))
    self.assertEqual(2, Base32.GetPaddingLength(3))

  def testEncode(self):
    self.assertEqual('A', Base32.Encode('00000'))
    self.assertEqual('7', Base32.Encode('11111'))
    self.assertEqual('FI', Base32.Encode('0010101000'))

  def testDecode(self):
    self.assertEqual('00000', Base32.Decode('a'))
    self.assertEqual('0010101000', Base32.Decode('FI'))

  def testChecksum(self):
    self.assertEqual('5L', Base32.Checksum('FOO'))
    self.assertEqual('4C', Base32.Checksum('CHROMEBOOK ASDFQWERZXCV'))
    self.assertEqual('MP', Base32.Checksum('SOMETHING RANDOM'))

if __name__ == '__main__':
  unittest.main()
