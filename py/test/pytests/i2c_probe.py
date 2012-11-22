# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A hardware test for probing I2C devices.

It uses i2cdetect utility to check if there's an device on specific bus.

dargs:
  bus: (int) I2C bus to probe.
  addr: (int) I2C addr to probe.
"""

import re
import unittest

from cros.factory.test.args import Arg
from cros.factory.utils.process_utils import SpawnOutput

_RE_DEVICE_FOUND = re.compile('^\d\d:\s+(UU|[0-9a-f]{2})', re.MULTILINE)


class I2CProbeTest(unittest.TestCase):
  ARGS = [
    Arg('bus', int, 'I2C bus to probe.'),
    Arg('addr', int, 'I2C addr to probe.'),
  ]

  def runTest(self):
    bus, addr = self.args.bus, self.args.addr
    cmd = 'i2cdetect -y %d 0x%x 0x%x' % (bus, addr, addr)
    response = SpawnOutput(cmd.split(), log=True)

    self.assertTrue(_RE_DEVICE_FOUND.search(response) is not None,
                    'No I2C device on bus %d addr 0x%x' % (bus, addr))
