#!/usr/bin/env python3
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for SystemStatus."""


import logging
import unittest
from unittest import mock

from cros.factory.device import device_types
from cros.factory.device import fan
from cros.factory.device import power
from cros.factory.device import status as status_module
from cros.factory.device import thermal


class SystemStatusTest(unittest.TestCase):
  """Unittest for SystemStatus."""

  def runTest(self):
    # Set up mocks for Board interface
    board = mock.Mock(device_types.DeviceBoard)
    board.power = mock.Mock(power.Power)
    board.power.GetInfoDict.return_value = {}

    # Make it raise exception, then charge_state will be None rather than
    # mock object. If it's a mock object, it will make deepcopy fail.
    # Check "battery" method in class SystemStatus.
    board.power.GetChargeState.side_effect = IOError

    board.fan = mock.Mock(fan.FanControl)
    board.fan.GetFanRPM.return_value = [2000]

    board.thermal = mock.Mock(thermal.Thermal)
    board.thermal.GetTemperature.return_value = 37

    # Set up mocks for netifaces.
    def IfaddressesSideEffect(*args, **unused_kwargs):
      if args[0] == 'eth0':
        return {netifaces.AF_INET6: [{'addr': 'aa:aa:aa:aa:aa:aa'}],
                netifaces.AF_INET: [{'broadcast': '192.168.1.255',
                                     'addr': '192.168.1.100'}]}
      if args[0] == 'wlan0':
        return {netifaces.AF_INET: [{'addr': '192.168.16.100'},
                                    {'addr': '192.168.16.101'}]}
      return None

    netifaces = status_module.netifaces = mock.MagicMock()
    netifaces.AF_INET = 2
    netifaces.AF_INET6 = 10

    netifaces.interfaces.return_value = ['lo', 'eth0', 'wlan0']
    netifaces.ifaddresses.side_effect = IfaddressesSideEffect

    status = status_module.SystemStatus(board).Snapshot()

    # Don't check battery, since this system might not even have one.
    self.assertTrue(isinstance(status.battery, dict))
    self.assertEqual([2000], status.fan_rpm)
    self.assertEqual(37, status.temperature)
    self.assertEqual(
        'eth0=192.168.1.100, wlan0=192.168.16.100+192.168.16.101',
        status.ips)


if __name__ == '__main__':
  logging.basicConfig(
      format='%(asctime)s:%(filename)s:%(lineno)d:%(levelname)s:%(message)s',
      level=logging.DEBUG)
  unittest.main()
