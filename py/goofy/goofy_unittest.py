#!/usr/bin/python -u
#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The unittest for the main factory flow that runs the factory test."""


from __future__ import print_function

import factory_common  # pylint: disable=W0611

import cPickle as pickle
import imp
import logging
import math
import mox
import subprocess
import threading
import time
import unittest

from mox import IgnoreArg
from ws4py.client import WebSocketBaseClient

from cros.factory.goofy import goofy
from cros.factory.test import factory
from cros.factory.test import state

from cros.factory.goofy.goofy import Goofy
from cros.factory.goofy.prespawner import PytestPrespawner
from cros.factory.goofy.test_environment import Environment
from cros.factory.test.event import Event
from cros.factory.test.factory import TestState
from cros.factory.test.test_lists import test_lists
from cros.factory.utils import net_utils
from cros.factory.utils.process_utils import Spawn


def _BuildTestList(test_items, options):
  """Build a test list

  Args:
    test_items: the body of "with test_lists.TestList(...)" statement.  The
      'test_lists' module is imported, so you can use test_lists.FactoryTest or
      other functions to generate test items.  The top level should indent "4"
      spaces.
    options: set test list options, the "options" variable is imported.  Should
      indent "4" spaces.
  """

  _TEST_LIST_TEMPLATE = """
import factory_common
from cros.factory.test.test_lists import test_lists
from cros.factory.utils.net_utils import WLAN

def CreateTestLists():
  with test_lists.TestList(id='stub_test_list', label_en='label') as test_list:
    options = test_list.options

    # Load dummy plugin config as default.
    options.plugin_config_name = 'goofy_unittest'
    {options}
    {test_items}
  """

  source = _TEST_LIST_TEMPLATE.format(test_items=test_items, options=options)
  module = imp.new_module('stub_test_list')
  module.__file__ = '/dev/null'
  exec source in module.__dict__

  created_test_lists = test_lists.BuildTestLists(module)
  assert len(created_test_lists) == 1
  return created_test_lists.values()[0]


def _MockGetTestList(goofy_instance, test_list):
  """Mock "GetTestList" function in goofy.

  Mock "GetTestList" function in goofy, so the active test list will always be
  the given one.
  """
  def _GetTestList(test_list_id):
    del test_list_id
    return test_list

  goofy_instance.GetTestList = _GetTestList


def init_goofy(env=None, test_list=None, options='', restart=True, ui='none'):
  """Initializes and returns a Goofy."""
  new_goofy = Goofy()
  args = ['--ui', ui]
  if restart:
    args.append('--restart')
  if test_list:
    test_list = _BuildTestList(test_list, options)
    _MockGetTestList(new_goofy, test_list)

  logging.info('Running goofy with args %r', args)
  new_goofy.dut.info.Overrides('mlb_serial_number', 'mlb_sn_123456789')
  new_goofy.dut.info.Overrides('serial_number', 'sn_123456789')
  new_goofy.init(args, env or Environment())
  return new_goofy


def mock_pytest(spawn, name, test_state, error_msg, func=None):
  """Adds a side effect that a mock pytest will be executed.

  Args:
    spawn: The mock Spawn object.
    name: The name of the pytest to be mocked.
    test_state: The resulting test state.
    error_msg: The error message.
    func: Optional callable to run inside the side effect function.
  """
  def side_effect(info, unused_env):
    assert info.pytest_name == name
    if func:
      func()
    with open(info.results_path, 'w') as out:
      pickle.dump((test_state, error_msg), out)
    return Spawn(['true'], stdout=subprocess.PIPE)

  spawn(IgnoreArg(), IgnoreArg()).WithSideEffects(side_effect)


class GoofyTest(unittest.TestCase):
  """Base class for Goofy test cases."""
  options = ''
  ui = 'none'
  test_list = None  # Overridden by subclasses

  def setUp(self):
    # Some test cases might stub out PytestPrespawner.spawn. To restore it
    # after each test case, we need to save it now.
    self.original_spawn = PytestPrespawner.spawn
    # Log the name of the test we're about to run, to make it easier
    # to grok the logs.
    logging.info('*** Running test %s', type(self).__name__)
    state.DEFAULT_FACTORY_STATE_PORT = net_utils.FindUnusedTCPPort()
    logging.info('Using port %d for factory state',
                 state.DEFAULT_FACTORY_STATE_PORT)
    self.mocker = mox.Mox()
    self.env = self.mocker.CreateMock(Environment)
    self.state = state.get_instance()
    self.before_init_goofy()
    self.mocker.ReplayAll()
    self.goofy = init_goofy(self.env, self.test_list, self.options,
                            ui=self.ui)
    self.mocker.VerifyAll()
    self.mocker.ResetAll()
    self.mockAnything = mox.MockAnything()

  def tearDown(self):
    self.goofy.destroy()

    # Make sure we're not leaving any extra threads hanging around
    # after a second.
    for _ in range(10):
      extra_threads = [t for t in threading.enumerate()
                       if t != threading.current_thread()]
      if not extra_threads:
        break
      logging.info('Waiting for %d threads to die', len(extra_threads))

      # Wait another 100 ms
      time.sleep(.1)

    self.assertEqual([], extra_threads)

    # Restore PytestPrespawner.spawn
    PytestPrespawner.spawn = self.original_spawn

  def _wait(self):
    """Waits for any pending invocations in Goofy to complete.

    Waits for any pending invocations in Goofy to complete,
    and verifies and resets all mocks.
    """
    self.goofy.wait()
    self.mocker.VerifyAll()
    self.mocker.ResetAll()

  def before_init_goofy(self):
    """Hook invoked before init_goofy."""

  def check_one_test(self, spawn, test_id, name, passed, error_msg,
                     trigger=None, does_not_start=False, setup_mocks=True,
                     expected_count=1):
    """Runs a single pytest, waiting for it to complete.

    Args:
      test_id: The ID of the test expected to run.
      name: The pytest name of the test expected to run.
      passed: The TestState that whether the test should pass.
      error_msg: The error message, if any.
      trigger: An optional callable that will be executed after mocks are
        set up to trigger the pytest.  If None, then the test is
        expected to start itself.
      does_not_start: If True, checks that the test is not expected to start
        (e.g., due to an unsatisfied require_run).
      setup_mocks: If True, sets up mocks for the test runs.
      expected_count: The expected run count.
    """
    if setup_mocks and not does_not_start:
      mock_pytest(spawn, name, passed, error_msg)
    self.mocker.ReplayAll()
    if trigger:
      trigger()
    self.assertTrue(self.goofy.run_once())
    self.assertEqual([] if does_not_start else [test_id],
                     [test.path for test in self.goofy.invocations])
    self._wait()
    test_state = self.state.get_test_state(test_id)
    self.assertEqual(passed, test_state.status)
    self.assertEqual(0 if does_not_start else expected_count, test_state.count)
    self.assertEqual(error_msg, test_state.error_msg)


class GoofyUITest(GoofyTest):
  ui = 'chrome'

  def __init__(self, *args, **kwargs):
    super(GoofyUITest, self).__init__(*args, **kwargs)
    self.events = None
    self.ws_done = None

  def before_init_goofy(self):
    # Keep a record of events we received
    self.events = []
    # Trigger this event once the web socket closes
    self.ws_done = threading.Event()

  def waitForWebSocketClose(self):
    self.ws_done.wait()

  def setUpWebSocketMock(self):
    class MyClient(WebSocketBaseClient):
      """The web socket client class."""
      # pylint: disable=E0213
      def handshake_ok(socket_self):
        pass

      def received_message(socket_self, message):
        event = Event.from_json(str(message))
        logging.info('Test client received %s', event)
        self.events.append(event)
        if event.type == Event.Type.HELLO:
          socket_self.send(Event(Event.Type.KEEPALIVE,
                                 uuid=event.uuid).to_json())

    ws = MyClient('ws://%s:%d/event' %
                  (net_utils.LOCALHOST, state.DEFAULT_FACTORY_STATE_PORT),
                  protocols=None, extensions=None)

    def open_web_socket():
      ws.connect()
      # Simulate setting the test widget size/position, since goofy
      # waits for it.
      factory.set_shared_data('test_widget_size', [100, 200],
                              'test_widget_position', [300, 400])
      ws.run()
      self.ws_done.set()
    # pylint: disable=W0108
    self.env.controller_ready_for_ui().WithSideEffects(
        lambda: threading.Thread(target=open_web_socket).start()
    ).AndReturn(None)


# A simple test list with three tests.
ABC_TEST_LIST = """
    test_lists.OperatorTest(id='a', pytest_name='a_A')
    test_lists.OperatorTest(id='b', pytest_name='b_B')
    test_lists.OperatorTest(id='c', pytest_name='c_C')
"""


class BasicTest(GoofyTest):
  """A simple test case that checks that tests are run in the correct order."""
  test_list = ABC_TEST_LIST
  def runTest(self):
    # Stub out PytestPrespawner.spawn to mock pytest invocation.
    PytestPrespawner.spawn = self.mocker.CreateMock(PytestPrespawner.spawn)

    self.goofy.link_manager.UpdateStatus = self.mockAnything.UpdateStatus(False)
    self.check_one_test(PytestPrespawner.spawn, 'a', 'a_A', TestState.PASSED,
                        '')
    self.check_one_test(PytestPrespawner.spawn, 'b', 'b_B', TestState.FAILED,
                        'Uh-oh')
    self.check_one_test(PytestPrespawner.spawn, 'c', 'c_C', TestState.FAILED,
                        'Uh-oh')
    self.assertEqual(
        'id: null\n'
        'path: null\n'
        'subtests:\n'
        '- {count: 1, error_msg: null, id: a, path: a, status: PASSED}\n'
        '- {count: 1, error_msg: Uh-oh, id: b, path: b, status: FAILED}\n'
        '- {count: 1, error_msg: Uh-oh, id: c, path: c, status: FAILED}\n',
        self.goofy.test_list.as_yaml(
            factory.get_state_instance().get_test_states()))
    self.mockAnything.VerifyAll()


class WebSocketTest(GoofyUITest):
  """A test case that checks the behavior of web sockets."""
  test_list = ABC_TEST_LIST
  def runTest(self):
    # Stub out PytestPrespawner.spawn to mock pytest invocation.
    PytestPrespawner.spawn = self.mocker.CreateMock(PytestPrespawner.spawn)

    self.goofy.link_manager.UpdateStatus = self.mockAnything.UpdateStatus(False)
    self.setUpWebSocketMock()

    self.check_one_test(PytestPrespawner.spawn, 'a', 'a_A', TestState.PASSED,
                        '')
    self.check_one_test(PytestPrespawner.spawn, 'b', 'b_B', TestState.FAILED,
                        'Uh-oh')
    self.check_one_test(PytestPrespawner.spawn, 'c', 'c_C', TestState.FAILED,
                        'Uh-oh')

    # Kill Goofy and wait for the web socket to close gracefully
    self.goofy.destroy()
    self.waitForWebSocketClose()

    events_by_type = {}
    for event in self.events:
      events_by_type.setdefault(event.type, []).append(event)

    # There should be one hello event
    self.assertEqual(1, len(events_by_type[Event.Type.HELLO]))

    # Each test should have a transition to active, a transition to
    # active + visible, and then to its final state
    for path, final_status in (('a', TestState.PASSED),
                               ('b', TestState.FAILED),
                               ('c', TestState.FAILED)):
      statuses = [
          event.state['status']
          for event in events_by_type[Event.Type.STATE_CHANGE]
          if event.path == path]
      self.assertEqual(
          ['ACTIVE', 'ACTIVE', final_status],
          statuses)
    self.mockAnything.VerifyAll()


class ShutdownTest(GoofyTest):
  """A test case that checks the behavior of shutdown."""
  test_list = """
    test_lists.RebootStep(id='shutdown', iterations=3),
    test_lists.OperatorTest(id='a', pytest_name='a_A')
  """

  def runTest(self):
    # Stub out PytestPrespawner.spawn to mock pytest invocation.
    PytestPrespawner.spawn = self.mocker.CreateMock(PytestPrespawner.spawn)

    # Expect a reboot request.
    mock_pytest(PytestPrespawner.spawn, 'shutdown', TestState.ACTIVE, '',
                func=lambda: self.goofy.shutdown('reboot'))
    self.env.shutdown('reboot').AndReturn(True)
    self.mocker.ReplayAll()
    self.assertTrue(self.goofy.run_once())
    self._wait()

    # That should have enqueued a task that will cause Goofy
    # to shut down.
    self.assertFalse(self.goofy.run_once())

    # There should be a list of tests to run on wake-up.
    test_list_iterator = self.state.get_shared_data(
        goofy.TESTS_AFTER_SHUTDOWN, True)
    self.assertEqual('shutdown', test_list_iterator.stack[-1])
    self._wait()

    # Kill and restart Goofy to simulate the first two shutdown iterations.
    # Goofy should call for another shutdown.
    for _ in range(2):
      self.mocker.ResetAll()
      # Goofy should invoke shutdown test to do post-shutdown verification.
      mock_pytest(PytestPrespawner.spawn, 'shutdown', TestState.PASSED, '')
      # Goofy should invoke shutdown again to start next iteration.
      mock_pytest(PytestPrespawner.spawn, 'shutdown', TestState.ACTIVE,
                  '', func=lambda: self.goofy.shutdown('reboot'))
      self.env.shutdown('reboot').AndReturn(True)
      self.mocker.ReplayAll()
      self.goofy.destroy()
      self.goofy = init_goofy(self.env, self.test_list, restart=False)
      self.goofy.run_once()
      self._wait()

    # The third shutdown iteration.
    self.mocker.ResetAll()
    # Goofy should invoke shutdown test to do post-shutdown verification.
    mock_pytest(PytestPrespawner.spawn, 'shutdown', TestState.PASSED, '')
    self.mocker.ReplayAll()
    self.goofy.destroy()
    self.goofy = init_goofy(self.env, self.test_list, restart=False)
    self.goofy.run_once()
    self._wait()

    # No more shutdowns - now 'a' should run.
    self.check_one_test(PytestPrespawner.spawn, 'a', 'a_A', TestState.PASSED,
                        '')


class RebootFailureTest(GoofyTest):
  """A test case that checks the behavior of reboot failure."""
  test_list = """
    test_lists.RebootStep(id='shutdown'),
  """

  def runTest(self):
    # Stub out PytestPrespawner.spawn to mock pytest invocation.
    PytestPrespawner.spawn = self.mocker.CreateMock(PytestPrespawner.spawn)

    # Expect a reboot request
    mock_pytest(PytestPrespawner.spawn, 'shutdown', TestState.ACTIVE, '',
                func=lambda: self.goofy.shutdown('reboot'))
    self.env.shutdown('reboot').AndReturn(True)
    self.mocker.ReplayAll()
    self.assertTrue(self.goofy.run_once())
    self._wait()

    # That should have enqueued a task that will cause Goofy
    # to shut down.
    self.mocker.ReplayAll()
    self.assertFalse(self.goofy.run_once())
    self._wait()

    # Something pretty close to the current time should be written
    # as the shutdown time.
    shutdown_time = self.state.get_shared_data('shutdown_time')
    self.assertTrue(math.fabs(time.time() - shutdown_time) < 2)

    # Kill and restart Goofy to simulate a reboot.
    # Goofy should fail the test since it has been too long.
    self.goofy.destroy()

    self.mocker.ResetAll()
    # Mock a failed shutdown post-shutdown verification.
    mock_pytest(PytestPrespawner.spawn, 'shutdown', TestState.FAILED,
                'Reboot failed.')
    self.mocker.ReplayAll()
    self.goofy = init_goofy(self.env, self.test_list, restart=False)
    self.goofy.run_once()
    self._wait()

    test_state = factory.get_state_instance().get_test_state('shutdown')
    self.assertEquals(TestState.FAILED, test_state.status)
    logging.info('%s', test_state.error_msg)
    self.assertTrue(test_state.error_msg.startswith(
        'Reboot failed.'))


class NoAutoRunTest(GoofyTest):
  """A test case that checks the behavior when auto_run_on_start is False."""
  test_list = ABC_TEST_LIST
  options = 'options.auto_run_on_start = False'

  def _runTestB(self):
    # Stub out PytestPrespawner.spawn to mock pytest invocation.
    PytestPrespawner.spawn = self.mocker.CreateMock(PytestPrespawner.spawn)

    # There shouldn't be anything to do at startup, since auto_run_on_start
    # is unset.
    self.mocker.ReplayAll()
    self.goofy.run_once()
    self.assertEqual({}, self.goofy.invocations)
    self._wait()

    # Tell Goofy to run 'b'.
    self.check_one_test(
        PytestPrespawner.spawn, 'b', 'b_B', TestState.PASSED, '',
        trigger=lambda: self.goofy.handle_switch_test(
            Event(Event.Type.SWITCH_TEST, path='b')))

  def runTest(self):
    self._runTestB()
    # No more tests to run now.
    self.mocker.ReplayAll()
    self.goofy.run_once()
    self.assertEqual({}, self.goofy.invocations)


class PyTestTest(GoofyTest):
  """Tests the Python test driver.

  Note that no mocks are used here, since it's easy enough to just have the
  Python driver run a 'real' test (execpython).
  """
  test_list = """
    test_lists.OperatorTest(
        id='a', pytest_name='execpython',
        dargs={'script': 'assert "Tomato" == "Tomato"'})
    test_lists.OperatorTest(
        id='b', pytest_name='execpython',
        dargs={'script': ("assert 'Pa-TAY-to' == 'Pa-TAH-to', "
                          "'Let\\\\\'s call the whole thing off'")})
  """

  def runTest(self):
    self.goofy.run_once()
    self.assertEquals(['a'],
                      [test.id for test in self.goofy.invocations])
    self.goofy.wait()
    self.assertEquals(
        TestState.PASSED,
        factory.get_state_instance().get_test_state('a').status)

    self.goofy.run_once()
    self.assertEquals(['b'],
                      [test.id for test in self.goofy.invocations])
    self.goofy.wait()
    failed_state = factory.get_state_instance().get_test_state('b')
    self.assertEquals(TestState.FAILED, failed_state.status)
    self.assertTrue(
        """Let's call the whole thing off""" in failed_state.error_msg,
        failed_state.error_msg)


class PyLambdaTest(GoofyTest):
  """A test case that checks the behavior of execpython."""
  test_list = """
    test_lists.OperatorTest(
        id='a', pytest_name='execpython',
        dargs={'script': lambda env: 'raise ValueError("It"+"Failed")'})
  """

  def runTest(self):
    self.goofy.run_once()
    self.goofy.wait()
    failed_state = factory.get_state_instance().get_test_state('a')
    self.assertEquals(TestState.FAILED, failed_state.status)
    self.assertTrue(
        """ItFailed""" in failed_state.error_msg,
        failed_state.error_msg)


class MultipleIterationsTest(GoofyTest):
  """Tests running a test multiple times."""
  test_list = """
    test_lists.OperatorTest(id='a', pytest_name='a_A'),
    test_lists.OperatorTest(id='b', pytest_name='b_B', iterations=3),
    test_lists.OperatorTest(id='c', pytest_name='c_C', iterations=3),
    test_lists.OperatorTest(id='d', pytest_name='d_D'),
  """

  def runTest(self):
    # Stub out PytestPrespawner.spawn to mock pytest invocation.
    PytestPrespawner.spawn = self.mocker.CreateMock(PytestPrespawner.spawn)

    self.goofy.link_manager.UpdateStatus = self.mockAnything.UpdateStatus(False)
    self.check_one_test(PytestPrespawner.spawn, 'a', 'a_A', TestState.PASSED,
                        '')

    mock_pytest(PytestPrespawner.spawn, 'b_B', TestState.PASSED, '')
    mock_pytest(PytestPrespawner.spawn, 'b_B', TestState.PASSED, '')
    mock_pytest(PytestPrespawner.spawn, 'b_B', TestState.PASSED, '')
    self.check_one_test(PytestPrespawner.spawn, 'b', 'b_B', TestState.PASSED,
                        '', setup_mocks=False, expected_count=3)

    mock_pytest(PytestPrespawner.spawn, 'c_C', TestState.PASSED, '')
    mock_pytest(PytestPrespawner.spawn, 'c_C', TestState.FAILED,
                'I bent my wookie')
    # iterations=3, but it should stop after the first failed iteration.
    self.check_one_test(PytestPrespawner.spawn, 'c', 'c_C', TestState.FAILED,
                        'I bent my wookie', setup_mocks=False, expected_count=2)

    self.check_one_test(PytestPrespawner.spawn, 'd', 'd_D', TestState.PASSED,
                        '')
    self.mockAnything.VerifyAll()


class RequireRunTest(GoofyTest):
  """Tests FactoryTest require_run argument."""
  options = """
    options.auto_run_on_start = False
  """
  test_list = """
    test_lists.OperatorTest(id='a', pytest_name='a_A')
    test_lists.OperatorTest(id='b', pytest_name='b_B', require_run='a')
  """

  def runTest(self):
    # Stub out PytestPrespawner.spawn to mock pytest invocation.
    PytestPrespawner.spawn = self.mocker.CreateMock(PytestPrespawner.spawn)

    self.goofy.restart_tests(
        root=self.goofy.test_list.lookup_path('b'))
    self.check_one_test(PytestPrespawner.spawn, 'b', 'b_B', TestState.FAILED,
                        'Required tests [a] have not been run yet',
                        does_not_start=True)

    self.goofy.restart_tests()
    self.check_one_test(PytestPrespawner.spawn, 'a', 'a_A', TestState.PASSED,
                        '')
    self.check_one_test(PytestPrespawner.spawn, 'b', 'b_B', TestState.PASSED,
                        '')


class RequireRunPassedTest(GoofyTest):
  """Tests FactoryTest require_run argument with Passed syntax."""
  options = """
    options.auto_run_on_start = True
  """
  test_list = """
    test_lists.OperatorTest(id='a', pytest_name='a_A')
    test_lists.OperatorTest(id='b', pytest_name='b_B',
                            require_run=test_lists.Passed('a'))
  """

  def runTest(self):
    # Stub out PytestPrespawner.spawn to mock pytest invocation.
    PytestPrespawner.spawn = self.mocker.CreateMock(PytestPrespawner.spawn)

    self.goofy.link_manager.UpdateStatus = self.mockAnything.UpdateStatus(False)
    self.check_one_test(PytestPrespawner.spawn, 'a', 'a_A', TestState.FAILED,
                        '')
    self.check_one_test(PytestPrespawner.spawn, 'b', 'b_B', TestState.FAILED,
                        'Required tests [a] have not been run yet',
                        does_not_start=True)

    self.goofy.restart_tests()
    self.check_one_test(PytestPrespawner.spawn, 'a', 'a_A', TestState.PASSED,
                        '', expected_count=2)
    self.check_one_test(PytestPrespawner.spawn, 'b', 'b_B', TestState.PASSED,
                        '')
    self.mockAnything.VerifyAll()


class StopOnFailureTest(GoofyTest):
  """A unittest that checks if the goofy will stop after a test fails."""
  test_list = ABC_TEST_LIST
  options = """
    options.auto_run_on_start = True
    options.stop_on_failure = True
  """

  def runTest(self):
    # Stub out PytestPrespawner.spawn to mock pytest invocation.
    PytestPrespawner.spawn = self.mocker.CreateMock(PytestPrespawner.spawn)

    self.goofy.link_manager.UpdateStatus = self.mockAnything.UpdateStatus(False)
    mock_pytest(PytestPrespawner.spawn, 'a_A', TestState.PASSED, '')
    mock_pytest(PytestPrespawner.spawn, 'b_B', TestState.FAILED, 'Oops!')
    self.mocker.ReplayAll()
    # Make sure events are all processed.
    for _ in range(3):
      self.assertTrue(self.goofy.run_once())
      self.goofy.wait()

    state_instance = factory.get_state_instance()
    self.assertEquals(
        [TestState.PASSED, TestState.FAILED, TestState.UNTESTED],
        [state_instance.get_test_state(x).status for x in ['a', 'b', 'c']])
    self._wait()
    self.mockAnything.VerifyAll()


class ParallelTest(GoofyTest):
  """A test for parallel tests, goofy should run them in parallel."""

  test_list = """
    with test_lists.FactoryTest(id='parallel', parallel=True):
      test_lists.OperatorTest(id='a', pytest_name='a_A')
      test_lists.OperatorTest(id='b', pytest_name='b_B')
      test_lists.OperatorTest(id='c', pytest_name='c_C')
  """

  def runTest(self):
    PytestPrespawner.spawn = self.mocker.CreateMock(PytestPrespawner.spawn)
    mock_pytest(PytestPrespawner.spawn, 'a_A', TestState.PASSED, '')
    mock_pytest(PytestPrespawner.spawn, 'b_B', TestState.PASSED, '')
    mock_pytest(PytestPrespawner.spawn, 'c_C', TestState.PASSED, '')
    self.mocker.ReplayAll()

    self.goofy.run_once()
    self.assertSetEqual({'a', 'b', 'c'},
                        {test.id for test in self.goofy.invocations})
    self.goofy.wait()

    self.mocker.VerifyAll()
    self.mocker.ResetAll()


class WaivedTestTest(GoofyTest):
  """A test to verify that a waived test does not block test list execution."""

  options = """
    options.auto_run_on_start = True
    options.stop_on_failure = True
  """
  test_list = """
    test_lists.FactoryTest(id='waived', pytest_name='waived_test', waived=True)
    test_lists.FactoryTest(id='normal', pytest_name='normal_test')
  """

  def runTest(self):
    PytestPrespawner.spawn = self.mocker.CreateMock(PytestPrespawner.spawn)
    mock_pytest(PytestPrespawner.spawn, 'waived_test',
                TestState.FAILED_AND_WAIVED, 'Failed and waived')
    mock_pytest(PytestPrespawner.spawn, 'normal_test', TestState.PASSED, '')
    self.mocker.ReplayAll()

    for _ in range(2):
      self.assertTrue(self.goofy.run_once())
      self.goofy.wait()

    state_instance = factory.get_state_instance()
    self.assertEquals(
        [TestState.FAILED_AND_WAIVED, TestState.PASSED],
        [state_instance.get_test_state(x).status for x in ['waived', 'normal']])
    self._wait()


class NoHostTest(GoofyUITest):
  """A test to verify that tests marked 'no_host' run without host UI."""

  test_list = """
    test_lists.OperatorTest(
        id='a', pytest_name='execpython', no_host=True,
        dargs={'script': 'assert "Tomato" == "Tomato"'})
    test_lists.OperatorTest(
        id='b', pytest_name='execpython', no_host=False,
        dargs={'script': 'assert "Tomato" == "Tomato"'})
  """

  def runTest(self):
    # No UI for test 'a'
    self.mocker.ReplayAll()
    self.goofy.run_once()
    self._wait()
    self.assertEquals(
        TestState.PASSED,
        factory.get_state_instance().get_test_state('a').status)

    # Start the UI for test 'b'
    self.setUpWebSocketMock()
    self.mocker.ReplayAll()
    self.goofy.run_once()
    self._wait()
    self.assertEquals(
        TestState.PASSED,
        factory.get_state_instance().get_test_state('b').status)


if __name__ == '__main__':
  factory.init_logging('goofy_unittest')
  goofy._inited_logging = True  # pylint: disable=protected-access
  goofy.suppress_chroot_warning = True

  unittest.main()
