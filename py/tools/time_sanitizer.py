#!/usr/bin/env python
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import ctypes
from ctypes.util import find_library
import logging
import math
import os
import threading
import time
from urlparse import urlparse

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test import server_proxy
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils.type_utils import Error


def _FormatTime(t):
  us, s = math.modf(t)
  return '%s.%06dZ' % (time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(s)),
                       int(us * 1000000))


librt_name = find_library('rt')
librt = ctypes.cdll.LoadLibrary(librt_name)


class timespec(ctypes.Structure):
  _fields_ = [('tv_sec', ctypes.c_long),
              ('tv_nsec', ctypes.c_long)]


class Time(object):
  """Time object for mocking."""

  def __init__(self):
    self.lock = threading.RLock()

  def Time(self):
    return time.time()

  def SetTime(self, new_time=None):
    new_time = new_time or self.Time()
    logging.warn('Setting time to %s', _FormatTime(new_time))
    us, s = math.modf(new_time)
    value = timespec(int(s), int(us * 1000000))
    librt.clock_settime(0, ctypes.pointer(value))

    # Set hwclock after we set time(in a background thread, since this is slow).
    self.RequestCheckHwClock()

  def RequestCheckHwClock(self):
    process_utils.StartDaemonThread(target=self._CheckHwclock)

  def _CheckHwclock(self):
    """Check hwclock is working by a write(retry once if fail) and a read."""
    with self.lock:
      for _ in xrange(2):
        if process_utils.Spawn(['hwclock', '-w', '--utc', '--noadjfile'],
                               log=True,
                               log_stderr_on_error=True).returncode == 0:
          break
        else:
          logging.error('Unable to set hwclock time')

      logging.info('Current hwclock time: %s',
                   process_utils.Spawn(['hwclock', '-r'], log=True,
                                       read_stdout=True).stdout_data)

SECONDS_PER_DAY = 86400


class TimeSanitizer(object):

  def __init__(self,
               state_file=os.path.join(paths.DATA_STATE_DIR,
                                       'time_sanitizer_base_time'),
               monitor_interval_secs=30,
               time_bump_secs=60,
               max_leap_secs=(SECONDS_PER_DAY * 30),
               base_time=None):
    """Attempts to ensure that system time is monotonic and sane.

    Guarantees that:

    - The system time is never less than any other time seen
      while the monoticizer is alive (even after a reboot).
    - The system time is never less than base_time, if provided.
    - The system time never leaps forward more than max_leap_secs,
      e.g., to a nonsense time like 20 years in the future.

    When an insane time is observed, the current time is set to the
    last known time plus time_bump_secs.  For this reason
    time_bump_secs should be greater than monitor_interval_secs.

    Args/Properties:
      state_file: A file used to store persistent state across
        reboots (currently just the maximum time ever seen,
        plus time_bump_secs).
      monitor_interval_secs: The frequency at which to poll the
        system clock and ensure sanity.
      time_bump_secs: How far ahead the time should be moved past
        the last-seen-good time if an insane time is observed.
      max_leap_secs: How far ahead the time may increment without
        being considered insane.
      base_time: A time that is known to be earlier than the current
        time.
    """
    self.state_file = state_file
    self.monitor_interval_secs = monitor_interval_secs
    self.time_bump_secs = time_bump_secs
    self.max_leap_secs = max_leap_secs
    self.base_time = base_time
    self.lock = threading.RLock()

    # Whether to avoid re-raising exceptions from unsuccessful factory server
    # operations.  Set to False for testing.
    self.__exceptions = True
    # Set time object.  This may be mocked out.
    self._time = Time()

    file_utils.TryMakeDirs(os.path.dirname(self.state_file))

    # Set hwclock (in a background thread, since this is slow).
    # Do this upon startup to ensure hwclock is working
    self._time.RequestCheckHwClock()

  def Run(self):
    """Runs forever, immediately and then every monitor_interval_secs."""
    while True:
      try:
        self.RunOnce()
      except Exception:
        logging.exception('Exception in run loop')

      time.sleep(self.monitor_interval_secs)

  def RunOnce(self):
    """Runs once, returning immediately."""
    minimum_time = self.base_time  # May be None
    if os.path.exists(self.state_file):
      try:
        minimum_time = max(minimum_time,
                           float(open(self.state_file).read().strip()))
      except Exception:
        logging.exception('Unable to read %s', self.state_file)
    else:
      logging.warn('State file %s does not exist', self.state_file)

    now = self._time.Time()

    if minimum_time is None:
      minimum_time = now
      logging.warn('No minimum time or base time provided; assuming '
                   'current time (%s) is correct.',
                   _FormatTime(now))
    else:
      sane_time = minimum_time + self.time_bump_secs
      if now < minimum_time:
        logging.warn('Current time %s is less than minimum time %s; '
                     'assuming clock is hosed',
                     _FormatTime(now), _FormatTime(minimum_time))
        self._time.SetTime(sane_time)
        now = sane_time
      elif now > minimum_time + self.max_leap_secs:
        logging.warn(
            'Current time %s is too far past %s; assuming clock is hosed',
            _FormatTime(now), _FormatTime(minimum_time + self.max_leap_secs))
        self._time.SetTime(sane_time)
        now = sane_time

    self.SaveTime(now)

  def SaveTime(self, now=None):
    """Writes the current time to the state file.

    Thread-safe.

    Args:
      now: The present time if already known.  If None, time.time() will be
        used.
    """
    with self.lock:
      with open(self.state_file, 'w') as f:
        now = now or self._time.Time()
        logging.debug('Recording current time %s into %s',
                      _FormatTime(now), self.state_file)
        print >> f, now

  def SyncWithFactoryServerHtpdate(self):
    """Attempts to synchronize the clock with the factory server.

    Using built-in command htpdate -s -t <server-url>

    Raises:
      Error if sync time failed.
    """
    server_ip_port = urlparse(server_proxy.GetServerURL()).netloc
    try:
      synced = process_utils.Spawn(['htpdate', '-s', '-t', server_ip_port],
                                   log=True, call=True,
                                   log_stderr_on_error=True).returncode == 0
      if not synced:
        raise Error('cannot sync time successfully with htpdate.')

      self._time.SetTime()
      self.SaveTime()
    except OSError:
      raise Error('htpdate is not installed.')


def GetBaseTimeFromFile(*base_time_files):
  """Returns the base time to use.

  This will be the mtime of the first existing file in
  base_time_files, or None.

  Never throws an exception."""
  for f in base_time_files:
    if os.path.exists(f):
      try:
        base_time = os.stat(f).st_mtime
        logging.info('Using %s (mtime of %s) as base time',
                     _FormatTime(base_time), f)
        return base_time
      except Exception:
        logging.exception('Unable to stat %s', f)
    else:
      logging.warn('base-time-file %s does not exist', f)
  return None


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
      description='set current time from lsb-factory or lsb-release')
  parser.add_argument('--run-once', action='store_true', default=False,
                      help='run only once and exit')
  parser.add_argument('--monitor-interval', metavar='SECS', type=int,
                      default=30, help='the frequency at which to poll '
                      'the system clock and ensure sanity.')
  parser.add_argument('--time-bump', metavar='SECS', type=int,
                      default=60, help='how far ahead the time should be '
                      'moved past the last-seen-good time if an insane time '
                      'is observed.')
  parser.add_argument('--max-leap', metavar='SECS', type=int,
                      default=(SECONDS_PER_DAY * 30),
                      help='how far ahead the time may increment without '
                      'being considered insane.')

  args = parser.parse_args()

  time_sanitizer = TimeSanitizer(
      monitor_interval_secs=args.monitor_interval,
      time_bump_secs=args.time_bump,
      max_leap_secs=args.max_leap,
      base_time=GetBaseTimeFromFile(
          # lsb-factory is written by the factory install shim during
          # installation, so it should have a good time obtained from
          # the Factory Server.  If it's not available, we'll use
          # /etc/lsb-factory (which will be much older, but reasonably
          # sane) and rely on a sync to factory server to set a more accurate
          # time.
          '/usr/local/etc/lsb-factory',
          '/etc/lsb-release'))

  if args.run_once:
    time_sanitizer.RunOnce()
  else:
    time_sanitizer.Run()
