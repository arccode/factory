#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mock
import unittest
import textwrap

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import i2c


class I2CFunctionTest(unittest.TestCase):
  def testProbeI2C(self):
    with mock.patch('subprocess.check_output') as mock_output:
      mock_output.return_value = textwrap.dedent('''\
           0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
      00:                                  --
      10:
      20:
      30:
      40:
      50:
      60:
      70:
      ''')
      func = i2c.I2CFunction(bus='1', addr='0xb')
      result = func()
      self.assertEquals(result, [])

    with mock.patch('subprocess.check_output') as mock_output:
      mock_output.return_value = textwrap.dedent('''\
           0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
      00:                                  UU
      10:
      20:
      30:
      40:
      50:
      60:
      70:
      ''')
      func = i2c.I2CFunction(bus='1', addr='0xb')
      result = func()
      self.assertEquals(result, [{'bus': '1', 'addr': '0x0b'}])

    with mock.patch('subprocess.check_output') as mock_output:
      mock_output.return_value = textwrap.dedent('''\
           0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
      00:                                  0b
      10:
      20:
      30:
      40:
      50:
      60:
      70:
      ''')
      func = i2c.I2CFunction(bus='1', addr='0xb')
      result = func()
      self.assertEquals(result, [{'bus': '1', 'addr': '0x0b'}])

  def testProbeECI2C(self):
    with mock.patch('subprocess.call') as mock_call:
      mock_call.return_value = 1
      func = i2c.I2CFunction(bus='EC-0', addr='0xb')
      result = func()
      self.assertEquals(result, [])

    with mock.patch('subprocess.call') as mock_call:
      mock_call.return_value = 0
      func = i2c.I2CFunction(bus='EC-0', addr='0xb')
      result = func()
      self.assertEquals(result, [{'bus': 'EC-0', 'addr': '0x0b'}])


if __name__ == '__main__':
  unittest.main()
