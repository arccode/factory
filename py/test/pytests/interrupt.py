# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests if an interrupt's count is larger than expected.

dargs:
  interrupt: interrupt number or name.
  reload_module: Kernel module name. If set, rmmod and modprobe it.
  min_count: Minimum interrupt count to pass.
"""

import time
import unittest

from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils


class InterruptTest(unittest.TestCase):
  """Tests if an interrupt's count is larger than expected."""

  ARGS = [
      Arg('interrupt', (int, str), 'Interrupt number or name.'),
      Arg('reload_module', str,
          'Kernel module name. If set, rmmod and modprobe it.', default=None),
      Arg('min_count', int, 'Minimum #interrupts to pass.', default=1),
  ]

  def _GetInterruptCount(self, interrupt):
    if isinstance(interrupt, int):
      interrupt = str(interrupt)

    interrupts = sys_utils.GetInterrupts()
    self.assertTrue(interrupt in interrupts,
                    'Cannot get interrupt %s.' % interrupt)
    return interrupts[interrupt]

  def runTest(self):
    interrupt, reload_module, min_count = (
        self.args.interrupt, self.args.reload_module, self.args.min_count)
    count = self._GetInterruptCount(interrupt)

    if reload_module:
      process_utils.Spawn(['rmmod', reload_module], call=True)
      process_utils.Spawn(['modprobe', reload_module], call=True)
      # Wait for procfs update
      time.sleep(1)
      count = self._GetInterruptCount(interrupt) - count

    self.assertTrue(
        count >= min_count,
        'Interrupt test failed: int[%s] = %d < min_count %d' % (
            interrupt, count, min_count))
