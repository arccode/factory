#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for UI module."""

from __future__ import print_function

import sys
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.test import event as test_event
from cros.factory.test import test_ui


_MOCK_TEST = 'mock.test'
_MOCK_INVOCATION = 'mock-invocation'


class EventLoopTest(unittest.TestCase):

  def setUp(self):
    self._patchers = []

    self._mock_time = 0
    mock_session = self._CreatePatcher(test_ui, 'session')
    mock_session.GetCurrentTestPath.return_value = _MOCK_TEST
    mock_session.GetCurrentTestInvocation.return_value = _MOCK_INVOCATION
    self._CreatePatcher(test_ui.time, 'time').side_effect = (
        lambda: self._mock_time)
    self.mock_logging = self._CreatePatcher(test_ui, 'logging')

    self._handler_exceptions = []
    self._event_callback = None

    self.event_client = mock.Mock(spec=test_event.BlockingEventClient)
    self.event_loop = test_ui.EventLoop(
        self._RecordException, event_client_class=self._GetMockEventClient)

  def _CreatePatcher(self, *args, **kwargs):
    patcher = mock.patch.object(*args, **kwargs)
    self._patchers.append(patcher)
    return patcher.start()

  def _GetMockEventClient(self, callback):
    self._event_callback = callback
    return self.event_client

  def _RecordException(self):
    self._handler_exceptions.append(sys.exc_info()[1])

  def tearDown(self):
    for patcher in self._patchers:
      patcher.stop()

  def AssertTestUIEvent(self, event):
    self.assertEqual(test_event.Event.Type.TEST_UI_EVENT, event.type)
    self.assertEqual(_MOCK_TEST, event.test)
    self.assertEqual(_MOCK_INVOCATION, event.invocation)

  def testPostEvent(self):
    self.event_loop.PostEvent(
        test_event.Event(test_event.Event.Type.TEST_UI_EVENT, data='data'))

    self.event_client.post_event.assert_called_once()
    posted_event = self.event_client.post_event.call_args[0][0]
    self.AssertTestUIEvent(posted_event)
    self.assertEqual('data', posted_event.data)

  def testPostNewEvent(self):
    self.event_loop.PostNewEvent(
        test_event.Event.Type.TEST_UI_EVENT, data='data')

    self.event_client.post_event.assert_called_once()
    posted_event = self.event_client.post_event.call_args[0][0]
    self.AssertTestUIEvent(posted_event)
    self.assertEqual('data', posted_event.data)

  def _MockNewEvent(self,
                    event_type=test_event.Event.Type.TEST_UI_EVENT,
                    **kwargs):
    kwargs.setdefault('test', _MOCK_TEST)
    kwargs.setdefault('invocation', _MOCK_INVOCATION)
    self._event_callback(test_event.Event(event_type, **kwargs))

  def testHandleEvent(self):
    def _handler(name, event):
      self.AssertTestUIEvent(event)
      received_data.append((name, event.data))

    self.event_loop.AddEventHandler(
        'type1', lambda event: _handler('handler1', event))
    self.event_loop.AddEventHandler(
        'type1', lambda event: _handler('handler2', event))
    self.event_loop.AddEventHandler(
        'type2', lambda event: _handler('handler3', event))

    received_data = []
    self._MockNewEvent(subtype='type1', data='data')
    self.assertEqual([('handler1', 'data'), ('handler2', 'data')],
                     received_data)

    received_data = []
    self._MockNewEvent(subtype='type2', data='data')
    self.assertEqual([('handler3', 'data')], received_data)

    received_data = []
    self._MockNewEvent(subtype='type3', data='data')
    self.assertEqual([], received_data)

    # Wrong event type
    received_data = []
    self._MockNewEvent(
        event_type=test_event.Event.Type.END_EVENT_LOOP, subtype='type1')
    self.assertEqual([], received_data)

    # Wrong test or invocation.
    received_data = []
    self._MockNewEvent(test='footest', subtype='type1')
    self.assertEqual([], received_data)

    received_data = []
    self._MockNewEvent(invocation='fooinvocation', subtype='type1')
    self.assertEqual([], received_data)

  def testHandleEventException(self):
    def _handler(event):
      del event  # Unused.
      raise RuntimeError('Some unexpected error.')

    self.event_loop.AddEventHandler('type1', _handler)
    self._MockNewEvent(
        test_event.Event.Type.TEST_UI_EVENT, subtype='type1', data='data')
    self.assertTrue(self._handler_exceptions)
    self.assertIsInstance(self._handler_exceptions[0], RuntimeError)

  def testHandleEventTimeLimit(self):
    def _handler(event):
      del event  # Unused.
      self._mock_time += 10

    self.event_loop.AddEventHandler('type1', _handler)
    self._MockNewEvent(
        test_event.Event.Type.TEST_UI_EVENT, subtype='type1', data='data')
    self.mock_logging.warn.assert_called_once()
    self.assertRegexpMatches(self.mock_logging.warn.call_args[0][0],
                             r'The handler .* takes too long to finish')

  def testCatchException(self):
    self.assertEqual('foo', self.event_loop.CatchException(lambda: 'foo')())

    def _func():
      raise RuntimeError('Some unexpected error.')

    wrapped_func = self.event_loop.CatchException(_func)
    self.assertEqual('_func', wrapped_func.__name__)

    wrapped_func()
    self.assertTrue(self._handler_exceptions)
    self.assertIsInstance(self._handler_exceptions[0], RuntimeError)

  # TODO(pihsun): Add unit tests for Run / AddTimedHandler / AddTimedIterator.


# TODO(pihsun): Add unit test for UI.


if __name__ == '__main__':
  unittest.main()
