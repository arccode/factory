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
import threading
import time

from cros.factory.device import device_utils
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.env import paths
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


_MIN_SUSPEND_MARGIN_SECS = 5


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
      Arg('resume_early_margin_secs', int,
          'The allowable margin for the DUT to wake early', default=0),
      Arg('resume_worst_case_secs', int,
          'The worst case time a device is expected to take to resume',
          default=30),
      Arg('ignore_wakeup_source', str, 'Wakeup source to ignore', default=None),
      Arg('backup_rtc', bool, 'Use second rtc if present for backup',
          default=False),
      Arg('memory_check', bool, 'Use memory_suspend_test to suspend',
          default=False),
      Arg('memory_check_size', int,
          'Amount of memory to allocate (0 means as much as possible)',
          default=0),
  ]

  ui_class = test_ui.ScrollableLogUI

  def setUp(self):
    self.assertGreaterEqual(self.args.memory_check_size, 0)
    self.assertTrue(self.args.memory_check or not self.args.memory_check_size,
                    'Do not specify memory_check_size if memory_check is '
                    'False.')
    self.assertGreaterEqual(self.args.suspend_delay_min_secs,
                            _MIN_SUSPEND_MARGIN_SECS, 'The '
                            'suspend_delay_min_secs is too low, bad '
                            'test_list?')
    self.assertGreaterEqual(self.args.suspend_delay_max_secs,
                            self.args.suspend_delay_min_secs, 'Invalid suspend '
                            'timings provided in test_list (max < min).')
    self.assertGreaterEqual(self.args.resume_delay_max_secs,
                            self.args.resume_delay_min_secs, 'Invalid resume '
                            'timings provided in test_list (max < min).')
    self.dut = device_utils.CreateDUTInterface()
    self.goofy = state.GetInstance()
    self._suspend_stress_test_stop = threading.Event()

  def UpdateOutput(self, handle, interval_sec=0.1):
    """Updates output from file handle to given HTML node."""
    while not self._suspend_stress_test_stop.is_set():
      c = handle.read()
      if c:
        self.ui.AppendLog(c)
      time.sleep(interval_sec)

  def runTest(self):
    command = [
        'suspend_stress_test',
        '--count', str(self.args.cycles),
        '--suspend_max', str(self.args.suspend_delay_max_secs),
        '--suspend_min', str(self.args.suspend_delay_min_secs),
        '--wake_max', str(self.args.resume_delay_max_secs),
        '--wake_min', str(self.args.resume_delay_min_secs),
        '--wake_early_margin', str(self.args.resume_early_margin_secs),
        '--wake_worst_case', str(self.args.resume_worst_case_secs),
    ]
    if self.args.ignore_wakeup_source:
      command += ['--ignore_wakeup_source', self.args.ignore_wakeup_source]
    if self.args.backup_rtc:
      command += ['--backup_rtc']
    if self.args.memory_check:
      command += [
          '--memory_check',
          '--memory_check_size', str(self.args.memory_check_size)]

    logging.info('command: %r', command)
    testlog.LogParam('command', command)

    def GetLogPath(suffix):
      path = 'suspend_stress_test.' + suffix
      return os.path.join(paths.DATA_TESTS_DIR, session.GetCurrentTestPath(),
                          path)

    logging.info('Log path is %s', GetLogPath('*'))
    result_path = GetLogPath('result')
    stdout_path = GetLogPath('stdout')
    stderr_path = GetLogPath('stderr')
    with open(stdout_path, 'w+', 1) as out, open(stderr_path, 'w', 1) as err:
      process = self.dut.Popen(command, stdout=out, stderr=err)
      thread = process_utils.StartDaemonThread(
          target=self.UpdateOutput, args=(out, ))
      process.wait()
      self._suspend_stress_test_stop.set()
      thread.join()
    self.goofy.WaitForWebSocketUp()

    stdout = file_utils.ReadFile(stdout_path)
    stderr = file_utils.ReadFile(stderr_path)
    returncode = process.returncode

    try:
      file_utils.WriteFile(result_path, str(returncode))
    except IOError:
      logging.exception('Can not write logs to %s.', result_path)

    testlog.LogParam('stdout', stdout)
    testlog.LogParam('stderr', stderr)
    testlog.LogParam('returncode', returncode)
    # TODO(chuntsen): Attach EC logs and other system logs on failure.

    errors = []
    if returncode != 0:
      errors.append('Suspend stress test failed: returncode:%d' % returncode)
    match = re.findall(r'Premature wake detected', stdout)
    if match:
      errors.append('Premature wake detected:%d' % len(match))
    match = re.search(r'Finished (\d+) iterations', stdout)
    if match and match.group(1) != str(self.args.cycles):
      errors.append('Only finished %r cycles instead of %d cycles' %
                    (match.group(1), self.args.cycles))
    match = re.search(r'Suspend failures: (\d+)', stdout)
    if match and match.group(1) != '0':
      errors.append(match.group(0))
    match = re.search(r'Wakealarm errors: (\d+)', stdout)
    if match and match.group(1) != '0':
      errors.append(match.group(0))
    match = re.search(r'Firmware log errors: (\d+)', stdout)
    if match and match.group(1) != '0':
      errors.append(match.group(0))
    match = re.search(r's0ix errors: (\d+)', stdout)
    if match and match.group(1) != '0':
      errors.append(match.group(0))
    if errors:
      self.FailTask('%r' % errors)
