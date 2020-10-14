#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for Instalog datatypes."""

import copy
import datetime
import logging
import queue
import tempfile
import unittest
from unittest import mock

from cros.factory.instalog import datatypes
from cros.factory.instalog import json_utils
from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_base
from cros.factory.instalog.utils import time_utils


class RuntimeBound:
  """Ensures that a block of code takes at minimum some number of seconds.

  Can be used either as a decorator or as a context manager.
  """

  def __init__(self, min=None, max=None):  # pylint: disable=redefined-builtin
    self._min_seconds = min if min is not None else float('-inf')
    self._max_seconds = max if max is not None else float('inf')
    self._start = None
    self._end = None
    self._elapsed = None

  def __call__(self, fn):
    def WrappedFn(*args, **kwargs):
      with self:
        fn(*args, **kwargs)
    return WrappedFn

  def __enter__(self):
    self._start = time_utils.MonotonicTime()

  def __exit__(self, exc_type, exc_val, exc_tb):
    # If an exception was thrown within the block, pass it up the stack.
    if exc_type:
      raise
    self._end = time_utils.MonotonicTime()
    self._elapsed = self._end - self._start
    if self._elapsed < self._min_seconds:
      raise ValueError('Only %.5fs elapsed (min %.2fs)'
                       % (self._elapsed, self._min_seconds))
    if self._elapsed > self._max_seconds:
      raise ValueError('Already %.5fs elapsed (max %.2fs)'
                       % (self._elapsed, self._max_seconds))


# pylint: disable=abstract-method
class FakePluginAPI(plugin_base.PluginAPI):
  """Implements a fake PluginAPI.

  Implements IsFlushing, EventStreamNext, EventStreamCommit, and
  EventStreamAbort from PluginAPI.  Ignores the `plugin` and `plugin_stream`
  arguments, essentially acting as a BufferEventStream itself.
  """

  def __init__(self, buffer_queue, fail_on_commit=False):
    """Initializes FakePluginAPI.

    Args:
      buffer_queue: A queue from which to pop elements when EventStreamNext is
                    called.
      fail_on_commit: Causes Commit to fail when called.
    """
    self._buffer_queue = buffer_queue
    self._expired = False
    self._fail_on_commit = fail_on_commit

  def IsFlushing(self, plugin):
    del plugin
    return False

  def EventStreamNext(self, plugin, plugin_stream, timeout=1):
    del plugin, plugin_stream, timeout
    if self._expired:
      raise plugin_base.EventStreamExpired
    if self._buffer_queue.empty():
      logging.debug('Nothing to pop')
      return None
    ret = self._buffer_queue.get(False)
    logging.debug('Popping %s...', ret)
    return ret

  def EventStreamCommit(self, plugin, plugin_stream):
    del plugin, plugin_stream
    if self._expired:
      raise plugin_base.EventStreamExpired
    self._expired = True
    if self._fail_on_commit:
      return False
    return True

  def EventStreamAbort(self, plugin, plugin_stream):
    del plugin, plugin_stream
    if self._expired:
      raise plugin_base.EventStreamExpired
    self._expired = True


class TestEvent(unittest.TestCase):
  """Tests for the Event class."""

  def testDict(self):
    """Checks that an event can be accessed just like a dictionary."""
    payload = {'a': 1, 'b': 2, 'c': {}, '__d__': True}
    event = datatypes.Event(payload)
    self.assertEqual(event.payload, payload)
    self.assertEqual(event.keys(), list(payload))
    self.assertEqual(event.values(), list(payload.values()))
    self.assertEqual(event['a'], payload['a'])
    self.assertEqual(event['b'], payload['b'])
    self.assertTrue(repr(payload) in repr(event))
    # Self-defined iteritems(), so it still works in Python3.
    self.assertEqual(('a', 1), next(event.iteritems()))  # pylint: disable=dict-iter-method
    with self.assertRaises(AttributeError):
      self.assertTrue(event.__d__)
    event.setdefault('a', 2)
    event.setdefault('d', 2)
    self.assertEqual(event['a'], 1)
    self.assertEqual(event['d'], 2)
    self.assertEqual(event.get('d'), 2)
    self.assertEqual(event.get('e'), None)
    self.assertEqual(event.get('e', 9), 9)

    # Test equality operators.
    CONTENT = 'ASDFGHJKL!@#$%^&* :"'
    with tempfile.NamedTemporaryFile('w') as f1:
      with tempfile.NamedTemporaryFile('w') as f2:
        f1.write(CONTENT)
        f1.flush()
        f2.write(CONTENT)
        f2.flush()
        payload_a = payload.copy()
        payload_b = payload.copy()
        attachments_a = {'file_id': f1.name}
        attachments_b = {'file_id': f2.name}
        event_a = datatypes.Event(payload_a, attachments_a)
        event_b = datatypes.Event(payload_b, attachments_b)
        self.assertEqual(event_a, event_b)
        self.assertFalse(event_a != event_b)
        f1.write(' ')
        f1.flush()
        self.assertTrue(event_a != event_b)
        self.assertNotEqual(event_a, event_b)

    # Test copy.
    new_event = event.Copy()
    self.assertTrue(event.payload is new_event.payload)
    self.assertTrue(event.attachments is new_event.attachments)
    new_event = copy.copy(event)
    self.assertTrue(event.payload is new_event.payload)
    self.assertTrue(event.attachments is new_event.attachments)

    # Test deepcopy.
    new_event = copy.deepcopy(event)
    self.assertTrue(event == new_event)
    self.assertTrue(event.payload is not new_event.payload)
    self.assertTrue(event['c'] is not new_event['c'])
    self.assertTrue(event.attachments is not new_event.attachments)

  def testData(self):
    """Checks that invalid payload arguments are refused."""
    with self.assertRaises(TypeError):
      datatypes.Event(1)

  def testAttachments(self):
    """Checks that attachments can be properly accessed on an event."""
    # Check that the attachments list is properly initialized when empty.
    event = datatypes.Event({})
    self.assertEqual(len(event.attachments), 0)

    # Check that the attachments argument only accepts the correct type.
    with self.assertRaises(TypeError):
      datatypes.Event({}, attachments=[1])

    # Check accessing an attachment path.
    attachments = {'file_id': '/path/to/file'}
    event = datatypes.Event({}, attachments=attachments)
    self.assertEqual(event.attachments, attachments)

  def testDeserialize(self):
    now_time = datetime.datetime.utcnow()
    event = datatypes.Event({'a': 1, 'time': now_time})
    self.assertEqual(event, datatypes.Event.Deserialize(
        '{"a": 1, "time": {"__type__": "datetime", "value": "%s"}}' %
        now_time.strftime(json_utils.FORMAT_DATETIME)))
    self.assertEqual(event, datatypes.Event.Deserialize(
        '[{"a": 1, "time": {"__type__": "datetime", "value": "%s"}}, {}]' %
        now_time.strftime(json_utils.FORMAT_DATETIME)))
    self.assertEqual(event, datatypes.Event.Deserialize(
        '{"payload": {"a": 1, "time": {"__type__": "datetime", "value": "%s"}},'
        '"attachments": {}, "history": [], "__type__": "Event"}' %
        now_time.strftime(json_utils.FORMAT_DATETIME)))

  def testRoundTrip(self):
    """Checks that an event can de serialized and deserialized."""
    payload = {'a': 1, 'b': 2, 'time': datetime.datetime.utcnow()}

    # Test without attachments.
    event = datatypes.Event(payload)
    json_string = event.Serialize()
    self.assertEqual(event, datatypes.Event.Deserialize(json_string))
    dct = event.ToDict()
    self.assertEqual(event, datatypes.Event.FromDict(dct))

    # Test with attachments.
    attachments = {'file_id': '/path/to/file'}
    event = datatypes.Event(payload, attachments)
    json_string = event.Serialize()
    self.assertEqual(event, datatypes.Event.Deserialize(json_string))
    dct = event.ToDict()
    self.assertEqual(event, datatypes.Event.FromDict(dct))


class TestEventStream(unittest.TestCase):
  """Tests for the EventStream class."""

  def testEventStream(self):
    """Tests using the basic functionality of EventStream."""
    buffer_q = queue.Queue()
    plugin_api = FakePluginAPI(buffer_q)
    event_stream = datatypes.EventStream(None, plugin_api)

    # Try pulling events.
    self.assertEqual(event_stream.GetCount(), 0)
    self.assertIsNone(event_stream.Next())
    self.assertEqual(event_stream.GetCount(), 0)
    buffer_q.put(1)
    self.assertEqual(event_stream.Next(), 1)
    self.assertEqual(event_stream.GetCount(), 1)

    # Try committing/aborting before and after expiration.
    self.assertEqual(event_stream.Commit(), True)
    with self.assertRaises(plugin_base.EventStreamExpired):
      event_stream.Commit()
    with self.assertRaises(plugin_base.EventStreamExpired):
      event_stream.Abort()


class TestEventStreamIterator(unittest.TestCase):
  """Tests for the EventStreamIterator class."""

  def setUp(self):
    self.q = queue.Queue()
    self.plugin_api = FakePluginAPI(self.q)
    self.event_stream = datatypes.EventStream(None, self.plugin_api)

  def testTimeoutSmallerThanInterval(self):
    """Tests correct behaviour when timeout is smaller than interval."""
    with RuntimeBound(max=0.5), self.assertRaises(StopIteration):
      next(self.event_stream.iter(
          blocking=True, timeout=0.1, interval=1))

  def testWaitRetryLoop(self):
    """Stress tests wait-retry loop."""
    with RuntimeBound(min=0.5), self.assertRaises(StopIteration):
      next(self.event_stream.iter(
          blocking=True, timeout=0.5, interval=0.00001))
    with RuntimeBound(min=0.5), self.assertRaises(StopIteration):
      next(self.event_stream.iter(timeout=0.5, interval=0.00001))

  def testNonBlockingWithoutEvent(self):
    """Tests non-blocking operations with no events in the queue."""
    with RuntimeBound(max=0.1), self.assertRaises(StopIteration):
      next(self.event_stream.iter(blocking=False, timeout=1, count=5))
    with RuntimeBound(max=0.1), self.assertRaises(StopIteration):
      next(self.event_stream.iter(blocking=False, count=5))
    with RuntimeBound(max=0.1), self.assertRaises(StopIteration):
      next(self.event_stream.iter(blocking=False, timeout=1))
    with RuntimeBound(max=0.1), self.assertRaises(StopIteration):
      next(self.event_stream.iter(blocking=False))

  def testNonBlockingWithEvent(self):
    """Tests non-blocking operations with finite events in the queue."""
    self.q.put(1)
    with RuntimeBound(max=0.1):
      results = list(self.event_stream.iter(blocking=False, timeout=1, count=1))
      self.assertEqual(results, [1])

    self.q.put(1)
    with RuntimeBound(max=0.1):
      results = list(self.event_stream.iter(blocking=False, count=1))
      self.assertEqual(results, [1])

    self.q.put(1)
    with RuntimeBound(max=0.1):
      results = list(self.event_stream.iter(blocking=False, timeout=1))
      self.assertEqual(results, [1])

    self.q.put(1)
    with RuntimeBound(max=0.1):
      results = list(self.event_stream.iter(blocking=False))
      self.assertEqual(results, [1])

  def testInfiniteItems(self):
    """Tests operations with infinite events in the queue."""
    with mock.patch.object(self.q, 'empty', return_value=False):
      with mock.patch.object(self.q, 'get', return_value=1):
        with RuntimeBound(max=0.1):
          results = list(
              self.event_stream.iter(blocking=True, timeout=1, count=1))
          self.assertEqual(results, [1])

        with RuntimeBound(max=0.1):
          results = list(self.event_stream.iter(timeout=1, count=1))
          self.assertEqual(results, [1])

        with RuntimeBound(max=0.1):
          # Shouldn't matter what interval is set to.
          results = list(
              self.event_stream.iter(timeout=1, interval=1, count=10))
          self.assertEqual(results, [1] * 10)

        with RuntimeBound(max=0.1):
          # Shouldn't matter what interval is set to.
          results = list(
              self.event_stream.iter(timeout=1, interval=0.001, count=10))
          self.assertEqual(results, [1] * 10)

        with RuntimeBound(min=1, max=1.5):
          # No count argument; should run until timeout.
          results = list(self.event_stream.iter(timeout=1))
          self.assertTrue(all([x == 1 for x in results]))
          # Sanity check to make sure that the EventStreamIterator next() loop
          # is running fast enough.  On my machine I consistently get ~46000
          # results.  Tone this down to the safe amount of 5000.
          self.assertGreater(len(results), 5000)

  def testBlockUntilWaitException(self):
    """Tests that iterator aborts before its timeout on WaitException."""
    wait_exception_begin = time_utils.MonotonicTime() + 1
    def DelayedWaitException(plugin, event_stream, timeout):
      del plugin, event_stream, timeout
      if time_utils.MonotonicTime() > wait_exception_begin:
        raise plugin_base.WaitException

    # WaitException is thrown at T=1, so the iterator should end shortly
    # afterwards.
    with mock.patch.object(self.plugin_api, 'EventStreamNext',
                           DelayedWaitException):
      with RuntimeBound(min=1, max=1.2):
        results = list(self.event_stream.iter(timeout=2, interval=0.1, count=1))
        self.assertEqual(results, [])

  def testBlockUntilCountFulfilled(self):
    """Tests that an iterator ends when its count is fulfilled."""
    wait_event_begin = time_utils.MonotonicTime() + 1
    def DelayedEvent(plugin, event_stream, timeout):
      del plugin, event_stream, timeout
      if time_utils.MonotonicTime() > wait_event_begin:
        return 'delayed_event'
      return None

    with mock.patch.object(self.plugin_api, 'EventStreamNext',
                           DelayedEvent):
      with RuntimeBound(min=1, max=1.2):
        results = list(self.event_stream.iter(timeout=2, interval=0.1, count=1))
        self.assertEqual(results, ['delayed_event'])


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
