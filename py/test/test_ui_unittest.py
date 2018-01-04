#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for UI module."""

from __future__ import print_function

import Queue
import random
import sys
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.test import event as test_event
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.unittest_utils import mock_time_utils
from cros.factory.utils import type_utils


_MOCK_TEST = 'mock.test'
_MOCK_INVOCATION = 'mock-invocation'


_EventType = test_event.Event.Type


class EventLoopTestBase(unittest.TestCase):

  def setUp(self):
    self._patchers = []

    self._timeline = mock_time_utils.TimeLine()
    self._patchers.extend(mock_time_utils.MockAll(test_ui, self._timeline))
    mock_session = self._CreatePatcher(test_ui, 'session')
    mock_session.GetCurrentTestPath.return_value = _MOCK_TEST
    mock_session.GetCurrentTestInvocation.return_value = _MOCK_INVOCATION
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
    self.assertEqual(_EventType.TEST_UI_EVENT, event.type)
    self.assertEqual(_MOCK_TEST, event.test)
    self.assertEqual(_MOCK_INVOCATION, event.invocation)


class EventLoopTest(EventLoopTestBase):

  def testPostEvent(self):
    self.event_loop.PostEvent(
        test_event.Event(_EventType.TEST_UI_EVENT, data='data'))

    self.event_client.post_event.assert_called_once()
    posted_event = self.event_client.post_event.call_args[0][0]
    self.AssertTestUIEvent(posted_event)
    self.assertEqual('data', posted_event.data)

  def testPostNewEvent(self):
    self.event_loop.PostNewEvent(_EventType.TEST_UI_EVENT, data='data')

    self.event_client.post_event.assert_called_once()
    posted_event = self.event_client.post_event.call_args[0][0]
    self.AssertTestUIEvent(posted_event)
    self.assertEqual('data', posted_event.data)

  def _MockNewEvent(self, event_type=_EventType.TEST_UI_EVENT, **kwargs):
    kwargs.setdefault('test', _MOCK_TEST)
    kwargs.setdefault('invocation', _MOCK_INVOCATION)
    self._event_callback(test_event.Event(event_type, **kwargs))

  def testHandleEvent(self):
    def _Handler(name, event):
      self.AssertTestUIEvent(event)
      received_data.append((name, event.data))

    self.event_loop.AddEventHandler(
        'type1', lambda event: _Handler('handler1', event))
    self.event_loop.AddEventHandler(
        'type1', lambda event: _Handler('handler2', event))
    self.event_loop.AddEventHandler(
        'type2', lambda event: _Handler('handler3', event))

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
        event_type=_EventType.END_EVENT_LOOP, subtype='type1')
    self.assertEqual([], received_data)

    # Wrong test or invocation.
    received_data = []
    self._MockNewEvent(test='footest', subtype='type1')
    self.assertEqual([], received_data)

    received_data = []
    self._MockNewEvent(invocation='fooinvocation', subtype='type1')
    self.assertEqual([], received_data)

  def testHandleEventException(self):
    def _Handler(event):
      del event  # Unused.
      raise RuntimeError('Some unexpected error.')

    self.event_loop.AddEventHandler('type1', _Handler)
    self._MockNewEvent(_EventType.TEST_UI_EVENT, subtype='type1', data='data')
    self.assertTrue(self._handler_exceptions)
    self.assertIsInstance(self._handler_exceptions[0], RuntimeError)

  def testHandleEventTimeLimit(self):
    def _Handler(event):
      del event  # Unused.
      self._timeline.AdvanceTime(10)

    self.event_loop.AddEventHandler('type1', _Handler)
    self._MockNewEvent(_EventType.TEST_UI_EVENT, subtype='type1', data='data')
    self.mock_logging.warn.assert_called_once()
    self.assertRegexpMatches(self.mock_logging.warn.call_args[0][0],
                             r'The handler .* takes too long to finish')

  def testCatchException(self):
    self.assertEqual('foo', self.event_loop.CatchException(lambda: 'foo')())

    def _Func():
      raise RuntimeError('Some unexpected error.')

    wrapped_func = self.event_loop.CatchException(_Func)
    self.assertEqual('_Func', wrapped_func.__name__)

    wrapped_func()
    self.assertTrue(self._handler_exceptions)
    self.assertIsInstance(self._handler_exceptions[0], RuntimeError)


_PROBE_INTERVAL = 100


class EventLoopRunTest(EventLoopTestBase):

  def setUp(self):
    super(EventLoopRunTest, self).setUp()

    self._fake_event_client_queue = mock_time_utils.FakeQueue(
        timeline=self._timeline)
    self.event_client.wait.side_effect = self._MockWaitEndEventLoopEvent
    # pylint: disable=protected-access
    # Change the probing interval to 100 to make all time values integer.
    self._original_probe_interval = test_ui._EVENT_LOOP_PROBE_INTERVAL
    test_ui._EVENT_LOOP_PROBE_INTERVAL = _PROBE_INTERVAL

  def tearDown(self):
    super(EventLoopRunTest, self).tearDown()
    # pylint: disable=protected-access
    test_ui._EVENT_LOOP_PROBE_INTERVAL = self._original_probe_interval

  def _MockWaitEndEventLoopEvent(self, condition, timeout):
    try:
      end_time = self._timeline.GetTime() + timeout
      while True:
        event = self._fake_event_client_queue.get(
            timeout=end_time - self._timeline.GetTime())
        self._event_callback(event)
        if condition(event):
          return event
    except Queue.Empty:
      return None

  def _MockEndEventLoopEvent(self,
                             event_time,
                             status=state.TestState.PASSED,
                             **kwargs):
    event = test_event.Event(
        _EventType.END_EVENT_LOOP,
        test=_MOCK_TEST,
        invocation=_MOCK_INVOCATION,
        status=status,
        **kwargs)
    self._timeline.AddEvent(
        event_time, lambda: self._fake_event_client_queue.put(event))

  def testRunPassed(self):
    self._MockEndEventLoopEvent(10)
    self.event_loop.Run()

  def testRunFailed(self):
    self._MockEndEventLoopEvent(
        10, status=state.TestState.FAILED, error_msg='test failed.')
    self.assertRaisesRegexp(type_utils.TestFailure, '^test failed.$',
                            self.event_loop.Run)

  def testAddTimedHandler(self):
    """Test add a timed non-repeating handler.

    Time line:
      95: AddTimedHandler is called with time_sec = 10.
      105: The handler is called.
      120: Event loop ends.
    """
    def _Handler():
      self.assertEqual(105, self._timeline.GetTime())

    self._timeline.AddEvent(
        95, lambda: self.event_loop.AddTimedHandler(_Handler, 10))
    self._MockEndEventLoopEvent(120)

    self.event_loop.Run()

  def testAddTimedHandlerRepeating(self):
    """Test add a timed repeating handler.

    Time line:
      10: AddTimedHandler is called with time_sec = 30, repeat = True.
      100: The timed handler is checked and called.
      100, 130, 160, 190, 220: The handler is called.
      240: Event loop ends.
    """
    called_times = []
    def _Handler():
      called_times.append(self._timeline.GetTime())

    self._timeline.AddEvent(
        10, lambda: self.event_loop.AddTimedHandler(_Handler, 30, repeat=True))
    self._MockEndEventLoopEvent(240)

    self.event_loop.Run()

    expected_times = [100, 130, 160, 190, 220]
    self.assertEqual(expected_times, called_times)

  def testAddTimedHandlerRepeatingLongTimeout(self):
    """Test add a timed repeating handler.

    Time line:
      10: AddTimedHandler is called with time_sec = 330, repeat = True.
      100: The timed handler is checked and called.
      100, 430, 760, 1090: The handler is called.
      1100: Event loop ends.
    """
    called_times = []
    def _Handler():
      called_times.append(self._timeline.GetTime())

    self._timeline.AddEvent(
        10, lambda: self.event_loop.AddTimedHandler(_Handler, 330, repeat=True))
    self._MockEndEventLoopEvent(1100)

    self.event_loop.Run()

    expected_times = [100, 430, 760, 1090]
    self.assertEqual(expected_times, called_times)

  def testAddTimedHandlerStopIteration(self):
    """Test add a timed repeating handler that raises StopIteration.

    Time line:
      10: AddTimedHandler is called with time_sec = 30, repeat = True.
      100: The timed handler is checked and executed.
      100, 130: The handler is called.
      160: The handler is called and StopIteration is raised.
      240: Event loop ends.
    """
    called_times = []
    def _Handler():
      t = self._timeline.GetTime()
      called_times.append(t)
      if t > 150:
        raise StopIteration

    self._timeline.AddEvent(
        10, lambda: self.event_loop.AddTimedHandler(_Handler, 30, repeat=True))
    self._MockEndEventLoopEvent(240)

    self.event_loop.Run()

    expected_times = [100, 130, 160]
    self.assertEqual(expected_times, called_times)

  def testAddTimedIterator(self):
    """Test add a timed iterator.

    Time line:
      10: AddTimedIterable is called with time_sec = 30.
      100: The timed iterator is checked.
      100, 130, 160, 190, 220: The iterator is called.
      300: Event loop ends.
    """
    called_times = []
    def _Iterator():
      for unused_i in range(5):
        called_times.append(self._timeline.GetTime())
        yield

    self._timeline.AddEvent(
        10, lambda: self.event_loop.AddTimedIterable(_Iterator(), 30))
    self._MockEndEventLoopEvent(300)

    self.event_loop.Run()

    expected_times = [100, 130, 160, 190, 220]
    self.assertEqual(expected_times, called_times)

  def testAddMultiple(self):
    """Test add multiple random timed events and event handler."""
    TOTAL_TIME = 1000

    calls = {}
    called_times = []
    def _Log(name):
      calls.setdefault(name, []).append(self._timeline.GetTime())
      called_times.append(self._timeline.GetTime())

    def _MockEvent(subtype):
      self._fake_event_client_queue.put(
          test_event.Event(
              _EventType.TEST_UI_EVENT,
              test=_MOCK_TEST,
              invocation=_MOCK_INVOCATION,
              subtype=subtype))

    self.event_loop.AddEventHandler(
        'type1', lambda event: _Log('handler1'))
    self.event_loop.AddEventHandler(
        'type2', lambda event: _Log('handler2'))

    expected_calls = {}

    def _AddRandomEvent():
      event_type = random.randint(1, 3)
      event_time = random.randrange(TOTAL_TIME)
      self._timeline.AddEvent(
          event_time, lambda: _MockEvent('type%d' % event_type))
      if event_type != 3:
        expected_calls.setdefault('handler%d' % event_type,
                                  []).append(event_time)

    for unused_i in range(300):
      _AddRandomEvent()

    # Non-repeating timed handler.
    def _AddRandomHandler():
      event_time = random.randrange(TOTAL_TIME)
      event_delay = random.randrange(TOTAL_TIME)
      name = 'timed-%d-%d' % (event_time, event_delay)
      self._timeline.AddEvent(event_time,
                              (lambda: self.event_loop.AddTimedHandler(
                                  lambda: _Log(name), event_delay)))
      expected_time = event_time + event_delay
      expected_calls.setdefault(name, []).append(expected_time)

    for unused_i in range(300):
      _AddRandomHandler()

    # Repeating timed handler.
    def _AddRandomRepeatingHandler():
      event_time = random.randrange(TOTAL_TIME)
      event_delay = random.randrange(TOTAL_TIME)
      name = 'timed-repeat-%d-%d' % (event_time, event_delay)
      self._timeline.AddEvent(
          event_time, (lambda: self.event_loop.AddTimedHandler(
              lambda: _Log(name), event_delay, repeat=True)))
      expected_times = expected_calls.setdefault(name, [])
      while event_time <= TOTAL_TIME:
        expected_times.append(event_time)
        event_time += event_delay

    for unused_i in range(100):
      _AddRandomRepeatingHandler()

    # Repeating timed iterable.
    def _AddRandomRepeatingIterable():
      event_time = random.randrange(TOTAL_TIME)
      event_delay = random.randrange(TOTAL_TIME)
      iter_count = random.randrange(1, 30)
      name = 'iter-repeat-%d-%d-%d' % (event_time, event_delay, iter_count)

      def _Iterator():
        for unused_i in xrange(iter_count):
          _Log(name)
          yield

      self._timeline.AddEvent(
          event_time, (lambda: self.event_loop.AddTimedIterable(
              _Iterator(), event_delay)))
      expected_calls.setdefault(name, []).extend(
          [event_time + event_delay * i for i in xrange(iter_count)])

    for unused_i in range(100):
      _AddRandomRepeatingIterable()

    self._MockEndEventLoopEvent(TOTAL_TIME)

    self.event_loop.Run()

    self.assertEqual(sorted(called_times), called_times)
    for name, expected_times in expected_calls.iteritems():
      expected_times = sorted(expected_times)
      actual_times = calls.get(name, [])
      if name.startswith('handler'):
        # Event handler should be at correct time.
        self.assertEqual(expected_times, actual_times)
      else:
        self.assertLessEqual(len(actual_times), len(expected_times))
        for i, expected_time in enumerate(expected_times):
          if i < len(actual_times):
            # Timed handler may be delayed by at most _PROBE_INTERVAL.
            self.assertGreaterEqual(actual_times[i], expected_time)
            self.assertLess(actual_times[i], expected_time + _PROBE_INTERVAL)
          else:
            # The call happens after TOTAL_TIME.
            self.assertGreater(expected_time + _PROBE_INTERVAL, TOTAL_TIME)


_MOCK_HTML = 'mock-html'
_MOCK_ID = 'mock-id'


class UITest(unittest.TestCase):

  def setUp(self):
    self._event_loop = mock.Mock()
    self._ui = test_ui.UI(event_loop=self._event_loop)

  def AssertEventsPosted(self, *events):
    flatten_args = [
        (args[0], kwargs)
        for (args, kwargs) in self._event_loop.PostNewEvent.call_args_list
    ]
    self.assertEqual(flatten_args, list(events))

  def _SetHTMLEvent(self, **kwargs):
    event = {
        'html': _MOCK_HTML,
        'id': _MOCK_ID,
        'append': False,
        'autoscroll': False
    }
    event.update(kwargs)
    return (_EventType.SET_HTML, event)

  def testSetHTML(self):
    self._ui.SetHTML(_MOCK_HTML, id=_MOCK_ID)
    self._ui.SetHTML(_MOCK_HTML, id=_MOCK_ID, append=True)
    self._ui.SetHTML(_MOCK_HTML, id=_MOCK_ID, autoscroll=True)

    self.AssertEventsPosted(
        self._SetHTMLEvent(),
        self._SetHTMLEvent(append=True),
        self._SetHTMLEvent(autoscroll=True))

  def testAppendHTML(self):
    self._ui.AppendHTML(_MOCK_HTML, id=_MOCK_ID)
    self._ui.AppendHTML(_MOCK_HTML, id=_MOCK_ID, autoscroll=True)

    self.AssertEventsPosted(
        self._SetHTMLEvent(append=True),
        self._SetHTMLEvent(append=True, autoscroll=True))

  def testAppendCSS(self):
    _MOCK_CSS = 'mock-css'
    self._ui.AppendCSS(_MOCK_CSS)

    self.AssertEventsPosted(
        self._SetHTMLEvent(
            html='<style type="text/css">%s</style>' % _MOCK_CSS,
            id='head',
            append=True))

  def testAppendCSSLink(self):
    _MOCK_CSS_LINK = 'mock-css-link'
    self._ui.AppendCSSLink(_MOCK_CSS_LINK)

    self.AssertEventsPosted(
        self._SetHTMLEvent(
            html='<link rel="stylesheet" type="text/css" href="%s">' %
            _MOCK_CSS_LINK,
            id='head',
            append=True))

  def _RunJSEvent(self, js, **kwargs):
    return (_EventType.RUN_JS, {'js': js, 'args': kwargs})

  def testRunJS(self):
    self._ui.RunJS('alert(1);')
    self._ui.RunJS('alert(args.msg);', msg='foobar')

    self.AssertEventsPosted(
        self._RunJSEvent('alert(1);'),
        self._RunJSEvent('alert(args.msg);', msg='foobar'))

  def testCallJSFunction(self):
    self._ui.CallJSFunction('test.alert', '123')

    self.AssertEventsPosted(
        self._RunJSEvent('test.alert(args.arg_0)', arg_0='123'))

  def testInitJSTestObject(self):
    js_object = self._ui.InitJSTestObject('someTest', 2, 1, 7)
    js_object.Hopping()
    js_object.Jump()

    self.AssertEventsPosted(
        self._RunJSEvent(
            'window.testObject = new someTest(...args.constructorArg)',
            constructorArg=(2, 1, 7)),
        self._RunJSEvent('window.testObject.hopping()'),
        self._RunJSEvent('window.testObject.jump()'))

  def testBindStandardKeys(self):
    self._ui.BindStandardKeys()
    self._ui.BindStandardPassKeys()
    self._ui.BindStandardFailKeys()

    self.AssertEventsPosted(
        self._RunJSEvent('test.bindStandardKeys()'),
        self._RunJSEvent('test.bindStandardPassKeys()'),
        self._RunJSEvent('test.bindStandardFailKeys()'))

  def testBindKeyJS(self):
    self._ui.BindKeyJS('A', 'a()')
    self._ui.BindKeyJS('B', 'b()', once=True)
    self._ui.BindKeyJS(
        test_ui.ENTER_KEY, 'onEnter()', once=True, virtual_key=False)

    self.AssertEventsPosted(
        self._RunJSEvent(
            'test.bindKey(args.key, (event) => { a() }, '
            'args.once, args.virtual_key)',
            key='A',
            once=False,
            virtual_key=True),
        self._RunJSEvent(
            'test.bindKey(args.key, (event) => { b() }, '
            'args.once, args.virtual_key)',
            key='B',
            once=True,
            virtual_key=True),
        self._RunJSEvent(
            'test.bindKey(args.key, (event) => { onEnter() }, '
            'args.once, args.virtual_key)',
            key='ENTER',
            once=True,
            virtual_key=False))

  def testBindKey(self):
    def _Handler(event):
      del event  # Unused.

    self._ui.BindKey('U', _Handler)
    self._event_loop.AddEventHandler.assert_called_once()
    uuid, handler = self._event_loop.AddEventHandler.call_args[0]
    self.assertEqual(_Handler, handler)
    self.AssertEventsPosted(
        self._RunJSEvent(
            'test.bindKey(args.key, (event) => { test.sendTestEvent("%s", '
            '{}); }, args.once, args.virtual_key)' % uuid,
            key='U',
            once=False,
            virtual_key=True))

  def testUnbindKey(self):
    self._ui.UnbindKey('A')
    self._ui.UnbindAllKeys()

    self.AssertEventsPosted(
        self._RunJSEvent('test.unbindKey(args.arg_0)', arg_0='A'),
        self._RunJSEvent('test.unbindAllKeys()'))

  def testPlayAudio(self):
    self._ui.PlayAudioFile('a.mp4')

    self._event_loop.PostNewEvent.assert_called_once()
    args, kwargs = self._event_loop.PostNewEvent.call_args
    self.assertEqual((_EventType.RUN_JS,), args)
    self.assertEqual('/sounds/a.mp4', kwargs['args']['path'])
    self.assertEqual("""
      const audioElement = new Audio(args.path);
      audioElement.addEventListener(
          "canplaythrough", () => { audioElement.play(); });
    """.replace(' ', ''), kwargs['js'].replace(' ', ''))

  def testSetFocus(self):
    self._ui.SetFocus('main')

    self.AssertEventsPosted(
        self._RunJSEvent('document.getElementById(args.id).focus()', id='main'))

  def testSetSelected(self):
    self._ui.SetSelected('main')

    self.AssertEventsPosted(
        self._RunJSEvent(
            'document.getElementById(args.id).select()', id='main'))

  def testAlert(self):
    self._ui.Alert('1')

    self.AssertEventsPosted(
        self._RunJSEvent('test.alert(args.arg_0)', arg_0='1'))

  def testShowHideElement(self):
    self._ui.HideElement('main')
    self._ui.ShowElement('main')

    self.AssertEventsPosted(
        self._RunJSEvent(
            'document.getElementById(args.id).style.display = "none"',
            id='main'),
        self._RunJSEvent(
            'document.getElementById(args.id).style.display = "initial"',
            id='main'))

  def testImportHTML(self):
    self._ui.ImportHTML('fragment.html')

    self.AssertEventsPosted((_EventType.IMPORT_HTML, {'url': 'fragment.html'}))


class UIKeyTest(unittest.TestCase):

  def setUp(self):
    self._event_loop = mock.Mock()
    self._ui = test_ui.UI(event_loop=self._event_loop)

    self._patchers = []

    self._timeline = mock_time_utils.TimeLine()
    self._patchers.extend(mock_time_utils.MockAll(test_ui, self._timeline))

    self.key_callbacks = {}

    self._CreatePatcher(self._ui, 'BindKey').side_effect = self._StubBindKey
    self._CreatePatcher(self._ui, 'UnbindKey').side_effect = self._StubUnbindKey
    self._CreatePatcher(test_ui.threading,
                        'current_thread')().name = 'other_thread'

  def _StubBindKey(self, key, callback):
    self.key_callbacks[key] = callback

  def _StubUnbindKey(self, key):
    del self.key_callbacks[key]

  def _CreatePatcher(self, *args, **kwargs):
    patcher = mock.patch.object(*args, **kwargs)
    self._patchers.append(patcher)
    return patcher.start()

  def tearDown(self):
    for patcher in self._patchers:
      patcher.stop()

  def _SimulateKeyPress(self, key):
    if key in self.key_callbacks:
      self.key_callbacks[key](None)

  def testWaitKeysOnce(self):
    self._timeline.AddEvent(
        3, lambda: self._SimulateKeyPress(test_ui.ENTER_KEY))

    self.assertEqual(test_ui.ENTER_KEY,
                     self._ui.WaitKeysOnce(test_ui.ENTER_KEY))
    self.assertFalse(self.key_callbacks)

  def testWaitKeysOnceTimeout(self):
    self._timeline.AddEvent(
        3, lambda: self._SimulateKeyPress(test_ui.ENTER_KEY))

    self.assertEqual(test_ui.ENTER_KEY,
                     self._ui.WaitKeysOnce(test_ui.ENTER_KEY, timeout=5))
    self.assertFalse(self.key_callbacks)

  def testWaitKeysOnceTimeoutNoKey(self):
    self._timeline.AddEvent(
        10, lambda: self._SimulateKeyPress(test_ui.ENTER_KEY))

    self.assertIsNone(self._ui.WaitKeysOnce(test_ui.ENTER_KEY, timeout=5))
    self.assertFalse(self.key_callbacks)

  def testWaitKeysOnceMultipleKey(self):
    self._timeline.AddEvent(
        2, lambda: self._SimulateKeyPress('A'))
    self._timeline.AddEvent(
        1, lambda: self._SimulateKeyPress('B'))
    self._timeline.AddEvent(
        7, lambda: self._SimulateKeyPress('C'))

    self.assertEqual('B', self._ui.WaitKeysOnce(['A', 'B', 'C']))
    self.assertFalse(self.key_callbacks)

  def testWaitKeysOnceMultipleKeyTimeout(self):
    self._timeline.AddEvent(
        2, lambda: self._SimulateKeyPress('A'))
    self._timeline.AddEvent(
        1, lambda: self._SimulateKeyPress('B'))
    self._timeline.AddEvent(
        7, lambda: self._SimulateKeyPress('C'))

    self.assertEqual('B', self._ui.WaitKeysOnce(['A', 'B', 'C'], timeout=10))
    self.assertFalse(self.key_callbacks)

  def testWaitKeysOnceMultipleKeyTimeoutNoKey(self):
    self._timeline.AddEvent(
        2, lambda: self._SimulateKeyPress('A'))
    self._timeline.AddEvent(
        7, lambda: self._SimulateKeyPress('B'))
    self._timeline.AddEvent(
        4, lambda: self._SimulateKeyPress('C'))

    self.assertIsNone(self._ui.WaitKeysOnce(['A', 'B', 'C'], timeout=1))
    self.assertFalse(self.key_callbacks)


class TestCaseWithUITest(unittest.TestCase):

  def setUp(self):
    self._patchers = []

    self._timeline = mock_time_utils.TimeLine()
    self._patchers.extend(mock_time_utils.MockAll(test_ui, self._timeline))

    self._test = test_ui.TestCaseWithUI()
    self._test.ui_class = mock.Mock

    self._handler_exception_hook = None

    self._mock_event_loop = mock.Mock()
    self._CreatePatcher(
        test_ui, 'EventLoop').side_effect = self._StubEventLoopConstructor

    self._event_loop_end = Queue.Queue()

    self._mock_event_loop.Run.side_effect = self._StubEventLoopRun
    self._mock_event_loop.PostNewEvent.side_effect = (
        self._StubEventLoopPostNewEvent)

  def _StubEventLoopConstructor(self, handler_exception_hook):
    self._handler_exception_hook = handler_exception_hook
    return self._mock_event_loop

  def _StubEventLoopPostNewEvent(self, event_type, **kwargs):
    if event_type == _EventType.END_EVENT_LOOP:
      self._event_loop_end.put(kwargs)

  def _StubEventLoopRun(self):
    end_event_kwargs = self._event_loop_end.get()
    status = end_event_kwargs['status']
    if status == state.TestState.FAILED:
      raise type_utils.TestFailure(end_event_kwargs['error_msg'])

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
    self.assertEqual(10, self._timeline.GetTime())

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
    self.assertEqual(10, self._timeline.GetTime())

  def testWaitTaskEndTimeout(self):
    times = []
    def _RunTest():
      while True:
        times.append(self._timeline.GetTime())
        self._test.WaitTaskEnd(timeout=2)

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
  random.seed(0)
  unittest.main()
