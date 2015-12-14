#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import time
import unittest

import factory_common # pylint: disable=W0611

from cros.factory.test.args import Arg
from cros.factory.test.utils.stress_manager import StressManager
from cros.factory.test.utils.stress_manager import StressManagerError


class StressAppTest(unittest.TestCase):
  """Run stressapptest to test the memory and disk is fine."""

  ARGS = [
      Arg('seconds', int,
          'Time to execute the stressapptest.', default=60),
      Arg('free_memory_fraction', float,
          'Fraction of free memory', default=0.95),
      Arg('wait_secs', int,
          'Time to wait in seconds before executing stressapptest.', default=0),
      Arg('disk_thread', bool,
          'stress disk using -f argument of stressapptest.',
          default=True),
  ]

  def runTest(self):
    # Wait other parallel tests memory usage to settle to a stable value, so
    # stressapptest will not claim too much memory.
    if self.args.wait_secs:
      time.sleep(self.args.wait_secs)

    try:
      with StressManager(self.dut).Run(
          duration_secs=self.args.seconds,
          memory_ratio=self.args.free_memory_fraction,
          disk_thread=self.args.disk_thread):
        pass
    except StressManagerError as e:
      logging.error('StressAppTest failed: %s', e)
      raise e
