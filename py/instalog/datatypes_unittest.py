#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for Instalog datatypes."""

from __future__ import print_function

import copy
import json
import logging
import mock
import Queue
import re
import time
import unittest

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
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

  Implements EventStreamNext, EventStreamCommit, and EventStreamAbort from
  PluginAPI.  Ignores the `plugin` and `event_stream` arguments, essentially
  acting as a BufferEventStream itself.
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
    data = {'a': 1, 'b': 2, 'c': {}}
    event = datatypes.Event(data)
    self.assertEqual(event.data, data)
    self.assertEqual(event.keys(), data.keys())
    self.assertEqual(event.values(), data.values())
    self.assertEqual(event['a'], data['a'])
    self.assertEqual(event['b'], data['b'])
    self.assertTrue(repr(data) in repr(event))
    self.assertEqual(('a', 1), event.iteritems().next())

    # Test equality operators.
    data_a = data.copy()
    data_b = data.copy()
    attachments_a = {'file_id': '/path/to/file'}
    attachments_b = attachments_a.copy()
    event_a = datatypes.Event(data_a, attachments_a)
    event_b = datatypes.Event(data_b, attachments_b)
    self.assertEqual(event_a, event_b)
    self.assertFalse(event_a != event_b)

    # Test copy.
    new_event = event.Copy()
    self.assertTrue(event.data is new_event.data)
    self.assertTrue(event.attachments is new_event.attachments)
    new_event = copy.copy(event)
    self.assertTrue(event.data is new_event.data)
    self.assertTrue(event.attachments is new_event.attachments)

    # Test deepcopy.
    new_event = copy.deepcopy(event)
    self.assertTrue(event == new_event)
    self.assertTrue(event.data is not new_event.data)
    self.assertTrue(event['c'] is not new_event['c'])
    self.assertTrue(event.attachments is not new_event.attachments)

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
    data = {'a': 1, 'b': 2}

    # Test without attachments.
    event = datatypes.Event(data)
    json_string = event.Serialize()
    self.assertEqual(event, datatypes.Event.Deserialize(json_string))
    # Serialize returns the JSON string of the two-element list:
    #   [data, attachments]
    # Since in this case, we don't provide any attachments, the JSON string will
    # look like:
    #   [{ ... data ... }, {}]
    # Use a regex to manually remove the second element of the returned list
    # for DeserializeRaw.
    json_event = re.sub(r'^\[(.*), ?{}]', r'\1', json_string)
    self.assertEqual(event, datatypes.Event.DeserializeRaw(json_event))

    # Test with attachments.
    attachments = {'file_id': '/path/to/file'}
    event2 = datatypes.Event(data, attachments)
    json_string = event2.Serialize()
    self.assertEqual(event2, datatypes.Event.Deserialize(json_string))
    self.assertEquals(event2, datatypes.Event.DeserializeRaw(
        json.dumps(data), json.dumps(attachments)))


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
  LOG_FORMAT = '%(asctime)s [%(levelname)s] [%(name)s] %(message)s'
  logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
  unittest.main()
