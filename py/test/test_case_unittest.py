#!/usr/bin/env python3
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for TestCase module."""

import queue
import unittest
from unittest import mock

from cros.factory.test import event as test_event
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.unittest_utils import mock_time_utils
from cros.factory.utils import type_utils


_EventType = test_event.Event.Type


class TestCaseTest(unittest.TestCase):

  class _MockEventLoop:
    def __init__(self):
      self._event_loop_end = queue.Queue()
      # We don't use mock for PostNewEvent and Run, since there is race
      # condition within the mock library __call__...
      self.mock = mock.Mock()

    def PostNewEvent(self, event_type, **kwargs):
      if event_type == _EventType.END_EVENT_LOOP:
        self._event_loop_end.put(kwargs)

    def Run(self):
      end_event_kwargs = self._event_loop_end.get()
      return type_utils.Obj(**end_event_kwargs)

    def __getattr__(self, name):
      return getattr(self.mock, name)

  def setUp(self):
    self._patchers = []

    self._timeline = mock_time_utils.TimeLine()
    self._patchers.extend(mock_time_utils.MockAll(self._timeline))

    self._test = test_case.TestCase()
    self._test.ui_class = mock.Mock

    self._handler_exception_hook = None

    self._mock_event_loop = self._MockEventLoop()
    self._CreatePatcher(
        test_ui, 'EventLoop').side_effect = self._StubEventLoopConstructor

  def _StubEventLoopConstructor(self, handler_exception_hook):
    self._handler_exception_hook = handler_exception_hook
    return self._mock_event_loop

  def _CreatePatcher(self, *args, **kwargs):
    patcher = mock.patch.object(*args, **kwargs)
    self._patchers.append(patcher)
    return patcher.start()

  def tearDown(self):
    for patcher in self._patchers:
      patcher.stop()

  def AssertRunResult(self, error_msg=None):
    result = unittest.TestResult()
    self._test.run(result=result)
    errors = result.errors + result.failures
    if error_msg is None:
      self.assertFalse(errors)
    else:
      self.assertEqual(1, len(errors))
      self.assertIn(error_msg, errors[0][1])

  def AssertNotReached(self):
    raise AssertionError('This should not be reached.')

  def testAutomaticPass(self):
    def _RunTest():
      pass

    self._test.runTest = _RunTest

    self.AssertRunResult()
    self._mock_event_loop.AddEventHandler.assert_any_call(
        'goofy_ui_task_end', mock.ANY)

  def testPassTask(self):
    def _RunTest():
      self._test.PassTask()
      self.AssertNotReached()

    self._test.runTest = _RunTest

    self.AssertRunResult()

  def testFailTask(self):
    def _RunTest():
      self._test.FailTask('failed to bla')
      self.AssertNotReached()

    self._test.runTest = _RunTest

    self.AssertRunResult('failed to bla')

  def testFailWithAssert(self):
    def _RunTest():
      self.assertTrue(False)  # pylint: disable=redundant-unittest-assert

    self._test.runTest = _RunTest

    self.AssertRunResult('False is not true')

  def testAddTaskAllPass(self):
    executed_tasks = []
    def _Task(idx):
      self.assertEqual(idx, self._mock_event_loop.ClearHandlers.call_count)
      self.assertEqual(idx, self._test.ui.UnbindAllKeys.call_count)
      executed_tasks.append(idx)

    self._test.AddTask(lambda: _Task(0))
    self._test.AddTask(lambda: _Task(1))
    self._test.AddTask(lambda: _Task(2))

    self.AssertRunResult()
    self.assertEqual([0, 1, 2], executed_tasks)

  def testAddTaskSomeFail(self):
    executed_tasks = []
    def _Task(name, fail=False):
      executed_tasks.append(name)
      if fail:
        self._test.FailTask('Something wrong')

    self._test.AddTask(lambda: _Task('task1'))
    self._test.AddTask(lambda: _Task('task2', True))
    self._test.AddTask(lambda: _Task('task3'))

    self.AssertRunResult('Something wrong')
    self.assertEqual(['task1', 'task2'], executed_tasks)

  def testWaitTaskEnd(self):
    def _RunTest():
      self._test.WaitTaskEnd()
      self.AssertNotReached()

    def _TestEnd():
      try:
        self._test.PassTask()
      except Exception:
        self._handler_exception_hook()

    self._test.runTest = _RunTest
    self._timeline.AddEvent(10, _TestEnd)

    self.AssertRunResult()
    self._timeline.AssertTimeAt(10)

  def testWaitTaskEndFail(self):
    def _RunTest():
      self._test.WaitTaskEnd()
      self.AssertNotReached()

    def _TestEnd():
      try:
        self._test.FailTask('FAILED!')
      except Exception:
        self._handler_exception_hook()

    self._test.runTest = _RunTest
    self._timeline.AddEvent(10, _TestEnd)

    self.AssertRunResult('FAILED!')
    self._timeline.AssertTimeAt(10)

  def testSleep(self):
    times = []
    def _RunTest():
      while True:
        times.append(self._timeline.GetTime())
        self._test.Sleep(2)

    def _TestEnd():
      try:
        self._test.FailTask('FAILED!')
      except Exception:
        self._handler_exception_hook()

    self._test.runTest = _RunTest
    self._timeline.AddEvent(5, _TestEnd)

    self.AssertRunResult('FAILED!')
    self.assertEqual(5, self._timeline.GetTime())
    self.assertEqual([0, 2, 4], times)


if __name__ == '__main__':
  unittest.main()
