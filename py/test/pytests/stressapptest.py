# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A test to stress CPU, memory and disk.

Description
-----------
A test using `stressapptest <https://github.com/stressapptest/stressapptest>`_
to stress CPU, memory, and disk.

By default the system data partition (or the stateful partition for Chrome OS
devices) is used. However a long stress testing of disk may shorten eMMC or SSD
life, so you may want to set `disk_thread` argument to False if `seconds` is
pretty long.

Setting memory ratio may be tricky. If your system does not have enough free
memory (for example if you have lots of tests running in parallel) then the test
will fail, so usually you'll want to set `free_memory_only` argument to True.

However, if you start multiple tests at same time, other tests may allocate more
memory after the calculation of "free memory" is done, causing the test to fail.
To solve that, increase the argument `wait_secs` so the calculation of "free
memory" will be done when the memory usage is stabilized.

Test Procedure
--------------
This is an automated test without user interaction.

Start the test and it will run for the time specified in argument `seconds`, and
pass if no errors found; otherwise fail with error messages and logs, especially
if unexpected reboot or crash were found during execution.

Dependency
----------
- Need external program `stressapptest
  <https://github.com/stressapptest/stressapptest>`_.

Examples
--------
To stress CPU, memory (90% of free memory), and the disk using stateful
partition for 60 seconds, add this in test list::

  {
    "pytest_name": "stressapptest"
  }

To stress for one day without accessing disk::

  {
    "pytest_name": "stressapptest",
    "args": {
      "seconds": 86400,
      "disk_thread": false
    }
  }

To stress using only two threads, and only run on cpu core 2 and 3::

  {
    "pytest_name": "stressapptest",
    "args": {
      "num_threads": 2,
      "taskset_args": ["-c", "2,3"]
    }
  }
"""

import logging
import time
import unittest

from cros.factory.device import device_utils
from cros.factory.test import state
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
          default=True),
      Arg('wait_secs', int,
          'Time to wait in seconds before executing stressapptest.',
          default=0),
      Arg('disk_thread', bool,
          'Stress disk using -f argument of stressapptest.',
          default=True),
      Arg('disk_thread_dir', str,
          'Directory of disk thread file will be placed '
          '(default to system stateful partition.)',
          default=None),
      Arg('max_errors', int,
          'Number of errors to exit early.',
          default=stress_manager.DEFAULT_MAX_ERRORS),
      Arg('num_threads', int,
          'Number of threads to be used. Default to number of cores.',
          default=None),
      Arg('taskset_args', list,
          'Argument to taskset to change CPU affinity for stressapptest.',
          default=None)
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.goofy = state.GetInstance()

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
          disk_thread_dir=self.args.disk_thread_dir,
          max_errors=self.args.max_errors,
          num_threads=self.args.num_threads,
          taskset_args=self.args.taskset_args):
        pass
    except stress_manager.StressManagerError as e:
      logging.error('StressAppTest failed: %s', e)
      raise
    finally:
      self.goofy.WaitForWebSocketUp()
