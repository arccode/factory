# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests if an interrupt's count is larger than expected.

dargs:
  interrupt: interrupt number or name.
  reload_module: Kernel module name. If set, rmmod and modprobe it.
  min_count: Minimum interrupt count to pass.
"""

import logging
import time
import unittest

from cros.factory.test.args import Arg
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn


class ProcInterrupts(object):
  """Parses /proc/interrupts to get #interrupts per module."""

  def __init__(self):
    self._interrupt_count = {}
    self._ParseInterrupts()

  def _ParseInterrupts(self):
    """Parses /proc/interrupts.

    Stores interrupt count in self._interrupt_count.
    """
    lines = file_utils.ReadLines('/proc/interrupts')
    if not lines:
      return

    # First line indicates CPUs in system
    num_cpus = len(lines.pop(0).split())

    for line_num, line in enumerate(lines, start=1):
      fields = line.split()
      if len(fields) < num_cpus + 1:
        logging.error('Parse error at line %d: %s', line_num, line)
        continue
      interrupt = fields[0].strip().split(':')[0]
      count = sum(map(int, fields[1:1 + num_cpus]))
      self._interrupt_count[interrupt] = count
      logging.debug('int[%s] = %d', interrupt, count)

  def GetCount(self, interrupt):
    """Gets interrupt count across all CPUs.

    Args:
      interrupt: either interrupt number or name.

    Returns:
      interrupt count. -1 if not found.
    """
    if isinstance(interrupt, int):
      interrupt = str(interrupt)

    if interrupt not in self._interrupt_count:
      logging.error('Cannot get interrupt %s.', interrupt)
      return -1

    count = self._interrupt_count[interrupt]
    logging.debug('Got int[%s] = %d', interrupt, count)
    return count


class InterruptTest(unittest.TestCase):
  """Tests if an interrupt's count is larger than expected."""

  ARGS = [
    Arg('interrupt', (int, str), 'Interrupt number or name.'),
    Arg('reload_module', str,
        'Kernel module name. If set, rmmod and modprobe it.', optional=True),
    Arg('min_count', int, 'Minimum #interrupts to pass.', default=1),
  ]

  def _GetInterruptCount(self, interrupt):
    count = ProcInterrupts().GetCount(interrupt)
    self.assertNotEqual(count, -1, 'Cannot get interrupt %s.' % interrupt)
    return count

  def runTest(self):
    interrupt, reload_module, min_count = (
      self.args.interrupt, self.args.reload_module, self.args.min_count)
    count = self._GetInterruptCount(interrupt)

    if reload_module:
      Spawn(['rmmod', reload_module], call=True)
      Spawn(['modprobe', reload_module], call=True)
      # Wait for procfs update
      time.sleep(1)
      count = self._GetInterruptCount(interrupt) - count

    self.assertTrue(
      count >= min_count,
      'Interrupt test failed: int[%s] = %d < min_count %d' % (
        interrupt, count, min_count))
