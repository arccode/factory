#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import binascii
import unittest

import mock

import factory_common  # pylint: disable=unused-import
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


class _FakeFunc(object):
  def __init__(self, results):
    self.results = results

  def __call__(self, *unused_args, **unused_kwargs):
    result, self.results = self.results[0], self.results[1:]
    return result


class EDIDFunctionTest(unittest.TestCase):
  FAKE_EDID = [
      {'vendor': 'IBM', 'product_id': '001', 'width': '111'},
      {'vendor': 'IBN', 'product_id': '002', 'width': '222'},
      {'vendor': 'IBO', 'product_id': '003', 'width': '333'},
  ]
  FAKE_PATHS = [['/sys/class/drm/A/edid', '/sys/class/drm/BB/edid'],
                ['/dev/i2c-1', '/dev/i2c-22']]
  FAKE_OUTPUTS = [
      dict(FAKE_EDID[0], sysfs_path='/sys/class/drm/A/edid'),
      dict(FAKE_EDID[1],
           sysfs_path='/sys/class/drm/BB/edid', dev_path='/dev/i2c-1'),
      dict(FAKE_EDID[2], dev_path='/dev/i2c-22')]

  @mock.patch('cros.factory.utils.sys_utils.LoadKernelModule')
  @mock.patch('cros.factory.probe.functions.edid.LoadFromFile',
              side_effect=_FakeFunc(FAKE_EDID[:2]))
  @mock.patch('cros.factory.probe.functions.edid.LoadFromI2C',
              side_effect=_FakeFunc(FAKE_EDID[1:]))
  @mock.patch('glob.glob', side_effect=_FakeFunc(FAKE_PATHS))
  def testNormal(self, *unused_mocks):
    result = edid.EDIDFunction()()
    self.assertItemsEqual(result, self.FAKE_OUTPUTS)

    for i in xrange(2):
      for j in xrange(2):
        result = edid.EDIDFunction(path=self.FAKE_PATHS[i][j])()
        self.assertItemsEqual(result, [self.FAKE_OUTPUTS[i + j]])

    result = edid.EDIDFunction(path='22')()
    self.assertItemsEqual(result, [self.FAKE_OUTPUTS[2]])


if __name__ == '__main__':
  unittest.main()
