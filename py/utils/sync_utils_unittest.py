#!/usr/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import signal
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


class PollForConditionTest(unittest.TestCase):

  def _Increment(self):
    self.counter = self.counter + 1
    return self.counter

  def _IncrementCheckTrigger(self, trigger=3):
    return self._Increment() > trigger

  def setUp(self):
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


class WaitForTest(unittest.TestCase):

  def runTest(self):
    def _ReturnTrueAfter(t):
      return time.time() > t

    now = time.time()
    self.assertEquals(True, sync_utils.WaitFor(
        lambda: _ReturnTrueAfter(now + 0.5),
        timeout_secs=1))

    now = time.time()
    self.assertRaises(type_utils.TimeoutError, sync_utils.WaitFor,
                      lambda: _ReturnTrueAfter(now + 1), timeout_secs=0.5)


class TimeoutTest(unittest.TestCase):

  def runTest(self):
    with sync_utils.Timeout(3):
      time.sleep(1)

    prev_secs = signal.alarm(10)
    self.assertTrue(prev_secs == 0,
                    msg='signal.alarm() is in use after "with Timeout()"')
    try:
      with sync_utils.Timeout(3):
        time.sleep(1)
    except AssertionError:
      pass
    else:
      raise AssertionError("No assert raised on previous signal.alarm()")
    signal.alarm(0)

    try:
      with sync_utils.Timeout(1):
        time.sleep(3)
    except type_utils.TimeoutError:
      pass
    else:
      raise AssertionError("No timeout")


if __name__ == '__main__':
  unittest.main()
