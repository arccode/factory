#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import ctypes
import daemon
import lockfile
import logging
import math
import optparse
import os
import time

import factory_common
from cros.factory.test import factory


def _FormatTime(t):
  us, s = math.modf(t)
  return '%s.%06dZ' % (time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(s)),
                       int(us * 1000000))


librt = ctypes.cdll.LoadLibrary('librt.so')
class timespec(ctypes.Structure):
  _fields_ = [('tv_sec', ctypes.c_long),
              ('tv_nsec', ctypes.c_long)]


class Time(object):
  '''Time object for mocking.'''
  def Time(self):
    return time.time()

  def SetTime(self, new_time):
    logging.warn('Setting time to %s', _FormatTime(new_time))
    us, s = math.modf(new_time)
    value = timespec(int(s), int(us * 1000000))
    librt.clock_settime(0, ctypes.pointer(value))


SECONDS_PER_DAY = 86400


class TimeSanitizer(object):
  def __init__(self, state_file,
               monitor_interval_secs,
               time_bump_secs,
               max_leap_secs,
               base_time=None):
    '''Attempts to ensure that system time is monotonic and sane.

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
    '''
    self.state_file = state_file
    self.monitor_interval_secs = monitor_interval_secs
    self.time_bump_secs = time_bump_secs
    self.max_leap_secs = max_leap_secs
    self.base_time = base_time

    # Set time object.  This may be mocked out.
    self._time = Time()

    if not os.path.isdir(os.path.dirname(self.state_file)):
      os.makedirs(os.path.dirname(self.state_file))

  def Run(self):
      '''Runs forever, immediately and then every monitor_interval_secs.'''
      while True:
        try:
          self.RunOnce()
        except:
          logging.exception()

        time.sleep(self.monitor_interval_secs)

  def RunOnce(self):
    '''Runs once, returning immediately.'''
    minimum_time = self.base_time  # May be None
    if os.path.exists(self.state_file):
      try:
        minimum_time = max(minimum_time,
                           float(open(self.state_file).read().strip()))
      except:
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

    with open(self.state_file, 'w') as f:
      logging.debug('Recording current time %s into %s',
                    _FormatTime(now), self.state_file)
      print >>f, now


def _GetBaseTime(base_time_file):
  '''Returns the base time to use (the mtime of base_time_file or None).

  Never throws an exception.'''
  if os.path.exists(base_time_file):
    try:
      base_time = os.stat(base_time_file).st_mtime
      logging.info('Using %s (mtime of %s) as base time',
                   _FormatTime(base_time), base_time_file)
      return base_time
    except:
      logging.exception('Unable to stat %s', base_time_file)
  else:
    logging.warn('base-time-file %s does not exist',
                 base_time_file)
  return None


def main():
  parser = argparse.ArgumentParser(description='Ensure sanity of system time.')
  parser.add_argument('--state-file', metavar='FILE',
                      default=os.path.join(factory.get_state_root(),
                                           'time_sanitizer.state'),
                      help='file to maintain state across reboots')
  parser.add_argument('--daemon', action='store_true',
                      help=('run as a daemon (to keep known-good time '
                            'in state file up to date)')),
  parser.add_argument('--log', metavar='FILE',
                      default=os.path.join(factory.get_log_root(),
                                           'time_sanitizer.log'),
                      help='log file (if run as a daemon)')
  parser.add_argument('--monitor-interval-secs', metavar='SECS', type=int,
                      default=30,
                      help='period with which to monitor time')
  parser.add_argument('--time-bump-secs', metavar='SECS', type=int,
                      default=60,
                      help=('how far ahead to move the time '
                            'if the clock is hosed')),
  parser.add_argument('--max-leap-secs', metavar='SECS', type=int,
                      default=(SECONDS_PER_DAY * 30),
                      help=('maximum possible time leap without the clock '
                            'being considered hosed')),
  parser.add_argument('--verbose', '-v', action='store_true',
                      help='verbose log')
  parser.add_argument('--base-time-file', metavar='FILE',
                      default='/usr/local/etc/lsb-factory',
                      help=('a file whose mtime represents the minimum '
                            'possible time that can ever be seen'))
  args = parser.parse_args()

  logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                      filename=args.log if args.daemon else None)

  sanitizer = TimeSanitizer(os.path.realpath(args.state_file)
                            if args.state_file else None,
                            _GetBaseTime(args.base_time_file)
                            if args.base_time_file else None,
                            args.monitor_interval_secs,
                            args.time_bump_secs,
                            args.max_leap_secs)

  # Make sure we run once (even in daemon mode) before returning.
  sanitizer.RunOnce()

  if args.daemon:
    with daemon.DaemonContext():
      sanitizer.Run()


if __name__ == '__main__':
    main()
