#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import binascii
import mock
import os
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import edid
from cros.factory.utils import sys_utils


class EdidTest(unittest.TestCase):

  @mock.patch.object(edid, '_I2CDump', return_value=None)
  def testLoadFromI2c(self, MockI2CDump):
    self.assertIsNone(edid.LoadFromI2C(0))
    self.assertIsNone(edid.LoadFromI2C('/dev/i2c-0'))
    MockI2CDump.assert_called_with(
        '/dev/i2c-0', edid.I2C_LVDS_ADDRESS, edid.MINIMAL_SIZE)

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


class EdidFunctionTest(unittest.TestCase):

  FAKE_DATA = 'FAKE_DATA'
  FAKE_OUTPUT = {'foo': 'FOO'}

  def setUp(self):
    self.tmp_fd, self.tmp_file = tempfile.mkstemp()
    with open(self.tmp_file, 'w') as f:
      f.write(self.FAKE_DATA)

  def tearDown(self):
    if os.path.isfile(self.tmp_file):
      os.close(self.tmp_fd)

  @mock.patch.object(edid, 'Parse', return_value=FAKE_OUTPUT)
  def testEDIDFile(self, MockParse):
    results = edid.EDIDFunction(path=self.tmp_file)()
    self.assertEquals(results, [self.FAKE_OUTPUT])
    MockParse.assert_called_with(self.FAKE_DATA)

  @mock.patch.object(edid, 'LoadFromI2C', return_value=FAKE_OUTPUT)
  @mock.patch.object(sys_utils, 'LoadKernelModule')
  def testI2CDeviceByNumber(self, MockLoadKernelModule, MockLoadFromI2C):
    results = edid.EDIDFunction(path='2')()
    self.assertEquals(results, [self.FAKE_OUTPUT])
    MockLoadKernelModule.assert_called_with('i2c_dev')
    MockLoadFromI2C.assert_called_with('/dev/i2c-2')

  @mock.patch.object(edid, 'LoadFromI2C', return_value=FAKE_OUTPUT)
  @mock.patch.object(sys_utils, 'LoadKernelModule')
  @mock.patch('glob.glob', return_value=['/dev/i2c-2'])
  def testI2CDeviceByPath(self, MockGlob, MockLoadKernelModule,
                          MockLoadFromI2C):
    results = edid.EDIDFunction(path='/dev/i2c-2')()
    self.assertEquals(results, [self.FAKE_OUTPUT])
    MockGlob.assert_called_with('/dev/i2c-2')
    MockLoadKernelModule.assert_called_with('i2c_dev')
    MockLoadFromI2C.assert_called_with('/dev/i2c-2')

if __name__ == '__main__':
  unittest.main()
