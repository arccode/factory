#!/usr/bin/env python3
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

from cros.factory.hwid.v3.base8192 import Base8192


class Base8192Test(unittest.TestCase):

  def testGetPaddingLength(self):
    self.assertEqual(5, Base8192.GetPaddingLength(0))
    self.assertEqual(5, Base8192.GetPaddingLength(13))
    self.assertEqual(0, Base8192.GetPaddingLength(5))
    self.assertEqual(0, Base8192.GetPaddingLength(18))
    self.assertEqual(1, Base8192.GetPaddingLength(4))
    self.assertEqual(1, Base8192.GetPaddingLength(17))
    self.assertEqual(2, Base8192.GetPaddingLength(3))

  def testEncode(self):
    self.assertEqual('E', Base8192.Encode('00100'))
    self.assertEqual('C', Base8192.Encode('00010'))
    self.assertEqual('A2AA', Base8192.Encode('000000000000000000'))
    self.assertEqual('76AA', Base8192.Encode('111111000000000000'))
    self.assertEqual('F4AA', Base8192.Encode('001010100000000000'))
    self.assertEqual('F67D', Base8192.Encode('001011001111100011'))

  def testDecode(self):
    self.assertEqual('001011001111100000', Base8192.Decode('F67A'))
    self.assertEqual('001000000000000000', Base8192.Decode('e2aa'))

  def testChecksum(self):
    self.assertEqual('7L', Base8192.Checksum('FOO'))
    self.assertEqual('6C', Base8192.Checksum('CHROMEBOOK ASDFQWERZXCV'))
    self.assertEqual('6P', Base8192.Checksum('SOMETHING RANDOM'))

if __name__ == '__main__':
  unittest.main()
