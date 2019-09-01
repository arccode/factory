#!/usr/bin/env python2
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import Queue
import signal
import threading
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.unittest_utils import mock_time_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


class PollingTestBase(unittest.TestCase):

  def setUp(self):
    self._timeline = mock_time_utils.TimeLine()
    self._patchers = mock_time_utils.MockAll(self._timeline)
    self._polling_sleep_context = sync_utils.WithPollingSleepFunction(
        self._timeline.AdvanceTime)
    self._polling_sleep_context.__enter__()

  def tearDown(self):
    self._polling_sleep_context.__exit__(None, None, None)
    for patcher in self._patchers:
      patcher.stop()


class PollForConditionTest(PollingTestBase):

  def _Increment(self):
    self.counter = self.counter + 1
    return self.counter

  def _IncrementCheckTrigger(self, trigger=3):
    return self._Increment() > trigger

  def setUp(self):
    super(PollForConditionTest, self).setUp()
    self.counter = 1

  def testPollForCondition(self):
    self.assertEqual(True, sync_utils.PollForCondition(
        poll_method=self._IncrementCheckTrigger,
        timeout_secs=5, poll_interval_secs=0.01))

  def testPollForConditionSeparateConditionMethod(self):
    self.assertEqual(5, sync_utils.PollForCondition(
        poll_method=self._Increment,
        condition_method=lambda x: x >= 5,
        timeout_secs=5, poll_interval_secs=0.01))

  def testPollForConditionTimeout(self):
    self.assertRaises(
        type_utils.TimeoutError, sync_utils.PollForCondition,
        poll_method=lambda: self._IncrementCheckTrigger(trigger=30),
        timeout_secs=2, poll_interval_secs=0.1)


class WaitForTest(PollingTestBase):

  def runTest(self):
    def _ReturnTrueAfter(t):
      return self._timeline.GetTime() > t

    now = self._timeline.GetTime()
    self.assertEquals(True, sync_utils.WaitFor(
        lambda: _ReturnTrueAfter(now + 0.5),
        timeout_secs=1))

    now = self._timeline.GetTime()
    self.assertRaises(type_utils.TimeoutError, sync_utils.WaitFor,
                      lambda: _ReturnTrueAfter(now + 1), timeout_secs=0.5)


class QueueGetTest(PollingTestBase):

  def setUp(self):
    super(QueueGetTest, self).setUp()
    self._queue = Queue.Queue()

  def testQueueGetEmpty(self):
    self.assertRaises(Queue.Empty, sync_utils.QueueGet, self._queue, timeout=1)

  def testQueueGetSomething(self):
    self._timeline.AddEvent(30, lambda: self._queue.put(123))

    self.assertEqual(123, sync_utils.QueueGet(self._queue))

  def testQueueGetNone(self):
    self._timeline.AddEvent(1, lambda: self._queue.put(None))

    self.assertIsNone(sync_utils.QueueGet(self._queue))

  def testQueueGetTimeout(self):
    self._timeline.AddEvent(30, lambda: self._queue.put('foo'))
    self._timeline.AddEvent(40, lambda: self._queue.put('bar'))

    self.assertRaises(
        Queue.Empty,
        sync_utils.QueueGet, self._queue, timeout=20, poll_interval_secs=1)
    self._timeline.AssertTimeAt(20)

    self.assertEqual('foo',
                     sync_utils.QueueGet(
                         self._queue, timeout=20, poll_interval_secs=1))
    self._timeline.AssertTimeAt(30)

    self.assertEqual('bar',
                     sync_utils.QueueGet(
                         self._queue, timeout=20, poll_interval_secs=1))
    self._timeline.AssertTimeAt(40)


class TimeoutTest(unittest.TestCase):

  def testSignalTimeout(self):
    with sync_utils.SignalTimeout(3):
      time.sleep(1)

    prev_secs = signal.alarm(10)
    self.assertTrue(prev_secs == 0,
                    msg='signal.alarm() is in use after "with SignalTimeout()"')
    try:
      with sync_utils.SignalTimeout(3):
        time.sleep(1)
    except AssertionError:
      pass
    else:
      raise AssertionError("No assert raised on previous signal.alarm()")
    signal.alarm(0)

    try:
      with sync_utils.SignalTimeout(1):
        time.sleep(3)
    except type_utils.TimeoutError:
      pass
    else:
      raise AssertionError("No timeout")

  def testThreadTimeout(self):
    with sync_utils.ThreadTimeout(0.3):
      time.sleep(0.1)

    with sync_utils.ThreadTimeout(0.3):
      with sync_utils.ThreadTimeout(0.2):
        time.sleep(0.1)

    with sync_utils.ThreadTimeout(0.2):
      with sync_utils.ThreadTimeout(0.3):
        time.sleep(0.1)

    with self.assertRaises(type_utils.TimeoutError):
      with sync_utils.ThreadTimeout(0.1):
        time.sleep(0.3)

    with self.assertRaises(type_utils.TimeoutError):
      with sync_utils.ThreadTimeout(0.1):
        with sync_utils.ThreadTimeout(0.5):
          time.sleep(0.3)

    with self.assertRaises(type_utils.TimeoutError):
      with sync_utils.ThreadTimeout(0.5):
        with sync_utils.ThreadTimeout(0.1):
          time.sleep(0.3)

  def testThreadTimeoutInOtherThread(self):
    def WillPass():
      with sync_utils.ThreadTimeout(0.3):
        with sync_utils.ThreadTimeout(0.2):
          time.sleep(0.1)

    def WillTimeout():
      with sync_utils.ThreadTimeout(0.2):
        with sync_utils.ThreadTimeout(0.5):
          time.sleep(0.3)

    def Run(func, queue):
      try:
        queue.put((True, func()))
      except BaseException as e:
        queue.put((False, e))

    queue = Queue.Queue(1)
    thread = threading.Thread(target=Run, args=(WillPass, queue))
    thread.daemon = True
    thread.start()
    thread.join(1)
    self.assertFalse(thread.is_alive())
    flag, value = queue.get()
    self.assertTrue(flag)
    self.assertIsNone(value)

    queue = Queue.Queue(1)
    thread = threading.Thread(target=Run, args=(WillTimeout, queue))
    thread.daemon = True
    thread.start()
    thread.join(1)
    self.assertFalse(thread.is_alive())
    flag, value = queue.get()
    self.assertFalse(flag)
    self.assertTrue(isinstance(value, type_utils.TimeoutError))

  def testThreadTimeoutCancelTimeout(self):
    with sync_utils.ThreadTimeout(0.2) as timer:
      time.sleep(0.1)
      timer.CancelTimeout()
      time.sleep(0.3)


DELAY = 0.1


class SynchronizedTest(unittest.TestCase):
  class MyClass(object):
    def __init__(self):
      self._lock = threading.RLock()
      self.data = []

    @sync_utils.Synchronized
    def A(self):
      self.data.append('A1')
      time.sleep(DELAY * 2)
      self.data.append('A2')

    @sync_utils.Synchronized
    def B(self):
      self.data.append('B')

  def setUp(self):
    self.obj = self.MyClass()

  def testSynchronized(self):
    thread_a = threading.Thread(target=self.obj.A, name='A')
    thread_a.start()
    time.sleep(DELAY)
    self.obj.B()
    thread_a.join()
    self.assertEqual(['A1', 'A2', 'B'], self.obj.data)


if __name__ == '__main__':
  unittest.main()
