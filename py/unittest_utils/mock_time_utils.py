# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Fake time to be used in unittest using mock library."""

import inspect
from itertools import count
import queue
import threading
import time
from unittest import mock

from cros.factory.utils import time_utils
from cros.factory.utils import type_utils


class TimeLine:
  """A timeline class.

  This class implements a fake "time line" that unit test can register event on
  a particular time, and advance the time.

  This class is not multithread safe and should only be used when there's only
  one thread to test.
  """
  def __init__(self):
    self._fake_time = 0
    self._events = queue.PriorityQueue()
    self._unique_id = count()

  def AddEvent(self, time_at, event_func):
    """Add an event that would happen at a particular time.

    The event_func should NOT call any operation that blocks (For example,
    stubbed time.sleep, stubbed threading.Event.wait), or it would deadlock.

    Args:
      time_at: The time that the event would happen.
      event_func: The function to be executed.
    """
    if time_at < self._fake_time:
      raise ValueError('AddEvent add a past event, time_at = %s, time = %s' %
                       (time_at, self._fake_time))
    self._events.put((time_at, next(self._unique_id), event_func))

  def GetTime(self):
    """Get the current time."""
    return self._fake_time

  def AssertTimeAt(self, time_at):
    """Assert the current time is same at time_at."""
    assert self._fake_time == time_at, 'fake time %s != %s' % (self._fake_time,
                                                               time_at)

  def AdvanceTime(self, delta, condition=None):
    """Advance the time.

    The time is advanced for at most delta, or when the condition is True.

    Args:
      delta: The time difference to advance, can be None to block indefinitely
          until condition is True.
      condition: A condition to be checked before each event. The function
          returns when condition is True.
    """
    if condition is None:
      if delta is None:
        raise ValueError("Can't have both condition = None and delta = None")
      condition = lambda: False

    if delta is None:
      end_time = None
    else:
      end_time = self._fake_time + delta

    while not condition():
      try:
        event_time, unique_id, event_func = self._events.get_nowait()
      except queue.Empty:
        if end_time is None:
          # Set time to inf so following AddEvent would fail.
          self._fake_time = float('inf')
          raise type_utils.TimeoutError(
              'No events left when AdvanceTime(delta=None) is called.')

        self._fake_time = end_time
        break

      if end_time is not None and event_time > end_time:
        self._fake_time = end_time
        self._events.put((event_time, unique_id, event_func))
        break

      self._fake_time = event_time
      event_func()


class FakeEvent(threading.Event().__class__):
  """A fake threading.Event.

  All methods works like a normal threading.Event, except that wait() won't
  really block, but only advance the timeline.
  """
  def __init__(self, timeline):
    super(FakeEvent, self).__init__()
    self._timeline = timeline

  def wait(self, timeout=None):
    self._timeline.AdvanceTime(timeout, self.isSet)
    return self.isSet()


class FakeQueue(queue.Queue):
  """A fake queue.Queue.

  All methods works like a normal queue.Queue, except that get(block=True) won't
  really block, but only advance the timeline.

  Also notice that only maxsize=0 is supported, so the put operation never
  block.
  """
  def __init__(self, timeline):
    super(FakeQueue, self).__init__()
    self._timeline = timeline

  def get(self, block=True, timeout=None):
    if not block:
      return super(FakeQueue, self).get(block, timeout)
    self._timeline.AdvanceTime(timeout, lambda: not self.empty())
    return super(FakeQueue, self).get(False)

  def join(self):
    raise NotImplementedError


def MockAll(timeline):
  """Mock all modules that have a fake implemented.

  Args:
    timeline: A TimeLine instance.

  Returns:
    A list of patchers which stop() should be called in tearDown.
  """
  patchers = []
  def _StartPatcher(*args, **kwargs):
    patcher = mock.patch.object(*args, **kwargs)
    patchers.append(patcher)
    return patcher.start()

  def _MockFactoryOnly(obj, name, replace):
    """Only call the mocked version when called from factory code.

    This avoid accident usage of mocked version in some stdlib. (For example,
    threading.Thread use threading.Event internally.)
    """
    orig = getattr(obj, name)

    def _Stub(*args, **kwargs):
      frame = inspect.currentframe().f_back
      while inspect.getmodule(frame).__name__.startswith('unittest.mock'):
        frame = frame.f_back
      caller_module_name = inspect.getmodule(frame).__name__
      if caller_module_name.startswith('cros.factory.'):
        return replace(*args, **kwargs)
      return orig(*args, **kwargs)

    _StartPatcher(obj, name).side_effect = _Stub

  _MockFactoryOnly(time, 'time', timeline.GetTime)
  _MockFactoryOnly(time, 'sleep', timeline.AdvanceTime)

  _MockFactoryOnly(time_utils, 'MonotonicTime', timeline.GetTime)

  _MockFactoryOnly(threading, 'Event', lambda: FakeEvent(timeline))

  _MockFactoryOnly(queue, 'Queue', lambda: FakeQueue(timeline))

  return patchers
