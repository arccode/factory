#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common # pylint: disable=W0611
import unittest

from cros.factory.hwid.base32 import Base32

class Base32Test(unittest.TestCase):
  def testEncode(self):
    self.assertEquals('A', Base32.Encode('00000'))
    self.assertEquals('7', Base32.Encode('11111'))
    self.assertEquals('FI', Base32.Encode('0010101'))

  def testDecode(self):
    self.assertEquals('00000', Base32.Decode('a'))
    self.assertEquals('0010101000', Base32.Decode('FI'))

  def testChecksum(self):
    self.assertEquals('5L', Base32.Checksum('FOO'))
    self.assertEquals('4C', Base32.Checksum('CHROMEBOOK ASDFQWERZXCV'))
    self.assertEquals('MP', Base32.Checksum('SOMETHING RANDOM'))

if __name__ == '__main__':
  unittest.main()
