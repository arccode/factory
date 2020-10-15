#!/usr/bin/env python3
#
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for bluetooth_utils."""

import unittest
from unittest import mock

from cros.factory.test.utils import bluetooth_utils


class BtMgmtTest(unittest.TestCase):
  def setUp(self):
    with mock.patch('cros.factory.utils.process_utils.CheckOutput') as (
        checkoutput_mock):
      checkoutput_mock.return_value = (
          'Index list with 1 item\n'
          'hci0:   Primary controller\n'
          '        addr 3C:28:6D:01:02:03 version 10 manufacturer 29 class'
          ' 0x000000\n'
          '        supported settings: powered connectable fast-connectable'
          ' discoverable bondable link-security ssp br/edr hs le advertising'
          ' secure-conn debug-keys privacy configuration static-addr'
          ' phy-configuratio\n'
          '        current settings: bondable ssp br/edr le secure-conn'
          ' wide-band-speech\n'
          '        name Chromebook\n'
          '        short name\n'
          'hci0:   Configuration options\n'
          '        supported options: public-address\n'
          '        missing options: public-address\n')
      self.btmgmt = bluetooth_utils.BtMgmt()

  def testSearchMacAddress(self):
    self.assertEqual(self.btmgmt.GetMac(), '3C:28:6D:01:02:03')

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
    expected_result = {
        '5B:00:39:3C:AD:32': {
            'RSSI': -79
        },
        '5C:F3:70:77:72:24': {
            'RSSI': -59,
            'Name': 'scaned_device_name'
        }
    }

    devices = self.btmgmt.FindDevices()
    self.assertEqual(checkoutput_mock.call_args_list, [
        mock.call(['btmgmt', '--index', '0', 'find'], log=True),
        mock.call(['btmgmt', '--index', '0', 'stop-find'], log=True)
    ])
    self.assertDictEqual(devices, expected_result)

    devices = self.btmgmt.FindDevices(timeout_secs=0)
    self.assertEqual(checkoutput_mock.call_args_list[-2:], [
        mock.call(['btmgmt', '--index', '0', '--timeout', '0', 'find'],
                  log=True),
        mock.call(['btmgmt', '--index', '0', 'stop-find'], log=True)
    ])
    self.assertDictEqual(devices, expected_result)


if __name__ == '__main__':
  unittest.main()
