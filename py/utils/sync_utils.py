# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Syncronization-related utilities (waiting for state change)."""

from __future__ import print_function

import inspect
import logging
import time

import factory_common  # pylint: disable=W0611
from cros.factory.utils import time_utils
from cros.factory.utils import type_utils


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
    type_utils.TimeoutError when timeout is reached but condition has not yet
        been met.
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
      raise type_utils.TimeoutError(condition_name)
    time.sleep(poll_interval_secs)


def Retry(max_retry_times, interval, callback, target, *args, **kwargs):
  """Retries a function call with limited times until it returns True.

  Args:
    max_retry_times: The max retry times for target function to return True.
    interval: The sleep interval between each trial.
    callback: The callback after each retry iteration. Caller can use this
              callback to track progress. Callback should accept two arguments:
              callback(retry_time, max_retry_times).
    target: The target function for retry. *args and **kwargs will be passed to
            target.

  Returns:
    Within max_retry_times, if the return value of target function is
    neither None nor False, returns the value.
    If target function returns False or None or it throws
    any exception for max_retry_times, returns None.
  """
  result = None
  for retry_time in xrange(max_retry_times):
    try:
      result = target(*args, **kwargs)
    except Exception: # pylint: disable=W0703
      logging.exception('Retry...')
    if(callback):
      callback(retry_time, max_retry_times)
    if result:
      logging.info('Retry: Get result in retry_time: %d.', retry_time)
      break
    time.sleep(interval)
  return result


def WaitFor(condition, timeout_secs, poll_interval=0.1):
  """Wait for the given condition for at most the specified time.

  Args:
    condition: A function object.
    timeout_secs: Timeout value in seconds.
    poll_interval: Interval to poll condition.

  Raises:
    ValueError: If condition is not a function.
    TimeoutError: If cond does not become True after timeout_secs seconds.
  """
  if not callable(condition):
    raise ValueError('condition must be a callable object')

  def _GetConditionString():
    condition_string = condition.__name__
    if condition.__name__ == '<lambda>':
      try:
        condition_string = inspect.getsource(condition).strip()
      except IOError:
        pass
    return condition_string

  end_time = time.time() + timeout_secs
  while True:
    if condition():
      break
    if time.time() > end_time:
      raise type_utils.TimeoutError(
          'Timeout waiting for %r' % _GetConditionString())
    time.sleep(poll_interval)
