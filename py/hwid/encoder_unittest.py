#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common # pylint: disable=W0611
import os
import unittest

from cros.factory.hwid import Database
from cros.factory.hwid.encoder import BOMToBinaryString
from cros.factory.hwid.encoder import BinaryStringToEncodedString, Encode

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')


class EncoderTest(unittest.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(os.path.join(_TEST_DATA_PATH,
                                                   'test_db.yaml'))

  def testBOMToBinaryString(self):
    result = open(os.path.join(_TEST_DATA_PATH,
                               'test_probe_result.yaml'), 'r').read()
    bom = self.database.ProbeResultToBOM(result)
    self.assertEquals(
        '00000111010000010100', BOMToBinaryString(self.database, bom))

  def testBinaryStringToEncodedString(self):
    # TODO(jcliang): Change back in R27.
    #self.assertEquals('CHROMEBOOK A5AU-LU',
    self.assertEquals('CHROMEBOOK A5AU-LU 3324',
                      BinaryStringToEncodedString(
                          self.database, '00000111010000010100'))

  def testEncode(self):
    result = open(os.path.join(_TEST_DATA_PATH,
                               'test_probe_result.yaml'), 'r').read()
    bom = self.database.ProbeResultToBOM(result)
    hwid = Encode(self.database, bom)
    self.assertEquals('00000111010000010100', hwid.binary_string)
    # TODO(jcliang): Change back in R27.
    #self.assertEquals('CHROMEBOOK A5AU-LU', hwid.encoded_string)
    self.assertEquals('CHROMEBOOK A5AU-LU 3324', hwid.encoded_string)


if __name__ == '__main__':
  unittest.main()
