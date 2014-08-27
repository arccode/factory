#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import signal
import tempfile
import time
import unittest

import factory_common # pylint: disable=W0611
from cros.factory.test import utils


EARLIER_VAR_LOG_MESSAGES = '''19:26:17 kernel: That's all, folks.
19:26:56 kernel: [  0.000000] Initializing cgroup subsys cpuset
19:26:56 kernel: [  0.000000] Initializing cgroup subsys cpu
19:26:56 kernel: [  0.000000] Linux version blahblahblah
'''

VAR_LOG_MESSAGES = '''19:00:00 kernel: 7 p.m. and all's well.
19:27:17 kernel: That's all, folks.
19:27:17 kernel: Kernel logging (proc) stopped.
19:27:56 kernel: imklog 4.6.2, log source = /proc/kmsg started.
19:27:56 rsyslogd: [origin software="rsyslogd" blahblahblah] (re)start
19:27:56 kernel: [  0.000000] Initializing cgroup subsys cpuset
19:27:56 kernel: [  0.000000] Initializing cgroup subsys cpu
19:27:56 kernel: [  0.000000] Linux version blahblahblah
19:27:56 kernel: [  0.000000] Command line: blahblahblah
'''

class VarLogMessagesTest(unittest.TestCase):
  def _GetMessages(self, data, lines):
    with tempfile.NamedTemporaryFile() as f:
      path = f.name
      f.write(data)
      f.flush()

      return utils.var_log_messages_before_reboot(path=path, lines=lines)

  def runTest(self):
    self.assertEquals([
        "19:27:17 kernel: That's all, folks.",
        "19:27:17 kernel: Kernel logging (proc) stopped.",
        "<after reboot, kernel came up at 19:27:56>",
        ], self._GetMessages(VAR_LOG_MESSAGES, 2))
    self.assertEquals([
        "19:27:17 kernel: Kernel logging (proc) stopped.",
        "<after reboot, kernel came up at 19:27:56>",
        ], self._GetMessages(VAR_LOG_MESSAGES, 1))
    self.assertEquals([
        "19:00:00 kernel: 7 p.m. and all's well.",
        "19:27:17 kernel: That's all, folks.",
        "19:27:17 kernel: Kernel logging (proc) stopped.",
        "<after reboot, kernel came up at 19:27:56>",
        ], self._GetMessages(VAR_LOG_MESSAGES, 100))
    self.assertEquals([
        "19:26:17 kernel: That's all, folks.",
        "<after reboot, kernel came up at 19:26:56>",
        ], self._GetMessages(EARLIER_VAR_LOG_MESSAGES, 1))


class TimeoutTest(unittest.TestCase):
  def runTest(self):
    with utils.Timeout(3):
      time.sleep(1)

    prev_secs = signal.alarm(10)
    self.assertTrue(prev_secs == 0,
                    msg='signal.alarm() is in use after "with Timeout()"')
    try:
      with utils.Timeout(3):
        time.sleep(1)
    except AssertionError:
      pass
    else:
      self.assertTrue(False, msg='No assert raised on previous signal.alarm()')
    signal.alarm(0)

    try:
      with utils.Timeout(1):
        time.sleep(3)
    except utils.TimeoutError:
      pass
    else:
      self.assertTrue(False, msg='No timeout')


class WaitForTest(unittest.TestCase):
  def runTest(self):
    def _ReturnTrueAfter(t):
      return time.time() > t

    now = time.time()
    self.assertEquals(None, utils.WaitFor(lambda: _ReturnTrueAfter(now + 0.5),
                                          timeout_secs=1))

    now = time.time()
    self.assertRaises(utils.TimeoutError, utils.WaitFor,
                      lambda: _ReturnTrueAfter(now + 1), timeout_secs=0.5)


if __name__ == "__main__":
  unittest.main()
