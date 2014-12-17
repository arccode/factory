#!/usr/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

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
        timeout=5, poll_interval_secs=0.01))

  def testPollForConditionSeparateConditionMethod(self):
    self.assertEqual(5, sync_utils.PollForCondition(
        poll_method=self._Increment,
        condition_method=lambda x: x >= 5,
        timeout=5, poll_interval_secs=0.01))

  def testPollForConditionTimeout(self):
    self.assertRaises(type_utils.TimeoutError, sync_utils.PollForCondition,
        poll_method=lambda: self._IncrementCheckTrigger(trigger=30),
        timeout=2, poll_interval_secs=0.1)


if __name__ == '__main__':
  unittest.main()
