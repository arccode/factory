# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Uses i2cdetect utility to probe for I2C devices on a specific bus.
"""

import re
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import Log
from cros.factory.test import factory
from cros.factory.test.args import Arg
from cros.factory.utils.process_utils import SpawnOutput
from cros.factory.utils.sys_utils import GetI2CBus

_RE_DEVICE_FOUND = re.compile('^(UU|[0-9a-f]{2})$')


class I2CProbeTest(unittest.TestCase):
  def DeviceExists(self, i2c_result):
    """Returns true if i2c_result indicates that the device exists."""
    # Ignore first line.
    i2c_result = i2c_result[i2c_result.find('\n'):]
    return any(_RE_DEVICE_FOUND.match(f) for f in i2c_result.split())

  def ProbeI2C(self, bus, addr, r_flag):
    cmd = 'i2cdetect %s -y %d 0x%x 0x%x' % ('-r ' if r_flag else '',
                                            bus, addr, addr)
    return self.DeviceExists(SpawnOutput(cmd.split(), log=True))

  ARGS = [
    Arg('bus', int, 'I2C bus to probe.', optional=True),
    Arg('addr', (int, list), 'I2C address(es) to probe. Can be a list '
        'containing multiple I2C addresses, in which case the test passes '
        'when *any* of those exists.'),
    Arg('r_flag', bool, 'Use SMBus "read byte" commands for probing.',
        default=False),
    Arg('auto_detect_device', (str, list),
        'Given devices name from /proc/bus/input/devices to auto '
        'detect i2c bus',
        optional=True)
  ]

  def runTest(self):
    self.assertTrue(self.args.bus is not None or self.args.auto_detect_device,
        'You should assign bus or enable auto detect')
    bus, addr_list, r_flag = self.args.bus, self.args.addr, self.args.r_flag
    if self.args.auto_detect_device:
      if type(self.args.auto_detect_device) != list:
        self.args.auto_detect_device = [self.args.auto_detect_device]
      bus = GetI2CBus(self.args.auto_detect_device)
      self.assertTrue(type(bus) is int, "Auto detect bus error")
      factory.console.info('Auto detect bus: %d' % bus)

    if type(addr_list) != list:
      addr_list = [addr_list]
    probed_result = [self.ProbeI2C(bus, addr, r_flag) for addr in addr_list]
    Log('ic2_probed', result=probed_result, bus=bus, addr_list=addr_list)
    self.assertTrue(any(probed_result),
        'No I2C device on bus %d addr %s' %
        (bus, ', '.join(['0x%x' % addr for addr in addr_list])))
