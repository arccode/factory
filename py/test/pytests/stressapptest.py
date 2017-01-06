#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.utils import stress_manager
from cros.factory.utils.arg_utils import Arg


class StressAppTest(unittest.TestCase):
  """Run stressapptest to test the memory and disk is fine."""

  ARGS = [
      Arg('seconds', int,
          'Time to execute the stressapptest.', default=60),
      Arg('memory_ratio', float,
          'Radio of memory to be used by stressapptest.',
          default=0.9),
      Arg('free_memory_only', bool,
          'Only use free memory for test. When set to True, only '
          'memory_radio * free_memory are used for stressapptest.',
          default=False),
      Arg('wait_secs', int,
          'Time to wait in seconds before executing stressapptest.',
          default=0),
      Arg('disk_thread', bool,
          'stress disk using -f argument of stressapptest.',
          default=True),
      Arg('disk_thread_dir', str,
          'directory of disk thread file will be placed',
          default=None),
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    # Wait other parallel tests memory usage to settle to a stable value, so
    # stressapptest will not claim too much memory.
    if self.args.wait_secs:
      time.sleep(self.args.wait_secs)

    try:
      with stress_manager.StressManager(self.dut).Run(
          duration_secs=self.args.seconds,
          memory_ratio=self.args.memory_ratio,
          free_memory_only=self.args.free_memory_only,
          disk_thread=self.args.disk_thread,
          disk_thread_dir=self.args.disk_thread_dir):
        pass
    except stress_manager.StressManagerError as e:
      logging.error('StressAppTest failed: %s', e)
      raise e
