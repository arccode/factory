#!/usr/bin/env python2
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for SystemStatus."""


import logging
import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.device import fan
from cros.factory.device import power
from cros.factory.device import status as status_module
from cros.factory.device import thermal
from cros.factory.device import types


class SystemStatusTest(unittest.TestCase):
  """Unittest for SystemStatus."""

  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()

  def runTest(self):
    # Set up mocks for netifaces.
    netifaces = status_module.netifaces = self.mox.CreateMockAnything()
    netifaces.AF_INET = 2
    netifaces.AF_INET6 = 10

    # Set up mocks for Board interface
    board = self.mox.CreateMock(types.DeviceBoard)
    board.power = self.mox.CreateMock(power.Power)
    board.power.GetInfoDict().AndReturn({})
    board.fan = self.mox.CreateMock(fan.FanControl)
    board.fan.GetFanRPM().AndReturn([2000])
    board.thermal = self.mox.CreateMock(thermal.Thermal)
    board.thermal.GetTemperature().AndReturn(37)
    netifaces.interfaces().AndReturn(['lo', 'eth0', 'wlan0'])
    netifaces.ifaddresses('eth0').AndReturn(
        {netifaces.AF_INET6: [{'addr': 'aa:aa:aa:aa:aa:aa'}],
         netifaces.AF_INET: [{'broadcast': '192.168.1.255',
                              'addr': '192.168.1.100'}]})
    netifaces.ifaddresses('wlan0').AndReturn(
        {netifaces.AF_INET: [{'addr': '192.168.16.100'},
                             {'addr': '192.168.16.101'}]})
    self.mox.ReplayAll()

    status = status_module.SystemStatus(board).Snapshot()

    # Don't check battery, since this system might not even have one.
    self.assertTrue(isinstance(status.battery, dict))
    self.assertEquals([2000], status.fan_rpm)
    self.assertEquals(37, status.temperature)
    self.assertEquals(
        'eth0=192.168.1.100, wlan0=192.168.16.100+192.168.16.101',
        status.ips)

    self.mox.VerifyAll()


if __name__ == '__main__':
  logging.basicConfig(
      format='%(asctime)s:%(filename)s:%(lineno)d:%(levelname)s:%(message)s',
      level=logging.DEBUG)
  unittest.main()
