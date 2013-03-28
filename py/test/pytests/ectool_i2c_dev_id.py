# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A hardware test for checking EC connected I2C device's ID.

It uses ectool to read device ID from periphral and check for correctness.

dargs:
  bus: (int) I2C bus to probe.
  spec: (list) A list of tuples. Each tuple is in the following format:
    (addr, reg, expected_value).
      addr: The I2C address of the periphral.
      reg: The register containing device ID.
      expected_value: The expected device ID.
    If the condition in any tuple matches, the test passes.
"""

import re
import unittest

from cros.factory.event_log import Log
from cros.factory.test.args import Arg
from cros.factory.utils.process_utils import SpawnOutput

RE_I2C_RESULT = re.compile('Read from I2C port \d+ at \S+ offset \S+ = (0x\S+)')


class EctoolI2CDevIdTest(unittest.TestCase):

  ARGS = [
    Arg('bus', int, 'I2C bus to probe.'),
    Arg('spec', list, 'Address/register and expected values.'),
  ]

  def CheckDevice(self, bus, addr, reg, expected_value):
    cmd = 'ectool i2cread 8 %d %d %d' % (bus, addr, reg)
    output = SpawnOutput(cmd.split(), log=True)
    match = RE_I2C_RESULT.search(output)
    if not match:
      return False
    return int(match.group(1), 16) == expected_value

  def runTest(self):
    result = [self.CheckDevice(self.args.bus, *spec) for spec in self.args.spec]
    Log('device_checked', result=result, bus=self.args.bus, spec=self.args.spec)
    self.assertTrue(any(result), 'Device ID mismatches.')
