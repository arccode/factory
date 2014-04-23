# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Time-related utilities."""

import ctypes
import os


def MonotonicTime():
  """Gets the raw monotonic time.

  This function opens librt.so with ctypes and call:

    int clock_gettime(clockid_t clk_id, struct timespec *tp);

  to get raw monotonic time.
  """
  CLOCK_MONOTONIC_RAW = 4

  class TimeSpec(ctypes.Structure):
    """A representation of struct timespec in C."""
    _fields_ = [
        ('tv_sec', ctypes.c_long),
        ('tv_nsec', ctypes.c_long),
    ]

  librt = ctypes.CDLL('librt.so.1', use_errno=True)
  clock_gettime = librt.clock_gettime
  clock_gettime.argtypes = [ctypes.c_int, ctypes.POINTER(TimeSpec)]
  t = TimeSpec()
  if clock_gettime(CLOCK_MONOTONIC_RAW, ctypes.pointer(t)) != 0:
    errno = ctypes.get_errno()
    raise OSError(errno, os.strerror(errno))
  return t.tv_sec + 1e-9 * t.tv_nsec


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

  return "%s%02d:%02d:%02d" % ('-' if negative else '',
                               hours, mins, secs)
