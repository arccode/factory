#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for system module."""


import logging
import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory import system
from cros.factory.system.board import Board
from cros.factory.system import partitions

MOCK_RELEASE_IMAGE_LSB_RELEASE = "GOOGLE_RELEASE=5264.0.0"

class SystemStatusTest(unittest.TestCase):
  """Unittest for SystemStatus."""
  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()

  def runTest(self):

    # Set up mocks for Board interface
    mock_board = self.mox.CreateMock(Board)
    self.mox.StubOutWithMock(system, 'GetBoard')
    # Set up mocks for netifaces.
    netifaces = system.netifaces = self.mox.CreateMockAnything()
    netifaces.AF_INET = 2
    netifaces.AF_INET6 = 10

    system.GetBoard().AndReturn(mock_board)
    mock_board.GetFanRPM().AndReturn(2000)
    system.GetBoard().AndReturn(mock_board)
    mock_board.GetTemperatures().AndReturn([1, 2, 3, 4, 5])
    system.GetBoard().AndReturn(mock_board)
    mock_board.GetMainTemperatureIndex().AndReturn(2)
    netifaces.interfaces().AndReturn(['lo', 'eth0', 'wlan0'])
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


class SystemInfoTest(unittest.TestCase):
  """Unittest for SystemInfo."""
  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()

  def runTest(self):
    self.mox.StubOutWithMock(partitions, 'GetRootDev')
    partitions.GetRootDev().AndReturn('/dev/sda')
    self.mox.StubOutWithMock(system, 'MountDeviceAndReadFile')
    system.MountDeviceAndReadFile('/dev/sda5', '/etc/lsb-release').AndReturn(
        MOCK_RELEASE_IMAGE_LSB_RELEASE)

    self.mox.ReplayAll()

    info = system.SystemInfo()
    self.assertEquals('5264.0.0', info.release_image_version)
    # The cached release image version will be used in the second time.
    info = system.SystemInfo()
    self.assertEquals('5264.0.0', info.release_image_version)

    self.mox.VerifyAll()

if __name__ == "__main__":
  logging.basicConfig(
      format='%(asctime)s:%(filename)s:%(lineno)d:%(levelname)s:%(message)s',
      level=logging.DEBUG)
  unittest.main()
