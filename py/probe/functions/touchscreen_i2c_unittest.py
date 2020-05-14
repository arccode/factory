#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import tempfile
import unittest

from cros.factory.probe.functions import touchscreen_i2c
from cros.factory.utils import file_utils


class I2cTouchscreenFunctionTest(unittest.TestCase):
  def setUp(self):
    self.my_root = tempfile.mkdtemp()

    self.orig_glob_path = touchscreen_i2c.I2cTouchscreenFunction.GLOB_PATH
    touchscreen_i2c.I2cTouchscreenFunction.GLOB_PATH = (
        self.my_root + touchscreen_i2c.I2cTouchscreenFunction.GLOB_PATH)

  def tearDown(self):
    touchscreen_i2c.I2cTouchscreenFunction.GLOB_PATH = self.orig_glob_path

  def _CreateDevice(self, name, driver_target, values):
    path = os.path.join(self.my_root, 'sys', 'bus', 'i2c', 'devices', name)
    file_utils.TryMakeDirs(path)

    for key, value in values.items():
      file_utils.WriteFile(os.path.join(path, key), value)

    driver_target = self.my_root + driver_target
    file_utils.TryMakeDirs(driver_target)
    file_utils.ForceSymlink(driver_target, os.path.join(path, 'driver'))

  def testNormal(self):
    values1 = {'name': 'name1', 'hw_version': '1234', 'fw_version': '5678'}
    self._CreateDevice('dev1', '/sys/bus/i2c/drivers/elants_i2c', values1)

    # The driver of this device is not elants_i2c.
    values2 = {'name': 'xxxx', 'hw_version': '1357', 'fw_version': '2468'}
    self._CreateDevice('dev2', '/sys/bus/i2c/drivers/not_elants_i2c', values2)

    func = touchscreen_i2c.I2cTouchscreenFunction()
    device_path = os.path.join(self.my_root,
                               'sys', 'bus', 'i2c', 'devices', 'dev1')
    self.assertCountEqual(
        func(),
        [dict(values1, device_path=device_path, vendor='04f3', product='1234')])


if __name__ == '__main__':
  unittest.main()
