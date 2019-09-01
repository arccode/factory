#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import tempfile
import textwrap
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import i2c


class I2CFunctionTest(unittest.TestCase):
  def setUp(self):
    # Mock the sysfs structure.
    self.sysfs_i2c_dir = tempfile.mkdtemp()
    os.mkdir(os.path.join(self.sysfs_i2c_dir, 'i2c-0'))
    os.mkdir(os.path.join(self.sysfs_i2c_dir, 'i2c-1'))
    with open(os.path.join(self.sysfs_i2c_dir, 'i2c-0', 'name'), 'w') as f:
      f.write('I2C-0 NAME')
    with open(os.path.join(self.sysfs_i2c_dir, 'i2c-1', 'name'), 'w') as f:
      f.write('I2C-1 NAME')

    self.patchers = []
    self.patchers.append(mock.patch.object(i2c, 'SYSFS_I2C_DIR_PATH',
                                           self.sysfs_i2c_dir))
    def MockRealPath(path):
      return os.path.join('/FAKE_PATH', os.path.basename(path))
    self.patchers.append(mock.patch('os.path.realpath', MockRealPath))
    for patcher in self.patchers:
      patcher.start()

  def tearDown(self):
    for patcher in self.patchers:
      patcher.stop()

  def testProbeI2C(self):
    expected = {
        'bus_number': '1',
        'bus_name': 'I2C-1 NAME',
        'bus_path': '/FAKE_PATH',
        'addr': '0x0b'}
    with mock.patch('subprocess.check_output') as mock_output:
      mock_output.return_value = textwrap.dedent("""\
           0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
      00:                                  --
      10:
      20:
      30:
      40:
      50:
      60:
      70:
      """)
      func = i2c.I2CFunction(bus_number='1', addr='0xb')
      result = func()
      self.assertEquals(result, [])

    with mock.patch('subprocess.check_output') as mock_output:
      mock_output.return_value = textwrap.dedent("""\
           0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
      00:                                  UU
      10:
      20:
      30:
      40:
      50:
      60:
      70:
      """)
      func = i2c.I2CFunction(bus_number='1', addr='0xb')
      result = func()
      self.assertEquals(result, [expected])

    with mock.patch('subprocess.check_output') as mock_output:
      mock_output.return_value = textwrap.dedent("""\
           0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
      00:                                  0b
      10:
      20:
      30:
      40:
      50:
      60:
      70:
      """)
      func = i2c.I2CFunction(bus_number='1', addr='0xb')
      result = func()
      self.assertEquals(result, [expected])

  def testProbeECI2C(self):
    with mock.patch('subprocess.call', return_value=1):
      func = i2c.I2CFunction(bus_number='EC-0', addr='0xb')
      result = func()
      self.assertEquals(result, [])

    with mock.patch('subprocess.call', return_value=0):
      func = i2c.I2CFunction(bus_number='EC-0', addr='0xb')
      result = func()
      self.assertEquals(result, [{'bus_number': 'EC-0', 'addr': '0x0b'}])


if __name__ == '__main__':
  unittest.main()
