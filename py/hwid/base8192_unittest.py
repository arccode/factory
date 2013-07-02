#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common # pylint: disable=W0611
import unittest

from cros.factory.hwid.base8192 import Base8192

class Base8192Test(unittest.TestCase):
  def testEncode(self):
    self.assertEquals('E', Base8192.Encode('001'))
    self.assertEquals('C', Base8192.Encode('0001'))
    self.assertEquals('A2AA', Base8192.Encode('000000'))
    self.assertEquals('76AA', Base8192.Encode('111111'))
    self.assertEquals('F4AA', Base8192.Encode('0010101'))
    self.assertEquals('F67D', Base8192.Encode('001011001111100011'))

  def testDecode(self):
    self.assertEquals('0010110011111', Base8192.Decode('f67'))
    self.assertEquals('0010000000000', Base8192.Decode('E2A'))
    self.assertRaisesRegexp(
        ValueError,
        r"Length of base8192 encoded string 'AA' is not multiple of 3",
        Base8192.Decode, 'AA')
    self.assertRaisesRegexp(
        KeyError, r"Encoded string should be of format: \(\[A-Z2-7\]\[2-9\]\["
        "A-Z2-7\]\)\+: 'FIB'", Base8192.Decode, 'FIB')

  def testChecksum(self):
    self.assertEquals('7L', Base8192.Checksum('FOO'))
    self.assertEquals('6C', Base8192.Checksum('CHROMEBOOK ASDFQWERZXCV'))
    self.assertEquals('6P', Base8192.Checksum('SOMETHING RANDOM'))

if __name__ == '__main__':
  unittest.main()

