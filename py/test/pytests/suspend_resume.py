# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''Suspends and resumes the device an adjustable number of times for
adjustable random lengths of time.

This uses the powerd_suspend utility and the rtc's wakealarm entry in sysfs.

Note that the rtc sysfs entry may vary from device to device, the test_list
must define the path to the correct sysfs entry for the specific device, the
default assumes a typical /sys/class/rtc/rtc0 entry.
'''


import logging
import os
import random
import re
import time
import unittest2

from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn

_TEST_TITLE = test_ui.MakeLabel('Suspend/Resume Test', zh=u'暂停/恢复测试')
_MSG_CYCLE = test_ui.MakeLabel('Suspend/Resume:', zh=u'暂停/恢复:')
_ID_CYCLES = 'sr_cycles'
_ID_RUN = 'sr_run'
_TEST_BODY = ('<font size="20">%s <div id="%s"></div> of \n'
              '<div id="%s"></div></font>') % (_MSG_CYCLE, _ID_RUN, _ID_CYCLES)

class SuspendResumeTest(unittest2.TestCase):
  ARGS = [
    Arg('cycles', int, 'Number of cycles to suspend/resume', default=1),
    Arg('suspend_delay_max_secs', int, 'Max time in sec during suspend per '
        'cycle', default=10),
    Arg('suspend_delay_min_secs', int, 'Min time in sec during suspend per '
        'cycle', default=5),
    Arg('resume_delay_max_secs', int, 'Max time in sec during resume per cycle',
        default=10),
    Arg('resume_delay_min_secs', int, 'Min time in sec during resume per cycle',
        default=5),
    Arg('resume_worst_case_secs', int, 'The worst case time a device is '
        'expected to take to resume', default=20),
    Arg('wakealarm_path', str, 'Path to the wakealarm file',
        default='/sys/class/rtc/rtc0/wakealarm'),
    Arg('time_path', str, 'Path to the time (since_epoch) file',
        default='/sys/class/rtc/rtc0/since_epoch'),
  ]

  def setUp(self):
    self.assertTrue(os.path.exists(self.args.wakealarm_path), 'wakealarm_path '
                    '%s is not found, bad path?' % (self.args.wakealarm_path))
    self.assertTrue(os.path.exists(self.args.time_path), 'time_path %s is not '
                    'found, bad path?' % (self.args.time_path))
    self._ui = test_ui.UI()
    self._template = OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._template.SetState(_TEST_BODY)

    # Remove lid-opened, which will prevent suspend.
    file_utils.TryUnlink('/var/run/power_manager/lid_opened')

  def _ReadSuspendCount(self):
    """Read the current suspend count from /sys/kernel/debug/suspend_stats.
    This assumes the first line of suspend_stats contains the number of
    successfull suspend cycles.

    Args:
      None.

    Returns:
      Int, the number of suspends the system has executed since last reboot.
    """
    self.assertTrue(os.path.exists('/sys/kernel/debug/suspend_stats'),
                    'suspend_stats file not found.')
    line_content = open('/sys/kernel/debug/suspend_stats').read().strip()
    return int(re.search(r'[0-9]+', line_content).group(0))

  def _VerifySuspended(self, count, resume_at):
    """Verify that a reasonable suspend has taken place.

    Args:
      count: expected number of suspends the system has executed
      resume_at: expected time since epoch to have resumed

    Returns:
      Boolean, True if suspend was valid, False if not.
    """
    cur_time = int(open(self.args.time_path).read().strip())
    self.assertGreaterEqual(
        cur_time, resume_at,
        'Premature wake detected (%d s early), spurious event? (got touched?)'
        % (resume_at - cur_time))
    self.assertLessEqual(
        cur_time, resume_at + self.args.resume_worst_case_secs,
        'Late wake detected (%ds > %ds delay), timer failure?' % (
            cur_time - resume_at, self.args.resume_worst_case_secs))

    actual_count = self._ReadSuspendCount()
    self.assertEqual(
        count, actual_count,
        'Incorrect suspend count: ' + (
            'no suspend?' if actual_count < count else 'spurious suspend?'))

  def runTest(self):
    self._ui.Run(blocking=False)
    self._ui.SetHTML(self.args.cycles, id=_ID_CYCLES)
    initial_suspend_count = self._ReadSuspendCount()

    random.seed(0)  # Make test deterministic

    for run in range(1, self.args.cycles + 1):
      self._ui.SetHTML(run, id=_ID_RUN)
      cur_time = int(open(self.args.time_path).read().strip())
      suspend_time = random.randint(self.args.suspend_delay_min_secs,
                                    self.args.suspend_delay_max_secs)
      logging.info('Suspend %d of %d for %d seconds.',
                   run, self.args.cycles, suspend_time)
      resume_at = suspend_time + cur_time
      open(self.args.wakealarm_path, 'w').write(str(resume_at))
      Spawn('powerd_suspend', check_call=True, log_stderr_on_error=True)
      self._VerifySuspended(initial_suspend_count + run, resume_at)
      resume_time = random.randint(self.args.resume_delay_min_secs,
                                   self.args.resume_delay_max_secs)
      logging.info('Resumed %d of %d for %d seconds',
                   run, self.args.cycles, resume_time)
      time.sleep(resume_time)
    self._ui.Pass()
