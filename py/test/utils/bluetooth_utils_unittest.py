#!/usr/bin/env python3
#
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for bluetooth_utils."""

import unittest

import mock

from cros.factory.test.utils import bluetooth_utils


class BtMgmtTest(unittest.TestCase):
  def setUp(self):
    self.btmgmt = bluetooth_utils.BtMgmt()

  @mock.patch('cros.factory.utils.process_utils.CheckOutput')
  def testFindTtyByDriver(self, checkoutput_mock):
    checkoutput_mock.return_value = (
        'Discovery started\n'
        'hci0 type 7 discovering on\n'
        'hci0 dev_found: 5B:00:39:3C:AD:32 type BR/EDR rssi -79 flags 0x0000\n'
        'AD flags 0x1a\n'
        'hci0 dev_found: 5C:F3:70:77:72:24 type BR/EDR rssi -59 flags 0x0000\n'
        'name scaned_device_name\n'
        'hci0 type 7 discovering off')

    devices = self.btmgmt.FindDevices()
    self.assertDictEqual(
        devices,
        {'5B:00:39:3C:AD:32': {'RSSI': -79},
         '5C:F3:70:77:72:24': {'RSSI': -59, 'Name': 'scaned_device_name'}})


if __name__ == '__main__':
  unittest.main()
