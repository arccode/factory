# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Syncronization-related utilities (waiting for state change)."""

from __future__ import print_function

import logging
import time

import factory_common  # pylint: disable=W0611
from cros.factory.common import TimeoutError
from cros.factory.utils import time_utils


DEFAULT_TIMEOUT = 10
DEFAULT_POLL_INTERVAL = 0.1


def PollForCondition(poll_method, condition_method=None,
                     timeout=DEFAULT_TIMEOUT,
                     poll_interval_secs=DEFAULT_POLL_INTERVAL,
                     condition_name=None):
  """Polls for every poll_interval_secs until timeout reached or condition met.

  It is a blocking call. If the condition is met, poll_method's return value
  is passed onto the caller. Otherwise, a TimeoutError is raised.

  Args:
    poll_method: a method to be polled. The method's return value will be passed
        into condition_method.
    condition_method: a method to decide if poll_method's return value is valid.
        None for standard Python if statement.
    timeout: maximum number of seconds to wait, None means forever.
    poll_interval_secs: interval to poll condition.
    condition_name: description of the condition. Used for TimeoutError when
        timeout is reached.

  Returns:
    poll_method's return value.

  Raises:
    TimeoutError when timeout is reached but condition has not yet been met.
  """
  if condition_method == None:
    condition_method = lambda ret: ret
  end_time = time_utils.MonotonicTime() + timeout if timeout else None
  while True:
    ret = poll_method()
    if condition_method(ret):
      return ret
    if ((end_time is not None) and
        (time_utils.MonotonicTime() + poll_interval_secs > end_time)):
      if condition_name:
        condition_name = 'Timed out waiting for condition: %s' % condition_name
      else:
        condition_name = 'Timed out waiting for unnamed condition'
      logging.error(condition_name)
      raise TimeoutError(condition_name)
    time.sleep(poll_interval_secs)
