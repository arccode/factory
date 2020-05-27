#!/usr/bin/env python3
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import binascii
import copy
import unittest

import mock

from cros.factory.probe.functions import edid


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


class EDIDFunctionTest(unittest.TestCase):
  FAKE_EDID = [
      {'vendor': 'IBM', 'product_id': '001', 'width': '111'},
      {'vendor': 'IBN', 'product_id': '002', 'width': '222'},
  ]
  FAKE_SYSFS_PATHS = ['/sys/class/drm/A/edid', '/sys/class/drm/BB/edid']
  FAKE_SYSFS_OUTPUTS = [
      dict(FAKE_EDID[0], sysfs_path=FAKE_SYSFS_PATHS[0]),
      dict(FAKE_EDID[1], sysfs_path=FAKE_SYSFS_PATHS[1])]
  FAKE_I2C_PATHS = ['/dev/i2c-1', '/dev/i2c-22']
  FAKE_I2C_OUTPUTS = [
      dict(FAKE_EDID[0], dev_path=FAKE_I2C_PATHS[0]),
      dict(FAKE_EDID[1], dev_path=FAKE_I2C_PATHS[1])]

  def InitEDIDFunction(self):
    edid.EDIDFunction.path_to_identity = None
    edid.EDIDFunction.identity_to_edid = None

  @mock.patch('cros.factory.utils.sys_utils.LoadKernelModule')
  @mock.patch('cros.factory.probe.functions.edid.LoadFromFile',
              side_effect=copy.deepcopy(FAKE_EDID))
  @mock.patch('cros.factory.probe.functions.edid.LoadFromI2C',
              side_effect=copy.deepcopy(FAKE_EDID))
  @mock.patch('glob.glob',
              side_effect=[FAKE_SYSFS_PATHS, FAKE_I2C_PATHS])
  def testSysfs(self, *unused_mocks):
    self.InitEDIDFunction()
    result = edid.EDIDFunction()()
    self.assertCountEqual(result, self.FAKE_SYSFS_OUTPUTS)

    for i in range(2):
      result = edid.EDIDFunction(path=self.FAKE_SYSFS_PATHS[i])()
      self.assertCountEqual(result, [self.FAKE_SYSFS_OUTPUTS[i]])

  @mock.patch('cros.factory.utils.sys_utils.LoadKernelModule')
  @mock.patch('cros.factory.probe.functions.edid.LoadFromFile',
              side_effect=[None, None])
  @mock.patch('cros.factory.probe.functions.edid.LoadFromI2C',
              side_effect=copy.deepcopy(FAKE_EDID))
  @mock.patch('glob.glob',
              side_effect=[FAKE_SYSFS_PATHS, FAKE_I2C_PATHS])
  def testI2C(self, *unused_mocks):
    self.InitEDIDFunction()
    result = edid.EDIDFunction()()
    self.assertCountEqual(result, self.FAKE_I2C_OUTPUTS)

    for i in range(2):
      result = edid.EDIDFunction(path=self.FAKE_I2C_PATHS[i])()
      self.assertCountEqual(result, [self.FAKE_I2C_OUTPUTS[i]])

    result = edid.EDIDFunction(path='22')()
    self.assertCountEqual(result, [self.FAKE_I2C_OUTPUTS[1]])


if __name__ == '__main__':
  unittest.main()
