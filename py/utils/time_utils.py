# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Time-related utilities."""


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
