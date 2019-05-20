# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Suspend and resume device with given cycles.

Description
-----------
Suspends and resumes the device an adjustable number of times for adjustable
random lengths of time.
See ``suspend_stress_test`` for more details.

Test Procedure
--------------
This is an automated test without user interaction.

When started, the test will try to suspend and resume by given arguments.
Will fail if unexpected reboot, crash or error found.

Dependency
----------
- power manager ``powerd``.
- power manager tool ``suspend_stress_test``.

Examples
--------
To suspend/resume in 1 cycle, suspend in 5~10 seconds, resume in 5~10 seconds,
and suspend to idle by writing freeze to ``/sys/power/state``::

  {
    "pytest_name": "suspend_stress"
  }
"""

import logging
import os
import re
import subprocess
import time

import six

from cros.factory.device import device_utils
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.env import paths
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import time_utils


class SuspendStressTest(test_case.TestCase):
  """Run suspend_stress_test to test the suspending is fine."""

  ARGS = [
      Arg('cycles', int, 'Number of cycles to suspend/resume', default=1),
      Arg('suspend_delay_max_secs', int,
          'Max time in sec during suspend per cycle', default=10),
      Arg('suspend_delay_min_secs', int,
          'Min time in sec during suspend per cycle', default=5),
      Arg('resume_delay_max_secs', int,
          'Max time in sec during resume per cycle', default=10),
      Arg('resume_delay_min_secs', int,
          'Min time in sec during resume per cycle', default=5),
      Arg('ignore_wakeup_source', str, 'Wakeup source to ignore', default=None),
      Arg('backup_rtc', bool, 'Use second rtc if present for backup',
          default=False),
  ]

  ui_class = test_ui.ScrollableLogUI

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.goofy = state.GetInstance()

  def UpdateOutput(self, handle, output, interval_sec=0.1):
    """Updates output from file handle to given HTML node."""
    while True:
      c = os.read(handle.fileno(), 4096)
      if not c:
        break
      c = c.decode('utf-8')
      self.ui.AppendLog(c)
      output.write(c)
      time.sleep(interval_sec)

  def runTest(self):
    command = [
        'suspend_stress_test',
        '--count', str(self.args.cycles),
        '--suspend_max', str(self.args.suspend_delay_max_secs),
        '--suspend_min', str(self.args.suspend_delay_min_secs),
        '--wake_max', str(self.args.resume_delay_max_secs),
        '--wake_min', str(self.args.resume_delay_min_secs),
    ]
    if self.args.ignore_wakeup_source:
      command += ['--ignore_wakeup_source', self.args.ignore_wakeup_source]
    if self.args.backup_rtc:
      command += ['--backup_rtc']
    logging.info('command: %r', command)
    testlog.LogParam('command', command)

    output = six.StringIO()
    process = self.dut.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    thread = process_utils.StartDaemonThread(
        target=self.UpdateOutput, args=(process.stdout, output))

    process.wait()
    thread.join()
    self.goofy.WaitForWebSocketUp()

    stdout = output.getvalue()
    stderr = process.stderr.read()
    returncode = process.returncode

    log_prefix = os.path.join(
        paths.DATA_TESTS_DIR, session.GetCurrentTestPath(),
        'suspend_stress_test.%s.' % time_utils.TimeString())
    logging.info('Log path is %s*', log_prefix)
    for suffix, value in zip(['result', 'stdout', 'stderr'],
                             [returncode, stdout, stderr]):
      try:
        path = log_prefix + suffix
        self.dut.WriteFile(path, str(value))
      except IOError:
        logging.exception('Can not write logs to %s.', path)

    testlog.LogParam('stdout', stdout)
    testlog.LogParam('stderr', stderr)
    testlog.LogParam('returncode', returncode)
    # TODO(chuntsen): Attach EC logs and other system logs on failure.

    if returncode != 0:
      self.FailTask('Suspend stress test failed')
    match = re.search(r'Finished (\d+) iterations', stdout)
    if match and match.group(1) != str(self.args.cycles):
      self.FailTask('Only finished %r cycles instead of %d cycles' %
                    (match.group(1), self.args.cycles))
    match = re.search(r'Suspend failures: (\d+)', stdout)
    if match and match.group(1) != '0':
      self.FailTask(match.group(0))
    match = re.search(r'Wakealarm errors: (\d+)', stdout)
    if match and match.group(1) != '0':
      self.FailTask(match.group(0))
    match = re.search(r'Firmware log errors: (\d+)', stdout)
    if match and match.group(1) != '0':
      self.FailTask(match.group(0))
    match = re.search(r's0ix errors: (\d+)', stdout)
    if match and match.group(1) != '0':
      self.FailTask(match.group(0))
