#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory import system
from cros.factory.system.ec import EC


class SystemStatusTest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()

  def runTest(self):

    # Set up mocks for EC interface
    mock_ec = self.mox.CreateMock(EC)
    self.mox.StubOutWithMock(system, 'GetEC')
    # Set up mocks for netifaces.
    netifaces = system.netifaces = self.mox.CreateMockAnything()
    netifaces.AF_INET = 2
    netifaces.AF_INET6 = 10

    system.GetEC().AndReturn(mock_ec)
    mock_ec.GetFanRPM().AndReturn(2000)
    system.GetEC().AndReturn(mock_ec)
    mock_ec.GetTemperatures().AndReturn([1, 2, 3, 4, 5])
    system.GetEC().AndReturn(mock_ec)
    mock_ec.GetMainTemperatureIndex().AndReturn(2)
    netifaces.interfaces().AndReturn(['lo0', 'eth0', 'wlan0'])
    netifaces.ifaddresses('eth0').AndReturn(
      {netifaces.AF_INET6: [{'addr': 'aa:aa:aa:aa:aa:aa'}],
       netifaces.AF_INET: [{'broadcast': '192.168.1.255',
                            'addr': '192.168.1.100'}]})
    netifaces.ifaddresses('wlan0').AndReturn(
      {netifaces.AF_INET: [{'addr': '192.168.16.100'},
                           {'addr': '192.168.16.101'}]})
    self.mox.ReplayAll()

    # Don't care about the values; just make sure there's something
    # there.
    status = system.SystemStatus()
    # Don't check battery, since this system might not even have one.
    self.assertTrue(isinstance(status.battery, dict))
    self.assertEquals(3, len(status.load_avg))
    self.assertEquals(10, len(status.cpu))
    self.assertEquals(
      'eth0=192.168.1.100, wlan0=192.168.16.100+192.168.16.101',
      status.ips)

    self.mox.VerifyAll()


if __name__ == "__main__":
  unittest.main()
