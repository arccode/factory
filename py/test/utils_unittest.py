#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import tempfile
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
        ], self._GetMessages(VAR_LOG_MESSAGES, 2))
    self.assertEquals([
        "19:27:17 kernel: Kernel logging (proc) stopped.",
        ], self._GetMessages(VAR_LOG_MESSAGES, 1))
    self.assertEquals([
        "19:00:00 kernel: 7 p.m. and all's well.",
        "19:27:17 kernel: That's all, folks.",
        "19:27:17 kernel: Kernel logging (proc) stopped.",
        ], self._GetMessages(VAR_LOG_MESSAGES, 100))
    self.assertEquals([
        "19:26:17 kernel: That's all, folks.",
        ], self._GetMessages(EARLIER_VAR_LOG_MESSAGES, 1))

if __name__ == "__main__":
  unittest.main()
