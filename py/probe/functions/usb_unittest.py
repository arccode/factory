#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import usb
from cros.factory.utils import  file_utils


def _AddBusType(results):
  for result in results:
    result['bus_type'] = 'usb'
  return results


class USBFunctionTest(unittest.TestCase):
  def setUp(self):
    self.my_root = tempfile.mkdtemp()

    self.orig_glob_path = usb.USBFunction.GLOB_PATH
    usb.USBFunction.GLOB_PATH = self.my_root + usb.USBFunction.GLOB_PATH

  def tearDown(self):
    usb.USBFunction.GLOB_PATH = self.orig_glob_path

  def _CreateUSBDevice(self, usb_name, real_path, values):
    real_path = self.my_root + real_path

    file_utils.TryMakeDirs(real_path)
    for key, value in values.iteritems():
      file_utils.WriteFile(os.path.join(real_path, key), value)

    link_name = os.path.join(
        self.my_root, 'sys', 'bus', 'usb', 'devices', usb_name)
    file_utils.TryMakeDirs(os.path.dirname(link_name))
    file_utils.ForceSymlink(real_path, link_name)

  def testNormal(self):
    # usb 1-1 includes only one required fields
    values1 = {'idVendor': 'google', 'idProduct': 'chromebook'}
    self._CreateUSBDevice('1-1', '/sys/devices/usb3/1-1', values1)

    # usb 1-1.2 includes some optional fields
    values2 = {'idVendor': 'goog', 'idProduct': 'cros', 'manufacturer': '123'}
    self._CreateUSBDevice('1-1.2', '/sys/devices/usb3/1-1.2', values2)

    # usb 1-1.2.y has an invalid directory name
    values3 = {'idVendor': 'goog', 'idProduct': 'cros'}
    self._CreateUSBDevice('1-1.2.y', '/sys/devices/usb3/1-1.2.y', values3)

    # usb 1-2 misses some required fields
    values4 = {'idVendor': 'goog', 'product': '234'}
    self._CreateUSBDevice('1-2', '/sys/devices/usb3/1-2', values4)

    # usb1 is a usb root hub.
    values5 = {'idVendor': 'aaa', 'idProduct': 'bbb'}
    self._CreateUSBDevice('usb1', '/sys/devices/usb1', values5)

    func = usb.USBFunction()
    self.assertEquals(
        sorted(func()), _AddBusType(sorted([values1, values2, values5])))

    func = usb.USBFunction(dir_path=self.my_root + '/sys/bus/usb/devices/1-1')
    self.assertEquals(func(), _AddBusType([values1]))

    func = usb.USBFunction(dir_path=self.my_root + '/sys/devices/usb3/1-1.2')
    self.assertEquals(func(), _AddBusType([values2]))


if __name__ == '__main__':
  unittest.main()
