#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for mock_time_utils module."""

from __future__ import print_function

import Queue
import threading
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.unittest_utils import mock_time_utils
from cros.factory.utils import type_utils


class TimeLineTest(unittest.TestCase):
  def setUp(self):
    self._timeline = mock_time_utils.TimeLine()

  def AssertTime(self, t):
    self.assertEqual(t, self._timeline.GetTime())

  def testAdvanceTime(self):
    self.AssertTime(0)
    self._timeline.AdvanceTime(10)
    self.AssertTime(10)

  def testAddEvent(self):
    handler1 = mock.Mock()
    self._timeline.AddEvent(10, handler1)

    handler2 = mock.Mock()
    self._timeline.AddEvent(20, handler2)

    self._timeline.AdvanceTime(6)
    self.AssertTime(6)
    handler1.assert_not_called()
    handler2.assert_not_called()

    self._timeline.AdvanceTime(6)
    self.AssertTime(12)
    handler1.assert_called_once()
    handler2.assert_not_called()

    self._timeline.AdvanceTime(6)
    self.AssertTime(18)
    handler1.assert_called_once()
    handler2.assert_not_called()

    self._timeline.AdvanceTime(6)
    self.AssertTime(24)
    handler1.assert_called_once()
    handler2.assert_called_once()

  def testAdvanceTimeCondition(self):
    event = threading.Event()
    self._timeline.AddEvent(5, event.set)

    self._timeline.AdvanceTime(3, condition=event.isSet)
    self.AssertTime(3)
    self.assertFalse(event.isSet())
    self._timeline.AdvanceTime(3, condition=event.isSet)
    self.AssertTime(5)
    self.assertTrue(event.isSet())

  def testAdvanceTimeConditionNoTimeout(self):
    event = threading.Event()
    self._timeline.AddEvent(5, event.set)

    self._timeline.AdvanceTime(None, condition=event.isSet)
    self.AssertTime(5)
    self.assertTrue(event.isSet())

  def testAdvanceTimeNoEvent(self):
    self.assertRaises(
        type_utils.TimeoutError,
        self._timeline.AdvanceTime,
        None,
        condition=lambda: False)


class FakeEventTest(TimeLineTest):
  def setUp(self):
    super(FakeEventTest, self).setUp()
    self._event = mock_time_utils.FakeEvent(self._timeline)

  def testWait(self):
    self._timeline.AddEvent(5, self._event.set)
    self.assertTrue(self._event.wait(timeout=10))
    self.AssertTime(5)

  def testWaitTimeout(self):
    self._timeline.AddEvent(5, self._event.set)
    self.assertFalse(self._event.wait(timeout=3))
    self.AssertTime(3)

  def testWaitBlocking(self):
    self._timeline.AddEvent(5, self._event.set)
    self.assertTrue(self._event.wait())
    self.AssertTime(5)

  def testWaitAlreadySet(self):
    self._timeline.AddEvent(3, self._event.set)
    self._timeline.AdvanceTime(5)
    self.assertTrue(self._event.wait(timeout=3))
    self.AssertTime(5)


class FakeQueueTest(TimeLineTest):
  def setUp(self):
    super(FakeQueueTest, self).setUp()
    self._queue = mock_time_utils.FakeQueue(self._timeline)

  def testGet(self):
    self._timeline.AddEvent(5, lambda: self._queue.put('foo'))
    self.assertEqual('foo', self._queue.get(timeout=10))
    self.AssertTime(5)

  def testGetTimeout(self):
    self._timeline.AddEvent(5, lambda: self._queue.put('foo'))
    self.assertRaises(Queue.Empty, self._queue.get, timeout=3)
    self.AssertTime(3)

  def testGetBlocking(self):
    self._timeline.AddEvent(5, lambda: self._queue.put('foo'))
    self.assertEqual('foo', self._queue.get())
    self.AssertTime(5)

  def testGetNotEmpty(self):
    self._timeline.AddEvent(3, lambda: self._queue.put('foo'))
    self._timeline.AdvanceTime(5)
    self.assertEqual('foo', self._queue.get(timeout=3))
    self.AssertTime(5)

  def testGetMultiple(self):
    self._timeline.AddEvent(3, lambda: self._queue.put('foo1'))
    self._timeline.AddEvent(6, lambda: self._queue.put('foo2'))
    self._timeline.AddEvent(9, lambda: self._queue.put('foo3'))
    self._timeline.AddEvent(12, lambda: self._queue.put('foo4'))

    self.assertEqual('foo1', self._queue.get(timeout=5))
    self.AssertTime(3)

    self.assertRaises(Queue.Empty, self._queue.get, timeout=2)
    self.AssertTime(5)

    self.assertEqual('foo2', self._queue.get(timeout=2))
    self.AssertTime(6)

    self.assertEqual('foo3', self._queue.get(timeout=10))
    self.AssertTime(9)

    self.assertEqual('foo4', self._queue.get())
    self.AssertTime(12)

    self.assertRaises(Queue.Empty, self._queue.get, timeout=10)
    self.AssertTime(22)


if __name__ == '__main__':
  unittest.main()
