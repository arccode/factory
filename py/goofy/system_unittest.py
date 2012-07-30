#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import system


class SystemStatusTest(unittest.TestCase):
  def runTest(self):
    # Set up mocks for netifaces.
    netifaces = system.netifaces = mox.MockAnything()
    netifaces.AF_INET = 2
    netifaces.AF_INET6 = 10

    netifaces.interfaces().AndReturn(['lo0', 'eth0', 'wlan0'])
    netifaces.ifaddresses('eth0').AndReturn(
      {netifaces.AF_INET6: [{'addr': 'aa:aa:aa:aa:aa:aa'}],
       netifaces.AF_INET: [{'broadcast': '192.168.1.255',
                            'addr': '192.168.1.100'}]})
    netifaces.ifaddresses('wlan0').AndReturn(
      {netifaces.AF_INET: [{'addr': '192.168.16.100'},
                           {'addr': '192.168.16.101'}]})
    mox.Replay(netifaces)

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

    mox.Verify(netifaces)


class ParseTemperaturesTest(unittest.TestCase):
  def runTest(self):
    # pylint: disable=W0212
    self.assertEquals([1, 2, None, 4, None],
                      system.SystemStatus._ParseTemperatures(
                          '0: 274\n'
                          '1: 275\n'
                          'Sensor 2 error\n'
                          '3: 277\n'
                          'Sensor 4 error\n'))
    self.assertEquals(['Foo', 'Bar', None, 'Baz'],
                      system.SystemStatus._ParseTemperatureInfo(
                          '0: 3 Foo\n'
                          '1: 4 Bar\n'
                          'EC returned error result code 2\n'
                          '3: 255 Baz\n'))

if __name__ == "__main__":
  unittest.main()
