# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Fake time to be used in unittest using mock library."""

import Queue
import threading

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import type_utils


class TimeLine(object):
  """A timeline class.

  This class implements a fake "time line" that unit test can register event on
  a particular time, and advance the time.

  This class is not multithread safe and should only be used when there's only
  one thread to test.
  """
  def __init__(self):
    self._fake_time = 0
    self._events = Queue.PriorityQueue()

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
    self._events.put((time_at, event_func))

  def GetTime(self):
    """Get the current time."""
    return self._fake_time

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
        event_time, event_func = self._events.get_nowait()
      except Queue.Empty:
        if end_time is None:
          # Set time to inf so following AddEvent would fail.
          self._fake_time = float('inf')
          raise type_utils.TimeoutError(
              'No events left when AdvanceTime(delta=None) is called.')

        self._fake_time = end_time
        break

      if end_time is not None and event_time > end_time:
        self._fake_time = end_time
        self._events.put((event_time, event_func))
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


class FakeQueue(Queue.Queue, object):
  """A fake Queue.Queue.

  All methods works like a normal Queue.Queue, except that get(block=True) won't
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


def MockAll(module, timeline):
  """Mock all imported modules in a module that have a fake implemented.

  Args:
    module: The module under testing.
    timeline: A TimeLine instance.

  Returns:
    A list of mock patchers that should be stopped in tearDown.
  """
  patchers = []
  def _StartPatcher(*args, **kwargs):
    patcher = mock.patch.object(*args, **kwargs)
    patchers.append(patcher)
    return patcher.start()

  if hasattr(module, 'time'):
    _StartPatcher(module.time, 'time').side_effect = timeline.GetTime
    _StartPatcher(module.time, 'sleep').side_effect = timeline.AdvanceTime

  if hasattr(module, 'threading'):
    _StartPatcher(module.threading,
                  'Event').side_effect = (lambda: FakeEvent(timeline))

  if hasattr(module, 'Queue'):
    _StartPatcher(module.Queue,
                  'Queue').side_effect = (lambda: FakeQueue(timeline))
  return patchers
