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
import threading
import unittest2

from cros.factory.event_log import Log
from cros.factory.test import test_ui
from cros.factory.test import utils
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn, CheckOutput

_TEST_TITLE = test_ui.MakeLabel('Suspend/Resume Test', zh=u'暂停/恢复测试')
_MSG_CYCLE = test_ui.MakeLabel('Suspend/Resume:', zh=u'暂停/恢复:')
_ID_CYCLES = 'sr_cycles'
_ID_RUN = 'sr_run'
_TEST_BODY = ('<font size="20">%s <div id="%s"></div> of \n'
              '<div id="%s"></div></font>') % (_MSG_CYCLE, _ID_RUN, _ID_CYCLES)
_MIN_SUSPEND_MARGIN_SECS = 5

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
    Arg('resume_early_margin_secs', int, 'The allowable margin for the '
        'DUT to wake early', default=0),
    Arg('resume_worst_case_secs', int, 'The worst case time a device is '
        'expected to take to resume', default=30),
    Arg('suspend_worst_case_secs', int, 'The worst case time a device is '
        'expected to take to suspend', default=60),
    Arg('wakealarm_path', str, 'Path to the wakealarm file',
        default='/sys/class/rtc/rtc0/wakealarm'),
    Arg('time_path', str, 'Path to the time (since_epoch) file',
        default='/sys/class/rtc/rtc0/since_epoch'),
    Arg('wakeup_count_path', str, 'Path to the wakeup_count file',
        default='/sys/power/wakeup_count'),
  ]

  def setUp(self):
    self.assertTrue(os.path.exists(self.args.wakealarm_path), 'wakealarm_path '
                    '%s is not found, bad path?' % (self.args.wakealarm_path))
    self.assertTrue(os.path.exists(self.args.time_path), 'time_path %s is not '
                    'found, bad path?' % (self.args.time_path))
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

    self._ui = test_ui.UI()
    self._template = OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._template.SetState(_TEST_BODY)

    # Remove lid-opened, which will prevent suspend.
    file_utils.TryUnlink('/var/run/power_manager/lid_opened')
    # Create this directory so powerd_suspend doesn't fail.
    utils.TryMakeDirs('/var/run/power_manager/root')

    self.done = False
    self.wakeup_count = ''
    self.start_time = 0
    self.resume_at = 0
    self.attempted_wake_extensions = 0
    self.actual_wake_extensions = 0
    self.initial_suspend_count = 0
    self.alarm_started = threading.Event()
    self.alarm_thread = threading.Thread()

  def tearDown(self):
    self.done = True
    self.alarm_thread.join(5)
    self.assertFalse(self.alarm_thread.isAlive(), 'Alarm thread failed join.')
    # Clear any active wake alarms
    open(self.args.wakealarm_path, 'w').write('0')

  def _MonitorWakealarm(self):
    """Start and extend the wakealarm as needed for the main thread."""
    open(self.args.wakealarm_path, 'w').write(str(self.resume_at))
    self.alarm_started.set()
    # CAUTION: the loop below is subject to race conditions with suspend time.
    while self._ReadSuspendCount() < self.initial_suspend_count + self.run:
      time.sleep(0.1)
      if self.done:
        break
      cur_time = self._ReadCurrentTime()
      if cur_time >= self.resume_at - 1:
        self.attempted_wake_extensions += 1
        logging.warn('Late suspend detected, attempting wake extension')
        open(self.args.wakealarm_path, 'w').write(
            '+=' + str(_MIN_SUSPEND_MARGIN_SECS))
        if (self._ReadSuspendCount() >= self.initial_suspend_count + self.run
            and self._ReadCurrentTime() < cur_time +
            _MIN_SUSPEND_MARGIN_SECS):
          logging.info('Attempted wake time extension, but suspended before.')
          break
        self.resume_at = self.resume_at + _MIN_SUSPEND_MARGIN_SECS
        self.actual_wake_extensions += 1
        logging.info('Attempted extending the wake timer %d s, resume is now '
                     'at %d.', _MIN_SUSPEND_MARGIN_SECS, self.resume_at)
      self.assertGreaterEqual(self.start_time +
                              self.args.suspend_worst_case_secs,
                              cur_time, 'Suspend timeout, device did not '
                              'suspend within %d sec.' %
                              self.args.suspend_worst_case_secs)
    self.alarm_started.clear()

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
    # If we just resumed, the suspend_stats file can take some time to update.
    time.sleep(0.1)
    line_content = open('/sys/kernel/debug/suspend_stats').read().strip()
    return int(re.search(r'[0-9]+', line_content).group(0))

  def _ReadCurrentTime(self):
    """Read the current time in seconds since_epoch.

    Args:
      None.

    Returns:
      Int, the time since_epoch in seconds.
    """
    with open(self.args.time_path, 'r') as f:
      return int(f.read().strip())

  def _VerifySuspended(self, count, resume_at):
    """Verify that a reasonable suspend has taken place.

    Args:
      count: expected number of suspends the system has executed
      resume_at: expected time since epoch to have resumed

    Returns:
      Boolean, True if suspend was valid, False if not.
    """
    cur_time = self._ReadCurrentTime()
    self.assertGreaterEqual(
        cur_time, resume_at - self.args.resume_early_margin_secs,
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
    self.initial_suspend_count = self._ReadSuspendCount()
    logging.info('The initial suspend count is %d.', self.initial_suspend_count)

    random.seed(0)  # Make test deterministic

    for self.run in range(1, self.args.cycles + 1):
      # Log disk usage to find out what cause disk full.
      # Check crosbug.com/p/18518
      disk_usage = CheckOutput(
          "du -a --exclude=factory/tests /var | sort -n -r | head -n 20",
          shell=True, log=True)
      logging.info(disk_usage)
      self.attempted_wake_extensions = 0
      self.actual_wake_extensions = 0
      alarm_suspend_delays = 0
      self.alarm_thread = threading.Thread(target=self._MonitorWakealarm)
      self._ui.SetHTML(self.run, id=_ID_RUN)
      self.start_time = self._ReadCurrentTime()
      suspend_time = random.randint(self.args.suspend_delay_min_secs,
                                    self.args.suspend_delay_max_secs)
      resume_time = random.randint(self.args.resume_delay_min_secs,
                                   self.args.resume_delay_max_secs)
      self.resume_at = suspend_time + self.start_time
      logging.info('Suspend %d of %d for %d seconds, starting at %d.',
                   self.run, self.args.cycles, suspend_time, self.start_time)
      self.wakeup_count = open(self.args.wakeup_count_path).read().strip()
      self.alarm_thread.start()
      self.assertTrue(self.alarm_started.wait(_MIN_SUSPEND_MARGIN_SECS),
                      'Alarm thread timed out.')
      logging.info('Calling powerd_suspend at %d', self._ReadCurrentTime())
      Spawn(['powerd_suspend', '-w', self.wakeup_count], check_call=True,
            log_stderr_on_error=True)
      logging.info('Return from powerd_suspend at %d', self._ReadCurrentTime())
      self._VerifySuspended(self.initial_suspend_count + self.run,
                            self.resume_at)
      logging.info('Resumed %d of %d for %d seconds.',
                   self.run, self.args.cycles, resume_time)
      time.sleep(resume_time)
      while self.alarm_thread.isAlive():
        alarm_suspend_delays += 1
        logging.warn('alarm thread is taking a while to return, waiting 1s.')
        time.sleep(1)
        self.assertGreaterEqual(self.start_time +
                                self.args.suspend_worst_case_secs,
                                int(open(self.args.time_path).read().strip()),
                                'alarm thread did not return within %d sec.' %
                                self.args.suspend_worst_case_secs)
      Log('suspend_resume_cycle', run=self.run, start_time=self.start_time,
          suspend_time=suspend_time, resume_time=resume_time,
          resume_at=self.resume_at, wakeup_count=self.wakeup_count,
          suspend_count=self._ReadSuspendCount(),
          initial_suspend_count=self.initial_suspend_count,
          attempted_wake_extensions=self.attempted_wake_extensions,
          actual_wake_extensions=self.actual_wake_extensions,
          alarm_suspend_delays=alarm_suspend_delays)
    self._ui.Pass()
