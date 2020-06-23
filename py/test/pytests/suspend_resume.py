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
- rtc's ``wakealarm`` entry in ``sysfs``.
- ``check_powerd_config`` if the argument ``suspend_type`` is not set.

Note that the rtc sysfs entry may vary from device to device, so the test_list
must define the path to the correct sysfs entry for the specific device, the
default assumes a typical ``/sys/class/rtc/rtc0`` entry.

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

from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import debug_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils

_MIN_SUSPEND_MARGIN_SECS = 5

_MESSAGES = '/var/log/messages'

_WAKEUP_PATH = '/sys/class/wakeup'
_KERNEL_DEBUG_SUSPEND_STATS = '/sys/kernel/debug/suspend_stats'
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
      Arg('suspend_type', str,
          'Suspend type.  The default is to use ``freeze`` if the platform '
          'supports it, or ``mem`` for other cases.',
          default=None),
      Arg('ignore_wakeup_source', str, 'Wakeup source to ignore',
          default=None),
      Arg('early_resume_retry_wait_secs', int,
          'Time to wait before re-suspending after early resume',
          default=3),
      Arg('ensure_wakealarm_cleared', bool,
          'Raise exception if wakealarm is not cleared after resume',
          default=True)]

  def setUp(self):
    self.assertTrue(os.path.exists(_WAKEUP_PATH),
                    'wakeup_sources file not found.')
    self.assertTrue(os.path.exists(_KERNEL_DEBUG_SUSPEND_STATS),
                    'suspend_stats file not found.')
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

    self.goofy = state.GetInstance()

    self.ui.ToggleTemplateClass('font-large', True)

    self.done = False
    self.suspend_type = None
    self.wakeup_count = ''
    self.wakeup_source_event_count = {}
    self.start_time = 0
    self.resume_at = 0
    self.attempted_wake_extensions = 0
    self.actual_wake_extensions = 0
    self.initial_suspend_count = 0
    self.alarm_started = threading.Event()
    self.alarm_thread = None
    self.messages = None
    # Group checker for Testlog.
    self.group_checker = testlog.GroupParam(
        'suspend_resume_cycle',
        ['run', 'start_time', 'suspend_time', 'resume_time', 'resume_at',
         'wakeup_count', 'suspend_count', 'initial_suspend_count',
         'attempted_wake_extensions', 'actual_wake_extensions',
         'alarm_suspend_delays', 'wake_source'])

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
    if self.alarm_thread:
      self.alarm_thread.join(5)
      self.assertFalse(self.alarm_thread.isAlive(), 'Alarm thread failed join.')
    # Clear any active wake alarms
    self._SetWakealarm('0')

  @staticmethod
  def _ReadAndCastFileSafely(path, return_type=str):
    try:
      text = file_utils.ReadFile(path)
    except IOError as err:
      logging.info('Reading %s failed. Error: %s', path, err)
      return None
    try:
      return return_type(text)
    except ValueError as err:
      logging.info('Casting %s to %r failed. Error: %s', text, return_type, err)
      return None

  def _GetWakeupSourceCounts(self):
    """Return snapshot of current event counts.

    Returns:
      Dictionary, key is sysfs path and value is its event_count.
    """
    wakeup_sources = [os.path.join(_WAKEUP_PATH, name)
                      for name in os.listdir(_WAKEUP_PATH)]
    return {wakeup_source: self._ReadAndCastFileSafely(
        os.path.join(wakeup_source, 'event_count'), int)
            for wakeup_source in wakeup_sources}

  def _GetPossibleWakeupSources(self):
    """Return all possible wakeup sources that may cause the wake.

    After writing to self.wakeup_count, the event count of any wakeup source
    which tries to wake up the device will increase.

    Returns:
      Dictionary, key is sysfs path and value is its name.
    """
    wake_sources = {}
    current_wakeup_source_event_count = self._GetWakeupSourceCounts()
    sources = (set(current_wakeup_source_event_count) |
               set(self.wakeup_source_event_count))
    for wakeup_source in sources:
      snapshot_event_count = self.wakeup_source_event_count.get(wakeup_source)
      current_event_count = current_wakeup_source_event_count.get(wakeup_source)
      if snapshot_event_count == current_event_count:
        continue
      name = (self._ReadAndCastFileSafely(
          os.path.join(wakeup_source, 'name')) or 'unknown').strip()
      if snapshot_event_count is None or current_event_count is None:
        logging.info('wakeup_source %s(%r) %sappeared after suspend.',
                     wakeup_source, name,
                     'dis' if current_event_count is None else '')
      else:
        wake_sources.update({wakeup_source: name})
    return wake_sources

  def _MonitorWakealarm(self):
    """Start and extend the wakealarm as needed for the main thread."""
    self._SetWakealarm(str(self.resume_at))
    self.alarm_started.set()
    self.Sleep(_MIN_SUSPEND_MARGIN_SECS)  # Wait for suspend.
    # The loop below will be run after resume, or when the device doesn't
    # suspend in _MIN_SUSPEND_MARGIN_SECS seconds.
    while not self.done:
      self.Sleep(0.5)  # Wait for suspend_stats to get updated after resume.
      if self._ReadSuspendCount() >= self.initial_suspend_count + self.run:
        break
      # A normal suspend-resume should not get here.
      cur_time = self._ReadCurrentTime()
      if cur_time >= self.resume_at - 1:
        self.attempted_wake_extensions += 1
        logging.warning('Late suspend detected, attempting wake extension.')
        try:
          self._SetWakealarm('+=%d' % _MIN_SUSPEND_MARGIN_SECS)
        except IOError:
          # This happens when the device actually suspends and resumes but
          # suspend_stats is not updated yet, or when the device hangs for a
          # while and suspends just before we try to extend the wake time.
          logging.warning('Write to wakealarm failed, assuming we woke.')
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
    self.alarm_started.clear()

  def _Suspend(self, retry_count=0):
    """Suspend the device by writing to /sys/power/state.

    First write to wakeup_count, then write to /sys/power/state. See
    kernel/power/main.c for detailed description.
    """
    # Explicitly sync the filesystem
    process_utils.Spawn(['sync'], check_call=True, log_stderr_on_error=True)

    self.wakeup_source_event_count = self._GetWakeupSourceCounts()
    logging.info('Suspending at %d.', self._ReadCurrentTime())

    try:
      # Write out the expected wakeup_count. Wakeup_count is a mechanism to
      # handle wakeup events in a non-racy way. The write could fail with
      # EINVAL if another wakeup event occurred since the last read of
      # wakeup_count, and we should not write to /sys/power/state if this
      # happens.
      logging.info('Writing "%s" to wakeup_count.', self.wakeup_count)
      file_utils.WriteFile(self.args.wakeup_count_path, self.wakeup_count)
    except IOError as err:
      if err.errno == errno.EINVAL:
        wake_sources = self._GetPossibleWakeupSources()
        raise IOError('EINVAL: Failed to write to wakeup_count. Maybe there is '
                      'another program trying to suspend at the same time?'
                      'source=%r' % wake_sources)
      raise IOError('Failed to write to wakeup_count: %s' %
                    debug_utils.FormatExceptionOnly())

    try:
      # Suspend to memory. The write could fail with EBUSY if another wakeup
      # event occurred since the last write to /sys/power/wakeup_count.
      logging.info('Writing "%s" to /sys/power/state.', self.suspend_type)
      file_utils.WriteFile('/sys/power/state', self.suspend_type)
    except IOError as err:
      if err.errno == errno.EBUSY:
        logging.info('Early wake event when attempting suspend.')
        wake_sources = self._GetPossibleWakeupSources()
        if self.args.ignore_wakeup_source in wake_sources:
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
        raise IOError('EBUSY: Early wake event when attempting suspend: %s, '
                      'source=%r' %
                      (debug_utils.FormatExceptionOnly(), wake_sources))
      raise IOError('Failed to write to /sys/power/state: %s' %
                    debug_utils.FormatExceptionOnly())
    logging.info('Returning from suspend at %d.', self._ReadCurrentTime())

  def _ReadSuspendCount(self):
    """Read the current suspend count from /sys/kernel/debug/suspend_stats.
    This assumes the first line of suspend_stats contains the number of
    successfull suspend cycles.

    Args:
      None.

    Returns:
      Int, the number of suspends the system has executed since last reboot.
    """
    line_content = file_utils.ReadFile(_KERNEL_DEBUG_SUSPEND_STATS).strip()
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

  def _SetWakealarm(self, content, raise_exception=True):
    """Set wakealarm by writing a string to wakealarm file.

    See drivers/rtc/rtc-sysfs.c for detailed implementation for setting
    wakealarm value.

    Args:
      content: the string to write to wakealarm file. It can be
        TIME: Set the wakealarm time to TIME, where TIME is in seconds since
              epoch. If TIME is earlier than current time, the write will clear
              the active wakealarm. If TIME is later then current time and there
              is an active wakealarm, the write fails and raises IOError
              (EBUSY).
        +TIME: Set the wakealarm time to (current time + TIME seconds). If
               there is an active wakealarm, the write fails and raises IOError
               (EBUSY).
        +=TIME: Extend the wakealarm time by TIME seconds. If there is no
                active wakealarm, the write fails with IOError (EINVAL).
      raise_exception: True to raise IOError when writing to wakealarm file
                       fails.

    Raises:
      IOError: when raise_exception is True and writing to wakealarm file fails.
    """
    try:
      logging.info('Writing "%s" to %s.', content, self.args.wakealarm_path)
      file_utils.WriteFile(self.args.wakealarm_path, content)
    except IOError:
      error_msg = 'Failed to write to wakealarm.'
      if raise_exception:
        raise IOError(error_msg)
      logging.warning(error_msg)

  def _VerifyWakealarmCleared(self, raise_exception=True):
    """Verify that wakealarm is cleared after resume.

    Wakealarm should be cleared after resume, but sometimes it isn't cleared
    and will cause write error at next suspend (b/120858506). Report warnings
    or raise an exception if wakealarm is not cleared, and always explicitly
    clear it again to make sure we can set wakealarm at next suspend.

    Args:
      raise_exception: True to raise an exception if wakealarm is not cleared,
                       otherwise only show warning message.

    Raises:
      RuntimeError: If raise_exception is True and wakealarm is not cleared.
    """
    content = file_utils.ReadFile(self.args.wakealarm_path).strip()
    if content:
      error_msg = 'Wakealarm is not cleared after resume, value: %s.' % content
      if raise_exception:
        raise RuntimeError(error_msg)
      logging.warning(error_msg)
    self._SetWakealarm('0')

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
        logging.exception('Unable to read %s.', _MESSAGES)
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
    wake_source = self._GetPossibleWakeupSources()
    logging.info('Wakeup source: %s.', wake_source or 'unknown')

    self.messages = messages
    return wake_source

  def _ResolveSuspendType(self):
    if self.args.suspend_type:
      self.suspend_type = self.args.suspend_type
    else:
      logging.info(
          'Suspend type is not specified, auto-detect the supported one.')
      retcode = process_utils.Spawn(
          ['check_powerd_config', '--suspend_to_idle'], log=True,
          call=True).returncode
      self.suspend_type = 'freeze' if retcode == 0 else 'mem'
      session.console.info('Set the suspend type to %r.', self.suspend_type)

  def runTest(self):
    self._ResolveSuspendType()
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
      self.wakeup_count = file_utils.ReadFile(
          self.args.wakeup_count_path).strip()
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
      self._VerifyWakealarmCleared(
          raise_exception=self.args.ensure_wakealarm_cleared)
      logging.info('Resumed %d of %d for %d seconds.',
                   self.run, self.args.cycles, resume_time)
      self.Sleep(resume_time)

      while self.alarm_thread.isAlive():
        alarm_suspend_delays += 1
        logging.warning('alarm thread is taking a while to return, waiting 1s.')
        self.Sleep(1)
        self.assertGreaterEqual(self.start_time +
                                self.args.suspend_worst_case_secs,
                                self._ReadCurrentTime(),
                                'alarm thread did not return within %d sec.' %
                                self.args.suspend_worst_case_secs)
      suspend_count = self._ReadSuspendCount()
      event_log.Log('suspend_resume_cycle',
                    run=self.run, start_time=self.start_time,
                    suspend_time=suspend_time, resume_time=resume_time,
                    resume_at=self.resume_at, wakeup_count=self.wakeup_count,
                    suspend_count=suspend_count,
                    initial_suspend_count=self.initial_suspend_count,
                    attempted_wake_extensions=self.attempted_wake_extensions,
                    actual_wake_extensions=self.actual_wake_extensions,
                    alarm_suspend_delays=alarm_suspend_delays,
                    wake_source=wake_source)
      with self.group_checker:
        testlog.LogParam('run', self.run)
        testlog.LogParam('start_time', self.start_time)
        testlog.LogParam('suspend_time', suspend_time)
        testlog.LogParam('resume_time', resume_time)
        testlog.LogParam('resume_at', self.resume_at)
        testlog.LogParam('wakeup_count', self.wakeup_count)
        testlog.LogParam('suspend_count', suspend_count)
        testlog.LogParam('initial_suspend_count', self.initial_suspend_count)
        testlog.LogParam('attempted_wake_extensions',
                         self.attempted_wake_extensions)
        testlog.LogParam('actual_wake_extensions', self.actual_wake_extensions)
        testlog.LogParam('alarm_suspend_delays', alarm_suspend_delays)
        testlog.LogParam('wake_source', wake_source)
