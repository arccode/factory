#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test EC battery communication.

The test uses factory.system.EC to get battery design capacity.
"""

import logging
import unittest

from cros.factory import system
from cros.factory.test.args import Arg

class ECBatteryTest(unittest.TestCase):
  """Tests EC battery communication."""
  ARGS = [
    Arg('design_capacity_range', tuple,
        'Expected battery design capacity range in mAh.',
        default=(1000, 10000)),
  ]

  def setUp(self):
    self._ec = system.GetEC()
    self._ec.Hello()

  def runTest(self):
    lower, upper = self.args.design_capacity_range
    capacity = self._ec.GetBatteryDesignCapacity()
    logging.info('Get battery design capacity from EC: %d', capacity)
    self.assertTrue(
      lower <= capacity <= upper,
      'Battery design capacity %d out of range: %s' % (
        capacity, str(self.args.design_capacity_range)))
