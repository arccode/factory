# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Syncronization-related utilities (waiting for state change)."""

from contextlib import contextmanager
import functools
import inspect
import logging
import queue
import signal
import threading
import time
import _thread

from . import thread_utils
from . import time_utils
from . import type_utils

_HAVE_CTYPES = True
try:
  # pylint: disable=wrong-import-order,wrong-import-position
  import ctypes
except Exception:
  _HAVE_CTYPES = False


DEFAULT_TIMEOUT_SECS = 10
DEFAULT_POLL_INTERVAL_SECS = 0.1


_DEFAULT_POLLING_SLEEP_FUNCTION = time.sleep
_POLLING_SLEEP_FUNCTION_KEY = 'sync_utils_polling_sleep_function'


def _GetPollingSleepFunction():
  return thread_utils.LocalEnv().get(_POLLING_SLEEP_FUNCTION_KEY,
                                     _DEFAULT_POLLING_SLEEP_FUNCTION)


@contextmanager
def WithPollingSleepFunction(sleep_func):
  """Set the function to be used to sleep for PollForCondition and Retry.

  Note that the Timeout() context manager is not affected by this.

  Args:
    sleep_func: A function whose only argument is number of seconds to sleep.
  """
  with thread_utils.SetLocalEnv(**{_POLLING_SLEEP_FUNCTION_KEY: sleep_func}):
    yield


def PollForCondition(poll_method, condition_method=None,
                     timeout_secs=DEFAULT_TIMEOUT_SECS,
                     poll_interval_secs=DEFAULT_POLL_INTERVAL_SECS,
                     condition_name=None):
  """Polls for every poll_interval_secs until timeout reached or condition met.

  It is a blocking call. If the condition is met, poll_method's return value
  is passed onto the caller. Otherwise, a TimeoutError is raised.

  Args:
    poll_method: a method to be polled. The method's return value will be passed
        into condition_method.
    condition_method: a method to decide if poll_method's return value is valid.
        None for standard Python if statement.
    timeout_secs: maximum number of seconds to wait, None means forever.
    poll_interval_secs: interval to poll condition.
    condition_name: description of the condition. Used for TimeoutError when
        timeout_secs is reached.

  Returns:
    poll_method's return value.

  Raises:
    type_utils.TimeoutError when timeout_secs is reached but condition has not
        yet been met.
  """
  if condition_method is None:
    condition_method = lambda ret: ret
  end_time = time_utils.MonotonicTime() + timeout_secs if timeout_secs else None
  sleep = _GetPollingSleepFunction()
  while True:
    if condition_name and end_time is not None:
      logging.debug('[%ds left] %s', end_time - time_utils.MonotonicTime(),
                    condition_name)
    ret = poll_method()
    if condition_method(ret):
      return ret
    if ((end_time is not None) and
        (time_utils.MonotonicTime() + poll_interval_secs > end_time)):
      if condition_name:
        msg = 'Timed out waiting for condition: %s' % condition_name
      else:
        msg = 'Timed out waiting for unnamed condition'
      logging.info(msg)
      raise type_utils.TimeoutError(msg, ret)
    sleep(poll_interval_secs)


def WaitFor(condition, timeout_secs, poll_interval=DEFAULT_POLL_INTERVAL_SECS):
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

  return PollForCondition(poll_method=condition,
                          timeout_secs=timeout_secs,
                          poll_interval_secs=poll_interval,
                          condition_name=_GetConditionString())


def QueueGet(q, timeout=None,
             poll_interval_secs=DEFAULT_POLL_INTERVAL_SECS):
  """Get from a queue.Queue, possibly by polling.

  This is useful when a custom polling sleep function is set.
  """
  if _GetPollingSleepFunction() is _DEFAULT_POLLING_SLEEP_FUNCTION:
    return q.get(timeout=timeout)

  def _Poll():
    try:
      return (True, q.get_nowait())
    except queue.Empty:
      return (False, None)

  try:
    return PollForCondition(
        _Poll,
        condition_method=lambda ret: ret[0],
        timeout_secs=timeout,
        poll_interval_secs=poll_interval_secs)[1]
  except type_utils.TimeoutError:
    raise queue.Empty


def EventWait(event, timeout=None,
              poll_interval_secs=DEFAULT_POLL_INTERVAL_SECS):
  """Wait for a threading.Event, possibly by polling.

  This is useful when a custom polling sleep function is set.
  """
  if _GetPollingSleepFunction() is _DEFAULT_POLLING_SLEEP_FUNCTION:
    return event.wait(timeout=timeout)

  try:
    return PollForCondition(
        event.is_set,
        timeout_secs=timeout,
        poll_interval_secs=poll_interval_secs)
  except type_utils.TimeoutError:
    return False


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
  sleep = _GetPollingSleepFunction()
  for retry_time in range(max_retry_times):
    try:
      result = target(*args, **kwargs)
    except Exception:
      logging.exception('Retry...')
    if callback:
      callback(retry_time, max_retry_times)
    if result:
      logging.info('Retry: Get result in retry_time: %d.', retry_time)
      break
    sleep(interval)
  return result


def Timeout(secs, use_signal=False):
  """Timeout context manager.

  It will raise TimeoutError after timeout is reached, interrupting execution
  of the thread.  Since implementation `ThreadTimeout` is more powerful than
  `SignalTimeout` in most cases, by default, ThreadTimeout will be used.

  You can force using SignalTimeout by setting `use_signal` to True.

  Example::

    with Timeout(0.5):
      # script in this block has to be done in 0.5 seconds

  Args:
    secs: Number of seconds to wait before timeout.
    use_signal: force using SignalTimeout (implemented by signal.alarm)
  """
  if not _HAVE_CTYPES or use_signal:
    return SignalTimeout(secs)
  return ThreadTimeout(secs)


def WithTimeout(secs, use_signal=False):
  """Function decoractor that adds a limited execution time to the function.

  Please see `Timeout`

  Example::

    @WithTimeout(0.5)
    def func(a, b, c):  # execution time of func will be limited to 0.5 seconds
      ...
  """
  def _Decorate(func):
    @functools.wraps(func)
    def _Decoracted(*func_args, **func_kwargs):
      with Timeout(secs, use_signal):
        return func(*func_args, **func_kwargs)
    return _Decoracted
  return _Decorate


@contextmanager
def SignalTimeout(secs):
  """Timeout context manager.

  It will raise TimeoutError after timeout is reached, interrupting execution
  of the thread.  It does not support nested "with Timeout" blocks, and can only
  be used in the main thread of Python.

  Args:
    secs: Number of seconds to wait before timeout.

  Raises:
    TimeoutError if timeout is reached before execution has completed.
    ValueError if not run in the main thread.
  """
  def handler(signum, frame):
    del signum, frame  # Unused.
    raise type_utils.TimeoutError('Timeout')

  if secs:
    old_handler = signal.signal(signal.SIGALRM, handler)
    prev_secs = signal.alarm(secs)
    assert not prev_secs, 'Alarm was already set before.'

  try:
    yield
  finally:
    if secs:
      signal.alarm(0)
      signal.signal(signal.SIGALRM, old_handler)


def Synchronized(f):
  """Decorates a member function to run with a lock

  The decorator is for Synchronizing member functions of a class object. To use
  this decorator, the class must initialize self._lock as threading.RLock in
  its constructor.

  Example:

  class MyServer:
    def __init__(self):
      self._lock = threading.RLock()

    @sync_utils.Synchronized
    def foo(self):
      ...

    @sync_utils.Synchronized
    def bar(self):
      ...

  """

  @functools.wraps(f)
  def wrapped(self, *args, **kw):
    # pylint: disable=protected-access
    if not self._lock or not isinstance(self._lock, _thread.RLock):
      raise RuntimeError(
          ("To use @Synchronized, the class must initialize self._lock as"
           " threading.RLock in its __init__ function."))

    with self._lock:
      return f(self, *args, **kw)
  return wrapped


class ThreadTimeout:
  """Timeout context manager.

  It will raise TimeoutError after timeout is reached, interrupting execution
  of the thread.

  Args:
    secs: Number of seconds to wait before timeout.

  Raises:
    TimeoutError if timeout is reached before execution has completed.
    ValueError if not run in the main thread.
  """
  def __init__(self, secs):
    self._secs = secs
    self._timer = None
    self._current_thread = threading.current_thread().ident
    self._lock = threading.RLock()

  def __enter__(self):
    with self._lock:
      self.SetTimeout()
    return self

  def __exit__(self, exc_type, exc_value, exc_traceback):
    with self._lock:
      self.CancelTimeout()
      return False

  def SetTimeout(self):
    if self._secs:
      self._timer = threading.Timer(self._secs, self._RaiseTimeoutException)
      self._timer.start()

  def CancelTimeout(self):
    with self._lock:
      if self._timer:
        self._timer.cancel()
      logging.debug('timer cancelled')

  def _RaiseTimeoutException(self):
    with self._lock:
      logging.debug('will raise exception')
      TryRaiseExceptionInThread(self._current_thread, type_utils.TimeoutError)


def TryRaiseExceptionInThread(thread_id, exception_class):
  """Try to raise an exception in a thread.

  This relies on cpython internal, does not guarantee to work and is generally
  a bad idea to do. So this function should only be used for exception that is
  "nice to have", but not necessary.

  Args:
    thread_id: The thread id of the thread, can be obtained by thread.ident.
    exception_class: The class of the exception to be thrown. Only exception
        class can be set, but not exception instance due to limit of cpython
        API.
  """
  num_modified_threads = ctypes.pythonapi.PyThreadState_SetAsyncExc(
      ctypes.c_long(thread_id), ctypes.py_object(exception_class))
  if num_modified_threads == 0:
    # thread ID is invalid, maybe the thread no longer exists?
    raise ValueError('Invalid thread ID')
  if num_modified_threads > 1:
    # somehow, more than one threads are modified, try to undo
    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread_id), None)
    raise SystemError('PthreadState_SetAsyncExc failed')
