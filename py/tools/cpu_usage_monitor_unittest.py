#!/usr/bin/python -u
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.tools.cpu_usage_monitor import CPUUsageMonitor
from cros.factory.utils import process_utils

MOCK_TOP_OUTPUT = \
"""top - 11:46:54 up  3:25,  0 users,  load average: 0.33, 2.32, 2.79
Tasks: 224 total,   1 running, 223 sleeping,   0 stopped,   0 zombie
Cpu(s): 10.3%us, 55.8%sy,  0.0%ni, 33.4%id,  0.2%wa,  0.0%hi,  0.2%si,  0.0%st
Mem:   2067628k total,   789764k used,  1277864k free,   105392k buffers
Swap:  1953124k total,        0k used,  1953124k free,   271360k cached

  PID USER   PR  NI  VIRT  RES  SHR S %CPU %MEM    TIME+  COMMAND
  32753 root   20   0  2284 1052  716 R    60  0.1   0:00.06 longer_than_10_char
  30275 root   20   0  170m  19m 3664 S    25  0.9   0:07.04 i_use_cpu
  30277 root   20   0  310m  12m 4436 S     4 12.6   0:03.04 i_use_memory
      3 root   20   0     0    0    0 S     0  0.0   0:00.80 [ksoftirqd/0]
      6 root   RT   0     0    0    0 S     0  0.0   0:00.00 [migration/0]
      7 root   RT   0     0    0    0 S     0  0.0   0:00.30 [watchdog/0]
"""
MOCK_LOAD = '1.2, 0.9, 0.8'

EXPECTED_OUTPUT = ('Load average: 1.2, 0.9, 0.8; ' +
                   'Process 32753 using 60% CPU: longer_tha; ' +
                   'Process 30275 using 25% CPU: i_use_cpu')

class TestCpuUsageMonitor(unittest.TestCase):
  def setUp(self):
    self.monitor = CPUUsageMonitor(120)
    self.monitor.COMMAND_LENGTH = 10
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(logging, 'info')
    self.mox.StubOutWithMock(CPUUsageMonitor, '_GetLoadString')
    self.mox.StubOutWithMock(process_utils, 'CheckOutput')

  def tearDown(self):
    self.mox.VerifyAll()
    self.mox.UnsetStubs()

  def testTopParsing(self):
    self.monitor._GetLoadString().AndReturn(MOCK_LOAD) # pylint: disable=W0212
    process_utils.CheckOutput(['top', '-b', '-c', '-n', '1']).AndReturn(
        MOCK_TOP_OUTPUT)
    logging.info(EXPECTED_OUTPUT)

    self.mox.ReplayAll()
    self.monitor.Check()


if __name__ == '__main__':
  unittest.main()
