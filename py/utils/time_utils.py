# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Time-related utilities."""

import datetime
import time
from uuid import uuid4

from . import platform_utils


MonotonicTime = platform_utils.GetProvider('MonotonicTime')


# pylint: disable=unused-argument
class TZUTC(datetime.tzinfo):
  """A tzinfo about UTC."""

  def utcoffset(self, dt):
    return datetime.timedelta(0)

  def dst(self, dt):
    return datetime.timedelta(0)

  def tzname(self, dt):
    return 'UTC'


def FormatElapsedTime(elapsed_secs):
  """Formats an elapsed time.

  Args:
    elapsed_secs: An integer number of seconds.

  Returns:
    The time in HH:MM:SS format.
  """
  negative = elapsed_secs < 0
  if negative:
    elapsed_secs = -elapsed_secs

  secs = elapsed_secs % 60
  elapsed_secs /= 60
  mins = elapsed_secs % 60
  elapsed_secs /= 60
  hours = elapsed_secs

  return '%s%02d:%02d:%02d' % ('-' if negative else '',
                               hours, mins, secs)


def TimeString(time_value=None, time_separator=':', milliseconds=True):
  """Returns a time as a string.

  The format is like ISO8601 but with milliseconds:

   2012-05-22T14:15:08.123Z

  Args:
    time_value: A datetime.datetime object, time in seconds since the epoch,
                or None for current time.
    time_separator: Separator for time components.
    milliseconds: Whether to include milliseconds.
  """

  if isinstance(time_value, datetime.datetime):
    t = DatetimeToUnixtime(time_value)
  else:
    t = time_value or time.time()
  ret = time.strftime(
      '%Y-%m-%dT%H' + time_separator + '%M' + time_separator + '%S',
      time.gmtime(t))
  if milliseconds:
    ret += '.%03d' % int((t - int(t)) * 1000)
  ret += 'Z'
  return ret


def TimedUUID():
  """Returns a UUID that is roughly sorted by time.

  The first 8 hexits are replaced by the current time in 100ths of a
  second, mod 2**32.  This will roll over once every 490 days, but it
  will cause UUIDs to be sorted by time in the vast majority of cases
  (handy for ls'ing directories); and it still contains far more than
  enough randomness to remain unique.
  """
  return ('%08x' % (int(time.time() * 100) & 0xFFFFFFFF) +
          str(uuid4())[8:])


EPOCH_ZERO = datetime.datetime(1970, 1, 1)
EPOCH_ZERO_WITH_TZINFO = datetime.datetime(1970, 1, 1, tzinfo=TZUTC())


def DatetimeToUnixtime(obj):
  """Converts datetime.datetime to Unix time.

  The function will use the time zone info if obj has; otherwise, it will treat
  obj as in Coordinated Universal Time (UTC).
  """
  if not isinstance(obj, datetime.datetime):
    raise ValueError('Expected datetime.datetime but found %s' % type(obj))
  if obj.tzinfo is not None:
    return (obj - EPOCH_ZERO_WITH_TZINFO).total_seconds()
  return (obj - EPOCH_ZERO).total_seconds()
