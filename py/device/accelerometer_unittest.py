#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for accelerometer module."""

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import accelerometer


class AccelerometerTest(unittest.TestCase):
  # pylint: disable=protected-access

  def testScanType(self):
    scan_type = accelerometer._ParseIIOBufferScanType('le:s12/16>>4')
    self.assertEqual(scan_type.sign, 's')
    self.assertEqual(scan_type.realbits, 12)
    self.assertEqual(scan_type.storagebits, 16)
    self.assertEqual(scan_type.shift, 4)
    self.assertEqual(scan_type.repeat, None)
    self.assertEqual(scan_type.endianness, 'le')

  def testScanTypeWithRepeat(self):
    scan_type = accelerometer._ParseIIOBufferScanType('le:s12/16X2>>4')
    self.assertEqual(scan_type.sign, 's')
    self.assertEqual(scan_type.realbits, 12)
    self.assertEqual(scan_type.storagebits, 16)
    self.assertEqual(scan_type.shift, 4)
    self.assertEqual(scan_type.repeat, 2)
    self.assertEqual(scan_type.endianness, 'le')


if __name__ == '__main__':
  unittest.main()
