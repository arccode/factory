# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A hardware test for checking battery existence.

This checks the existence of battery in sysfs.
"""

import unittest

from cros.factory import system

class SysfsBatteryTest(unittest.TestCase):
  def runTest(self):
    power = system.GetBoard().power
    self.assertTrue(power.CheckBatteryPresent(), "Cannot find battery path.")
    self.assertTrue(power.GetChargePct() is not None,
                    "Cannot get charge percentage.")
