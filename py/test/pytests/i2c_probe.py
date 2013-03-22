# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A hardware test for probing I2C devices.

It uses i2cdetect utility to check if there's an device on specific bus.

dargs:
  bus: (int) I2C bus to probe.
  addr: (int, list) I2C addr to probe. Can be a list containing multiple
    I2C addresses. If multiple addresses are specified, the test passes
    when *any* of those exists.
"""

import re
import unittest

from cros.factory.event_log import Log
from cros.factory.test.args import Arg
from cros.factory.utils.process_utils import SpawnOutput

_RE_DEVICE_FOUND = re.compile('^(UU|[0-9a-f]{2})$')


class I2CProbeTest(unittest.TestCase):
  def DeviceExists(self, i2c_result):
    """Returns true if i2c_result indicates that the device exists."""
    # Ignore first line.
    i2c_result = i2c_result[i2c_result.find('\n'):]
    return any(_RE_DEVICE_FOUND.match(f) for f in i2c_result.split())

  def ProbeI2C(self, bus, addr):
    cmd = 'i2cdetect -y %d 0x%x 0x%x' % (bus, addr, addr)
    return self.DeviceExists(SpawnOutput(cmd.split(), log=True))

  ARGS = [
    Arg('bus', int, 'I2C bus to probe.'),
    Arg('addr', (int, list), 'I2C address(es) to probe.'),
  ]

  def runTest(self):
    bus, addr_list = self.args.bus, self.args.addr
    if type(addr_list) != list:
      addr_list = [addr_list]
    probed_result = [self.ProbeI2C(bus, addr) for addr in addr_list]
    Log('ic2_probed', result=probed_result, bus=bus, addr_list=addr_list)
    self.assertTrue(any(probed_result),
                    'No I2C device on bus %d addr %s' %
                    (bus, ', '.join(['0x%x' % addr for addr in addr_list])))
