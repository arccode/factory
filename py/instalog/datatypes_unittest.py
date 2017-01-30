#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for Instalog datatypes."""

from __future__ import print_function

import copy
import logging
import mock
import Queue
import time
import unittest

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import log_utils
from instalog import plugin_base


class RuntimeBound(object):
  """Ensures that a block of code takes at minimum some number of seconds.

  Can be used either as a decorator or as a context manager.
  """

  def __init__(self, min=None, max=None):  # pylint: disable=W0622
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
    self._start = time.time()

  def __exit__(self, exc_type, exc_val, exc_tb):
    # If an exception was thrown within the block, pass it up the stack.
    if exc_type:
      raise
    self._end = time.time()
    self._elapsed = self._end - self._start
    if self._elapsed < self._min_seconds:
      raise ValueError('Only %.2fs elapsed (min %.2fs)'
                       % (self._elapsed, self._min_seconds))
    if self._elapsed > self._max_seconds:
      raise ValueError('Already %.2fs elapsed (max %.2fs)'
                       % (self._elapsed, self._max_seconds))


# pylint: disable=W0223
class FakePluginAPI(plugin_base.PluginAPI):
  """Implements a fake PluginAPI.

  Implements IsFlushing, EventStreamNext, EventStreamCommit, and
  EventStreamAbort from PluginAPI.  Ignores the `plugin` and `event_stream`
  arguments, essentially acting as a BufferEventStream itself.
  """

  def __init__(self, buffer_queue, fail_on_commit=False):
    """Initializes FakePluginAPI.

    Args:
      buffer_queue: A Queue from which to pop elements when EventStreamNext is
                    called.
      fail_on_commit: Causes Commit to fail when called.
    """
    self._buffer_queue = buffer_queue
    self._expired = False
    self._fail_on_commit = fail_on_commit

  def IsFlushing(self, plugin):
    del plugin
    return False

  def EventStreamNext(self, plugin, event_stream):
    del plugin, event_stream
    if self._expired:
      raise plugin_base.EventStreamExpired
    if self._buffer_queue.empty():
      logging.debug('Nothing to pop')
      return None
    ret = self._buffer_queue.get(False)
    logging.debug('Popping %s...', ret)
    return ret

  def EventStreamCommit(self, plugin, event_stream):
    del plugin, event_stream
    if self._expired:
      raise plugin_base.EventStreamExpired
    self._expired = True
    if self._fail_on_commit:
      return False
    return True

  def EventStreamAbort(self, plugin, event_stream):
    del plugin, event_stream
    if self._expired:
      raise plugin_base.EventStreamExpired
    self._expired = True
    return None


class TestEvent(unittest.TestCase):
  """Tests for the Event class."""

  def testDict(self):
    """Checks that an event can be accessed just like a dictionary."""
    payload = {'a': 1, 'b': 2, 'c': {}, '__d__': True}
    event = datatypes.Event(payload)
    self.assertEqual(event.payload, payload)
    self.assertEqual(event.keys(), payload.keys())
    self.assertEqual(event.values(), payload.values())
    self.assertEqual(event['a'], payload['a'])
    self.assertEqual(event['b'], payload['b'])
    self.assertTrue(repr(payload) in repr(event))
    self.assertEqual(('a', 1), event.iteritems().next())
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
    payload_a = payload.copy()
    payload_b = payload.copy()
    attachments_a = {'file_id': '/path/to/file'}
    attachments_b = attachments_a.copy()
    event_a = datatypes.Event(payload_a, attachments_a)
    event_b = datatypes.Event(payload_b, attachments_b)
    self.assertEqual(event_a, event_b)
    self.assertFalse(event_a != event_b)

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

  def testRoundTrip(self):
    """Checks that an event can de serialized and deserialized."""
    payload = {'a': 1, 'b': 2}

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
    buffer_q = Queue.Queue()
    plugin_api = FakePluginAPI(buffer_q)
    event_stream = datatypes.EventStream(None, plugin_api)

    # Try pulling events.
    self.assertEquals(event_stream.GetCount(), 0)
    self.assertIsNone(event_stream.Next())
    self.assertEquals(event_stream.GetCount(), 0)
    buffer_q.put(1)
    self.assertEquals(event_stream.Next(), 1)
    self.assertEquals(event_stream.GetCount(), 1)

    # Try committing/aborting before and after expiration.
    self.assertEquals(event_stream.Commit(), True)
    with self.assertRaises(plugin_base.EventStreamExpired):
      event_stream.Commit()
    with self.assertRaises(plugin_base.EventStreamExpired):
      event_stream.Abort()


class TestEventStreamIterator(unittest.TestCase):
  """Tests for the EventStreamIterator class."""

  def setUp(self):
    self.q = Queue.Queue()
    self.plugin_api = FakePluginAPI(self.q)
    self.event_stream = datatypes.EventStream(None, self.plugin_api)

  def testTimeoutSmallerThanInterval(self):
    """Tests correct behaviour when timeout is smaller than interval."""
    with RuntimeBound(max=0.5), self.assertRaises(StopIteration):
      self.event_stream.iter(
          blocking=True, timeout=0.1, interval=1).next()

  def testWaitRetryLoop(self):
    """Stress tests wait-retry loop."""
    with RuntimeBound(min=0.5), self.assertRaises(StopIteration):
      self.event_stream.iter(
          blocking=True, timeout=0.5, interval=0.00001).next()
    with RuntimeBound(min=0.5), self.assertRaises(StopIteration):
      self.event_stream.iter(timeout=0.5, interval=0.00001).next()

  def testNonBlockingWithoutEvent(self):
    """Tests non-blocking operations with no events in the queue."""
    with RuntimeBound(max=0.1), self.assertRaises(StopIteration):
      self.event_stream.iter(blocking=False, timeout=1, count=5).next()
    with RuntimeBound(max=0.1), self.assertRaises(StopIteration):
      self.event_stream.iter(blocking=False, count=5).next()
    with RuntimeBound(max=0.1), self.assertRaises(StopIteration):
      self.event_stream.iter(blocking=False, timeout=1).next()
    with RuntimeBound(max=0.1), self.assertRaises(StopIteration):
      self.event_stream.iter(blocking=False).next()

  def testNonBlockingWithEvent(self):
    """Tests non-blocking operations with finite events in the queue."""
    # pylint: disable=W0106
    self.q.put(1)
    with RuntimeBound(max=0.1):
      results = [x for x in self.event_stream.iter(
          blocking=False, timeout=1, count=1)]
      self.assertEqual(results, [1])

    self.q.put(1)
    with RuntimeBound(max=0.1):
      results = [x for x in self.event_stream.iter(blocking=False, count=1)]
      self.assertEqual(results, [1])

    self.q.put(1)
    with RuntimeBound(max=0.1):
      results = [x for x in self.event_stream.iter(blocking=False, timeout=1)]
      self.assertEqual(results, [1])

    self.q.put(1)
    with RuntimeBound(max=0.1):
      results = [x for x in self.event_stream.iter(blocking=False)]
      self.assertEqual(results, [1])

  def testInfiniteItems(self):
    """Tests operations with infinite events in the queue."""
    # pylint: disable=W0106
    with mock.patch.object(self.q, 'empty', return_value=False):
      with mock.patch.object(self.q, 'get', return_value=1):
        with RuntimeBound(max=0.1):
          results = [x for x in self.event_stream.iter(
              blocking=True, timeout=1, count=1)]
          self.assertEqual(results, [1])

        with RuntimeBound(max=0.1):
          results = [x for x in self.event_stream.iter(timeout=1, count=1)]
          self.assertEqual(results, [1])

        with RuntimeBound(max=0.1):
          # Shouldn't matter what interval is set to.
          results = [x for x in self.event_stream.iter(
              timeout=1, interval=1, count=10)]
          self.assertEqual(results, [1] * 10)

        with RuntimeBound(max=0.1):
          # Shouldn't matter what interval is set to.
          results = [x for x in self.event_stream.iter(
              timeout=1, interval=0.001, count=10)]
          self.assertEqual(results, [1] * 10)

        with RuntimeBound(min=1, max=1.5):
          # No count argument; should run until timeout.
          results = [x for x in self.event_stream.iter(timeout=1)]
          self.assertTrue(all([x == 1 for x in results]))
          # Sanity check to make sure that the EventStreamIterator next() loop
          # is running fast enough.  On my machine I consistently get ~46000
          # results.  Tone this down to the safe amount of 10000.
          self.assertTrue(len(results) > 10000)

  def testBlockUntilWaitException(self):
    """Tests that iterator aborts before its timeout on WaitException."""
    # pylint: disable=W0106
    wait_exception_begin = time.time() + 1
    def DelayedWaitException(plugin, event_stream):
      del plugin, event_stream
      if time.time() > wait_exception_begin:
        raise plugin_base.WaitException
      else:
        return None

    # WaitException is thrown at T=1, so the iterator should end shortly
    # afterwards.
    with mock.patch.object(self.plugin_api, 'EventStreamNext',
                           DelayedWaitException):
      with RuntimeBound(min=1, max=1.2):
        results = [x for x in self.event_stream.iter(
            timeout=2, interval=0.1, count=1)]
        self.assertEqual(results, [])

  def testBlockUntilCountFulfilled(self):
    """Tests that an iterator ends when its count is fulfilled."""
    # pylint: disable=W0106
    wait_event_begin = time.time() + 1
    def DelayedEvent(plugin, event_stream):
      del plugin, event_stream
      if time.time() > wait_event_begin:
        return 'delayed_event'
      else:
        return None

    with mock.patch.object(self.plugin_api, 'EventStreamNext',
                           DelayedEvent):
      with RuntimeBound(min=1, max=1.2):
        results = [x for x in self.event_stream.iter(
            timeout=2, interval=0.1, count=1)]
        self.assertEqual(results, ['delayed_event'])


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO, format=log_utils.LOG_FORMAT)
  unittest.main()
