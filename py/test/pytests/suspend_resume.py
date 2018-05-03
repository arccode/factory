# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Suspend and resume device with given cycles.

Description
-----------
Suspends and resumes the device an adjustable number of times for
adjustable random lengths of time.

Test Procedure
--------------
This is an automated test without user interaction.

When started, the test will try to suspend and resume by given arguments.
Will fail if device wakes too early, or if unexpected reboot (or crash) found.

Dependency
----------
- ``powerd_suspend`` utility.
- rtc's ``wakealarm`` entry in ``sysfs``.

Note that the rtc sysfs entry may vary from device to device, so the test_list
must define the path to the correct sysfs entry for the specific device, the
default assumes a typical ``/sys/class/rtc/rtc0 entry``.

Examples
--------
To suspend/resume in 1 cycle, suspend in 5~10 seconds, resume in 5~10 seconds,
and suspend to memory (see more criteria from arguments)::

  {
    "pytest_name": "suspend_resume"
  }
"""


import errno
import logging
import os
import random
import re
import threading

import factory_common  # pylint: disable=unused-import
from cros.factory.test import event_log
from cros.factory.test.i18n import _
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import debug_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils

_MIN_SUSPEND_MARGIN_SECS = 5

_MESSAGES = '/var/log/messages'

_KERNEL_DEBUG_WAKEUP_SOURCES = '/sys/kernel/debug/wakeup_sources'
_MAX_EARLY_RESUME_RETRY_COUNT = 3


class SuspendResumeTest(test_case.TestCase):
  ARGS = [
      Arg('cycles', int, 'Number of cycles to suspend/resume', default=1),
      Arg('suspend_delay_max_secs', int,
          'Max time in sec during suspend per '
          'cycle', default=10),
      Arg('suspend_delay_min_secs', int,
          'Min time in sec during suspend per '
          'cycle', default=5),
      Arg('resume_delay_max_secs', int,
          'Max time in sec during resume per cycle', default=10),
      Arg('resume_delay_min_secs', int,
          'Min time in sec during resume per cycle', default=5),
      Arg('resume_early_margin_secs', int,
          'The allowable margin for the '
          'DUT to wake early', default=0),
      Arg('resume_worst_case_secs', int,
          'The worst case time a device is '
          'expected to take to resume', default=30),
      Arg('suspend_worst_case_secs', int,
          'The worst case time a device is '
          'expected to take to suspend', default=60),
      Arg('wakealarm_path', str, 'Path to the wakealarm file',
          default='/sys/class/rtc/rtc0/wakealarm'),
      Arg('time_path', str, 'Path to the time (since_epoch) file',
          default='/sys/class/rtc/rtc0/since_epoch'),
      Arg('wakeup_count_path', str, 'Path to the wakeup_count file',
          default='/sys/power/wakeup_count'),
      Arg('suspend_type', str, 'Suspend type',
          default='mem'),
      Arg('ignore_wakeup_source', str, 'Wakeup source to ignore',
          default=None),
      Arg('early_resume_retry_wait_secs', int,
          'Time to wait before re-suspending after early resume',
          default=3)]

  def setUp(self):
    self.assertTrue(os.path.exists(self.args.wakealarm_path), 'wakealarm_path '
                    '%s is not found, bad path?' % self.args.wakealarm_path)
    self.assertTrue(os.path.exists(self.args.time_path), 'time_path %s is not '
                    'found, bad path?' % self.args.time_path)
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

    self.goofy = state.get_instance()

    self.ui.ToggleTemplateClass('font-large', True)

    # Remove lid-opened, which will prevent suspend.
    file_utils.TryUnlink('/run/power_manager/lid_opened')
    # Create this directory so powerd_suspend doesn't fail.
    file_utils.TryMakeDirs('/run/power_manager/root')

    self.done = False
    self.wakeup_count = ''
    self.start_time = 0
    self.resume_at = 0
    self.attempted_wake_extensions = 0
    self.actual_wake_extensions = 0
    self.initial_suspend_count = 0
    self.alarm_started = threading.Event()
    self.alarm_thread = threading.Thread()
    self.messages = None

  def tearDown(self):
    # Always log the last suspend/resume block we saw.  This is most
    # useful for failures, of course, but we log the last block for
    # successes too to make them easier to compare.
    if self.messages:
      # Remove useless lines that have any of these right after the square
      # bracket:
      #   call
      #   G[A-Z]{2}\d? (a register name)
      #   save
      messages = re.sub(r'^.*\] (call|G[A-Z]{2}\d?|save).*$\n?', '',
                        self.messages, flags=re.MULTILINE)
      logging.info('Last suspend block:\n%s',
                   re.sub('^', '    ', messages, flags=re.MULTILINE))

    self.done = True
    self.alarm_thread.join(5)
    self.assertFalse(self.alarm_thread.isAlive(), 'Alarm thread failed join.')
    # Clear any active wake alarms
    open(self.args.wakealarm_path, 'w').write('0')

  def _GetIgnoredWakeupSourceCount(self):
    """Return the recorded wakeup count for the ignored wakeup source."""
    if not self.args.ignore_wakeup_source:
      return None

    with open(_KERNEL_DEBUG_WAKEUP_SOURCES, 'r') as f:
      # The output has the format of:
      #
      # name active_count event_count wakeup_count expire_count active_since \
      #   total_time max_time last_change prevent_suspend_time
      # mmc2:0001:1 0 0 0 0 0 00 33154 0
      # ...
      #
      # We want to get the 'wakeup_count' column
      for line in f.readlines()[1:]:
        parts = line.split()
        if parts[0] == self.args.ignore_wakeup_source:
          return int(parts[3])

      raise RuntimeError('Ignore wakeup source %s not found' %
                         self.args.ignore_wakeup_source)

  def _MonitorWakealarm(self):
    """Start and extend the wakealarm as needed for the main thread."""
    file_utils.WriteFile(self.args.wakealarm_path, str(self.resume_at))
    self.alarm_started.set()
    # CAUTION: the loop below is subject to race conditions with suspend time.
    while (self._ReadSuspendCount() < self.initial_suspend_count + self.run
           and not self.done):
      cur_time = self._ReadCurrentTime()
      if cur_time >= self.resume_at - 1:
        self.attempted_wake_extensions += 1
        logging.warn('Late suspend detected, attempting wake extension')
        try:
          file_utils.WriteFile(self.args.wakealarm_path,
                               '+=' + str(_MIN_SUSPEND_MARGIN_SECS))
        except IOError:
          # The write to wakealarm returns EINVAL (22) if no alarm is active
          logging.warn('Write to wakealarm failed, assuming we woke: %s',
                       debug_utils.FormatExceptionOnly())
          break
        if (self._ReadSuspendCount() >= self.initial_suspend_count + self.run
            and self._ReadCurrentTime() < cur_time + _MIN_SUSPEND_MARGIN_SECS):
          logging.info('Attempted wake time extension, but suspended before.')
          break
        self.resume_at = self.resume_at + _MIN_SUSPEND_MARGIN_SECS
        self.actual_wake_extensions += 1
        logging.info('Attempted extending the wake timer %d s, resume is now '
                     'at %d.', _MIN_SUSPEND_MARGIN_SECS, self.resume_at)
      self.assertGreaterEqual(
          self.start_time + self.args.suspend_worst_case_secs,
          cur_time,
          'Suspend timeout, device did not suspend within %d sec.' %
          self.args.suspend_worst_case_secs)
      self.Sleep(0.1)
    self.alarm_started.clear()

  def _Suspend(self, retry_count=0):
    """Suspend the device by writing to /sys/power/state."""
    # Explicitly sync the filesystem
    process_utils.Spawn(['sync'], check_call=True, log_stderr_on_error=True)

    prev_suspend_ignore_count = self._GetIgnoredWakeupSourceCount()
    logging.info('Suspending at %d', self._ReadCurrentTime())

    try:
      # Write out our expected wakeup_count. Wakeup_count is a mechanism to
      # handle wakeup events in a non-racy way. If there is an IO error during
      # this write, it means someone else issues a wakeup event at the same
      # time.
      file_utils.WriteFile(self.args.wakeup_count_path, self.wakeup_count,
                           log=True)
    except Exception:
      raise RuntimeError('Failed to write to wakeup_count. Maybe there is '
                         'another program trying to suspend at the same time?')

    try:
      # Suspend to memory
      file_utils.WriteFile('/sys/power/state', self.args.suspend_type,
                           log=True)
    except IOError as err:
      # Both of the write could result in IOError if there is an early wake.
      if err.errno in [errno.EBUSY, errno.EINVAL]:
        if prev_suspend_ignore_count:
          logging.info('Early wake event when attempting suspend')
          if prev_suspend_ignore_count != self._GetIgnoredWakeupSourceCount():
            if retry_count == _MAX_EARLY_RESUME_RETRY_COUNT:
              raise RuntimeError('Maximum re-suspend retry exceeded for '
                                 'ignored wakeup source %s' %
                                 self.args.ignore_wakeup_source)

            logging.info('Wakeup source ignored, re-suspending...')
            self.Sleep(self.args.early_resume_retry_wait_secs)
            self.wakeup_count = file_utils.ReadFile(
                self.args.wakeup_count_path).strip()
            self._Suspend(retry_count + 1)
            return
          else:
            raise IOError('EBUSY: Early wake event when attempting suspend: %s'
                          % debug_utils.FormatExceptionOnly())
      else:
        raise IOError('Failed to write to /sys/power/state: %s' %
                      debug_utils.FormatExceptionOnly())
    logging.info('Returning from suspend at %d', self._ReadCurrentTime())

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
    self.Sleep(0.1)
    line_content = file_utils.ReadFile(
        '/sys/kernel/debug/suspend_stats').strip()
    return int(re.search(r'[0-9]+', line_content).group(0))

  def _ReadCurrentTime(self):
    """Read the current time in seconds since_epoch.

    Args:
      None.

    Returns:
      Int, the time since_epoch in seconds.
    """
    return int(file_utils.ReadFile(self.args.time_path).strip())

  def _VerifySuspended(self, wake_time, wake_source, count, resume_at):
    """Verify that a reasonable suspend has taken place.

    Args:
      wake_time: the time at which the device resumed
      wake_source: the wake source, if known
      count: expected number of suspends the system has executed
      resume_at: expected time since epoch to have resumed

    Returns:
      Boolean, True if suspend was valid, False if not.
    """
    self.assertGreaterEqual(
        wake_time, resume_at - self.args.resume_early_margin_secs,
        'Premature wake detected (%d s early, source=%s), spurious event? '
        '(got touched?)' % (resume_at - wake_time, wake_source or 'unknown'))
    self.assertLessEqual(
        wake_time, resume_at + self.args.resume_worst_case_secs,
        'Late wake detected (%ds > %ds delay, source=%s), timer failure?' % (
            wake_time - resume_at, self.args.resume_worst_case_secs,
            wake_source or 'unknown'))

    actual_count = self._ReadSuspendCount()
    self.assertEqual(
        count, actual_count,
        'Incorrect suspend count: ' + (
            'no suspend?' if actual_count < count else 'spurious suspend?'))

  def _HandleMessages(self, messages_start):
    """Finds the suspend/resume chunk in /var/log/messages.

    The contents are saved to self.messages to be logged on failure.

    Returns:
      The wake source, or none if unknown.
    """
    # The last chunk we read.  In a list so it can be written from
    # ReadMessages.
    last_messages = ['']

    def ReadMessages(messages_start):
      try:
        with open(_MESSAGES) as f:
          # Read from messages_start to the end of the file.
          f.seek(messages_start)
          last_messages[0] = messages = f.read()

          # If we see this, we can consider resume to be done.
          match = re.search(
              r'\] Restarting tasks \.\.\.'  # "Restarting tasks" line
              r'.+'                          # Any number of charcaters
              r'\] done\.\n',                # "done." line
              messages, re.DOTALL | re.MULTILINE)
          if match:
            messages = messages[:match.end()]
            return messages
      except IOError:
        logging.exception('Unable to read %s', _MESSAGES)
      return None
    messages = sync_utils.Retry(10, 0.2, None, ReadMessages, messages_start)

    if not messages:
      # We never found it. Just use the entire last chunk read
      messages = last_messages[0]

    logging.info(
        'To view suspend/resume messages: '
        'dd if=/var/log/messages skip=%d count=%d '
        'iflag=skip_bytes,count_bytes', messages_start, len(messages))

    # Find the wake source
    match = re.search('active wakeup source: (.+)', messages)
    wake_source = match.group(1) if match else None
    logging.info('Wakeup source: %s', wake_source or 'unknown')

    self.messages = messages
    return wake_source

  def runTest(self):
    self.initial_suspend_count = self._ReadSuspendCount()
    logging.info('The initial suspend count is %d.', self.initial_suspend_count)

    random.seed(0)  # Make test deterministic

    for self.run in range(1, self.args.cycles + 1):
      self.attempted_wake_extensions = 0
      self.actual_wake_extensions = 0
      alarm_suspend_delays = 0
      self.alarm_thread = threading.Thread(target=self._MonitorWakealarm)
      self.ui.SetState(
          _('Suspend/Resume: {run} of {cycle}',
            run=self.run,
            cycle=self.args.cycles))
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
      messages_start = os.path.getsize(_MESSAGES)
      self._Suspend()
      wake_time = self._ReadCurrentTime()
      wake_source = self._HandleMessages(messages_start)
      self._VerifySuspended(wake_time,
                            wake_source,
                            self.initial_suspend_count + self.run,
                            self.resume_at)
      logging.info('Resumed %d of %d for %d seconds.',
                   self.run, self.args.cycles, resume_time)
      self.Sleep(resume_time)

      while self.alarm_thread.isAlive():
        alarm_suspend_delays += 1
        logging.warn('alarm thread is taking a while to return, waiting 1s.')
        self.Sleep(1)
        self.assertGreaterEqual(self.start_time +
                                self.args.suspend_worst_case_secs,
                                int(open(self.args.time_path).read().strip()),
                                'alarm thread did not return within %d sec.' %
                                self.args.suspend_worst_case_secs)
      event_log.Log('suspend_resume_cycle',
                    run=self.run, start_time=self.start_time,
                    suspend_time=suspend_time, resume_time=resume_time,
                    resume_at=self.resume_at, wakeup_count=self.wakeup_count,
                    suspend_count=self._ReadSuspendCount(),
                    initial_suspend_count=self.initial_suspend_count,
                    attempted_wake_extensions=self.attempted_wake_extensions,
                    actual_wake_extensions=self.actual_wake_extensions,
                    alarm_suspend_delays=alarm_suspend_delays,
                    wake_source=wake_source)
