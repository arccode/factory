#!/usr/bin/env python2
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The unittest for the main factory flow that runs the factory test."""


from __future__ import print_function

import cPickle as pickle
import inspect
import logging
import math
import os
import subprocess
import threading
import time
import traceback
import unittest

import mox
from mox import IgnoreArg
from six import itervalues
from six.moves import xrange
from ws4py.client import WebSocketBaseClient

import factory_common  # pylint: disable=unused-import
from cros.factory.device import info as device_info
from cros.factory.goofy import goofy
from cros.factory.goofy.goofy import Goofy
from cros.factory.goofy import prespawner
from cros.factory.goofy.test_environment import Environment
from cros.factory.test import device_data
from cros.factory.test.env import goofy_proxy
from cros.factory.test.env import paths
from cros.factory.test.event import Event
from cros.factory.test import state
from cros.factory.test.state import TestState
from cros.factory.test.test_lists import manager
from cros.factory.test.utils import pytest_utils
from cros.factory.utils import log_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils


def MockPytest(name, test_state, exc_repr, func=None):
  """Adds a side effect that a mock pytest will be executed.

  Args:
    name: The name of the pytest to be mocked.
    test_state: The resulting test state.
    exc_repr: The error message.
    func: Optional callable to run inside the side effect function.
  """
  def SideEffect(info, unused_env):
    assert info.pytest_name == name
    if func:
      func()
    with open(info.results_path, 'w') as out:
      tb_list = traceback.extract_stack(inspect.currentframe())
      result = pytest_utils.PytestExecutionResult(
          test_state, failures=[pytest_utils.PytestExceptionInfo(exc_repr,
                                                                 tb_list)])
      pickle.dump(result, out)
    return process_utils.Spawn(['true'], stdout=subprocess.PIPE)

  prespawner.Prespawner.spawn(
      IgnoreArg(), IgnoreArg()).WithSideEffects(SideEffect)


class GoofyTest(unittest.TestCase):
  """Base class for Goofy test cases."""
  test_list = {}  # Overridden by subclasses
  mock_goofy_server = True
  mock_spawn_pytest = True

  def setUp(self):
    self.original_get_state_instance = state.GetInstance
    # Log the name of the test we're about to run, to make it easier
    # to grok the logs.
    logging.info('*** Running test %s', type(self).__name__)
    goofy_proxy.DEFAULT_GOOFY_PORT = net_utils.FindUnusedTCPPort()
    logging.info('Using port %d for factory state',
                 goofy_proxy.DEFAULT_GOOFY_PORT)
    self.mocker = mox.Mox()
    self.env = self.mocker.CreateMock(Environment)
    self.state = state.StubFactoryState()

    if self.mock_spawn_pytest:
      self.mocker.StubOutWithMock(prespawner.Prespawner, 'spawn')

    if self.mock_goofy_server:
      self.mocker.StubOutClassWithMocks(goofy.goofy_server, 'GoofyServer')
      state.GetInstance = lambda: self.state
    self.mocker.StubOutWithMock(state, 'ClearState')
    self.mocker.StubOutWithMock(state, 'FactoryState')

    self.test_list_manager = self.mocker.CreateMock(manager.Manager)

    self.BeforeInitGoofy()

    self.RecordGoofyInit()
    self.mocker.ReplayAll()
    self.InitGoofy()
    self.mocker.VerifyAll()
    self.mocker.ResetAll()

    self.AfterInitGoofy()

  def tearDown(self):
    try:
      self.mocker.VerifyAll()
      self.mocker.ResetAll()

      self.RecordGoofyDestroy()
      self.mocker.ReplayAll()

      self.goofy.Destroy()
      self.mocker.VerifyAll()
      self.mocker.ResetAll()

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
    finally:
      state.GetInstance = self.original_get_state_instance
      self.mocker.UnsetStubs()

  def InitGoofy(self, restart=True):
    """Initializes and returns a Goofy."""
    new_goofy = Goofy()
    args = []
    if restart:
      args.append('--restart')

    logging.info('Running goofy with args %r', args)
    # Overrides all dut info, so goofy don't try to get those infos which spend
    # lots of time.
    for prop in device_info._INFO_PROP_LIST:  # pylint: disable=protected-access
      new_goofy.dut.info.Overrides(prop, '')
    new_goofy.dut.info.Overrides(device_data.NAME_MLB_SERIAL_NUMBER,
                                 'mlb_sn_123456789')
    new_goofy.dut.info.Overrides(device_data.NAME_SERIAL_NUMBER, 'sn_123456789')
    new_goofy.test_list_manager = self.test_list_manager
    new_goofy.Init(args, self.env or Environment())
    self.goofy = new_goofy

  def RecordGoofyInit(self, restart=True):
    if restart:
      state.ClearState()

    state.FactoryState().AndReturn(self.state)

    if self.mock_goofy_server:
      server = goofy.goofy_server.GoofyServer((
          goofy_proxy.DEFAULT_GOOFY_BIND,
          goofy_proxy.DEFAULT_GOOFY_PORT))
      # We do not use mox for server.serve_forever, since the method is run in
      # another thread, and mox object are NOT thread safe.
      server.serve_forever = lambda *args, **kwargs: None
      server.RegisterPath('/',
                          os.path.join(paths.FACTORY_PYTHON_PACKAGE_DIR,
                                       'goofy/static')).InAnyOrder()
      server.RegisterData('/index.html', 'text/html', IgnoreArg()).InAnyOrder()
      server.AddRPCInstance(goofy_proxy.STATE_URL, self.state).InAnyOrder()
      server.AddHTTPGetHandler('/event', IgnoreArg()).InAnyOrder()
      server.RegisterData('/js/goofy-translations.js', 'application/javascript',
                          IgnoreArg()).InAnyOrder()
      server.RegisterData('/css/i18n.css', 'text/css', IgnoreArg()).InAnyOrder()

    if self.test_list:
      test_list = manager.BuildTestListForUnittest(
          test_list_config=self.test_list)
      test_list.options.read_device_data_from_vpd_on_init = False
      self.test_list_manager.BuildAllTestLists().AndReturn(
          ({'test': test_list}, {}))
      self.test_list_manager.GetActiveTestListId().AndReturn('test')

  def RecordGoofyDestroy(self):
    if self.mock_goofy_server:
      self.goofy.goofy_server.shutdown()
      self.goofy.goofy_server.server_close()

  def _Wait(self):
    """Waits for any pending invocations in Goofy to complete.

    Waits for any pending invocations in Goofy to complete,
    and verifies and resets all mocks.
    """
    self.goofy.Wait()
    self.mocker.VerifyAll()
    self.mocker.ResetAll()

  def BeforeInitGoofy(self):
    """Hook invoked before InitGoofy."""

  def AfterInitGoofy(self):
    """Hook invoked after InitGoofy."""

  def CheckOneTest(self, test_id, name, passed, error_msg,
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
      MockPytest(name, passed, error_msg)
    self.mocker.ReplayAll()
    if trigger:
      trigger()
    self.assertTrue(self.goofy.RunOnce())
    self.assertEqual(
        [] if does_not_start else [test_id],
        [invoc.test.path for invoc in itervalues(self.goofy.invocations)])
    self._Wait()
    test_state = self.state.GetTestState(test_id)
    self.assertEqual(passed, test_state.status)
    self.assertEqual(0 if does_not_start else expected_count, test_state.count)
    self.assertEqual(error_msg, test_state.error_msg)


class GoofyUITest(GoofyTest):
  mock_goofy_server = False

  def __init__(self, *args, **kwargs):
    super(GoofyUITest, self).__init__(*args, **kwargs)
    self.events = None
    self.ws_start = None
    self.ws_done = None

  def BeforeInitGoofy(self):
    # Keep a record of events we received
    self.events = []
    # Trigger this event once the web socket is ready
    self.ws_start = threading.Event()
    # Trigger this event once the web socket closes
    self.ws_done = threading.Event()

  def AfterInitGoofy(self):
    class MyClient(WebSocketBaseClient):
      """The web socket client class."""
      # pylint: disable=no-self-argument
      def handshake_ok(socket_self):
        pass

      def received_message(socket_self, message):
        event = Event.from_json(str(message))
        logging.info('Test client received %s', event)
        self.events.append(event)
        if event.type == Event.Type.HELLO:
          socket_self.send(Event(Event.Type.KEEPALIVE,
                                 uuid=event.uuid).to_json())
          self.ws_start.set()

    ws = MyClient('ws://%s:%d/event' %
                  (net_utils.LOCALHOST, goofy_proxy.DEFAULT_GOOFY_PORT),
                  protocols=None, extensions=None)

    def OpenWebSocket():
      ws.connect()
      ws.run()
      self.ws_done.set()

    # After goofy.Init(), it should be ready to accept a web socket
    process_utils.StartDaemonThread(target=OpenWebSocket)

  def WaitForWebSocketStart(self):
    self.ws_start.wait()

  def WaitForWebSocketStop(self):
    self.ws_done.wait()


# A simple test list with three tests.
ABC_TEST_LIST = [
    {'id': 'a', 'pytest_name': 'a_A', },
    {'id': 'b', 'pytest_name': 'b_B', },
    {'id': 'c', 'pytest_name': 'c_C', },
]


class BasicTest(GoofyUITest):
  """A simple test case that checks that tests are run in the correct order."""
  test_list = {
      'tests': ABC_TEST_LIST
  }

  def runTest(self):
    self.CheckOneTest('test:a', 'a_A', TestState.PASSED, '')
    self.CheckOneTest('test:b', 'b_B', TestState.FAILED, 'Uh-oh')
    self.CheckOneTest('test:c', 'c_C', TestState.FAILED, 'Uh-oh')
    self.assertEqual(
        dict(id=None, path='test:', subtests=[
            dict(count=1, error_msg=None, id='a', path='test:a',
                 status='PASSED'),
            dict(count=1, error_msg='Uh-oh', id='b', path='test:b',
                 status='FAILED'),
            dict(count=1, error_msg='Uh-oh', id='c', path='test:c',
                 status='FAILED'),
        ]),
        self.goofy.test_list.ToFactoryTestList().AsDict(
            state.GetInstance().GetTestStates()))


class WebSocketTest(GoofyUITest):
  """A test case that checks the behavior of web sockets."""
  test_list = {
      'tests': ABC_TEST_LIST
  }

  def CheckTestStatusChange(self, test_id, test_state):
    # The Goofy Server should receive the events in 2 seconds.
    for unused_t in xrange(20):
      statuses = []
      for event in self.events:
        if event.type == Event.Type.STATE_CHANGE and event.path == test_id:
          statuses.append(event.state['status'])
      if statuses == [TestState.UNTESTED, TestState.ACTIVE, test_state]:
        return True
      time.sleep(0.1)
    return False

  def runTest(self):
    self.WaitForWebSocketStart()
    self.CheckOneTest('test:a', 'a_A', TestState.PASSED, '')
    self.assertTrue(self.CheckTestStatusChange('test:a', TestState.PASSED))
    self.CheckOneTest('test:b', 'b_B', TestState.FAILED, 'Uh-oh')
    self.assertTrue(self.CheckTestStatusChange('test:b', TestState.FAILED))
    self.CheckOneTest('test:c', 'c_C', TestState.FAILED, 'Uh-oh')
    self.assertTrue(self.CheckTestStatusChange('test:c', TestState.FAILED))

    # Kill Goofy and wait for the web socket to close gracefully
    self.RecordGoofyDestroy()
    self.mocker.ReplayAll()
    self.goofy.Destroy()
    self.WaitForWebSocketStop()

    hello_event = 0
    for event in self.events:
      if event.type == Event.Type.HELLO:
        hello_event += 1

    # There should be one hello event
    self.assertEqual(1, hello_event)

    # Check the statuses again.
    self.assertTrue(self.CheckTestStatusChange('test:a', TestState.PASSED))
    self.assertTrue(self.CheckTestStatusChange('test:b', TestState.FAILED))
    self.assertTrue(self.CheckTestStatusChange('test:c', TestState.FAILED))


class ShutdownTest(GoofyUITest):
  """A test case that checks the behavior of shutdown."""
  test_list = {
      'tests': [
          {'inherit': 'RebootStep', 'iterations': 3},
          {'id': 'a', 'pytest_name': 'a_A'},
      ]
  }

  def runTest(self):
    # Expect a reboot request.
    MockPytest('shutdown', TestState.ACTIVE, '',
               func=lambda: self.goofy.Shutdown('reboot'))
    self.env.shutdown('reboot').AndReturn(True)
    self.mocker.ReplayAll()
    self.assertTrue(self.goofy.RunOnce())
    self._Wait()

    # That should have enqueued a task that will cause Goofy
    # to shut down.
    self.assertFalse(self.goofy.RunOnce())

    # There should be a list of tests to run on wake-up.
    test_list_iterator = self.state.DataShelfGetValue(
        goofy.TESTS_AFTER_SHUTDOWN, optional=True)
    self.assertEqual('test:RebootStep', test_list_iterator.Top().node)
    self._Wait()

    # Kill and restart Goofy to simulate the first two shutdown iterations.
    # Goofy should call for another shutdown.
    for _ in range(2):
      self.mocker.ResetAll()
      # Goofy should invoke shutdown test to do post-shutdown verification.
      MockPytest('shutdown', TestState.PASSED, '')
      # Goofy should invoke shutdown again to start next iteration.
      MockPytest('shutdown', TestState.ACTIVE,
                 '', func=lambda: self.goofy.Shutdown('reboot'))
      self.env.shutdown('reboot').AndReturn(True)
      self.RecordGoofyDestroy()
      self.RecordGoofyInit(restart=False)
      self.mocker.ReplayAll()
      self.goofy.Destroy()
      self.BeforeInitGoofy()
      self.InitGoofy(restart=False)
      self.AfterInitGoofy()
      self.goofy.RunOnce()
      self._Wait()

    # The third shutdown iteration.
    self.mocker.ResetAll()
    # Goofy should invoke shutdown test to do post-shutdown verification.
    MockPytest('shutdown', TestState.PASSED, '')
    self.RecordGoofyDestroy()
    self.RecordGoofyInit(restart=False)
    self.mocker.ReplayAll()
    self.goofy.Destroy()
    self.BeforeInitGoofy()
    self.InitGoofy(restart=False)
    self.AfterInitGoofy()
    self.goofy.RunOnce()
    self._Wait()

    # No more shutdowns - now 'a' should run.
    self.CheckOneTest('test:a', 'a_A', TestState.PASSED, '')


class RebootFailureTest(GoofyUITest):
  """A test case that checks the behavior of reboot failure."""
  test_list = {
      'tests': [
          'RebootStep'
      ]
  }

  def runTest(self):
    # Expect a reboot request
    MockPytest('shutdown', TestState.ACTIVE, '',
               func=lambda: self.goofy.Shutdown('reboot'))
    self.env.shutdown('reboot').AndReturn(True)
    self.mocker.ReplayAll()
    self.assertTrue(self.goofy.RunOnce())
    self._Wait()

    # That should have enqueued a task that will cause Goofy
    # to shut down.
    self.mocker.ReplayAll()
    self.assertFalse(self.goofy.RunOnce())
    self._Wait()

    # Something pretty close to the current time should be written
    # as the shutdown time.
    shutdown_time = self.state.DataShelfGetValue('shutdown_time')
    self.assertTrue(math.fabs(time.time() - shutdown_time) < 2)

    # Kill and restart Goofy to simulate a reboot.
    # Goofy should fail the test since it has been too long.
    self.RecordGoofyDestroy()
    self.mocker.ReplayAll()
    self.goofy.Destroy()

    self.mocker.ResetAll()
    # Mock a failed shutdown post-shutdown verification.
    MockPytest('shutdown', TestState.FAILED, 'Reboot failed.')
    self.RecordGoofyInit(restart=False)
    self.mocker.ReplayAll()
    self.BeforeInitGoofy()
    self.InitGoofy(restart=False)
    self.AfterInitGoofy()
    self.goofy.RunOnce()
    self._Wait()

    test_state = state.GetInstance().GetTestState(path='test:RebootStep')
    self.assertEqual(TestState.FAILED, test_state.status)
    logging.info('%s', test_state.error_msg)
    self.assertTrue(test_state.error_msg.startswith(
        'Reboot failed.'))


class NoAutoRunTest(GoofyUITest):
  """A test case that checks the behavior when auto_run_on_start is False."""
  test_list = {
      'tests': ABC_TEST_LIST,
      'options': {'auto_run_on_start': False}
  }

  def _runTestB(self):
    # There shouldn't be anything to do at startup, since auto_run_on_start
    # is unset.
    self.mocker.ReplayAll()
    self.goofy.RunOnce()
    self.assertEqual({}, self.goofy.invocations)
    self._Wait()

    # Tell Goofy to run 'b'.
    self.CheckOneTest(
        'test:b', 'b_B', TestState.PASSED, '',
        trigger=lambda: self.goofy.HandleEvent(
            Event(Event.Type.RESTART_TESTS, path='b')))

  def runTest(self):
    self._runTestB()
    # No more tests to run now.
    self.mocker.ReplayAll()
    self.goofy.RunOnce()
    self.assertEqual({}, self.goofy.invocations)


class PyTestTest(GoofyUITest):
  """Tests the Python test driver.

  Note that no mocks are used here, since it's easy enough to just have the
  Python driver run a 'real' test (exec_python).
  """
  test_list = {
      'tests': [
          {
              'id': 'a',
              'pytest_name': 'exec_python',
              'args': {
                  'script': 'assert "Tomato" == "Tomato"'
              }
          },
          {
              'id': 'b',
              'pytest_name': 'exec_python',
              'args': {
                  'script': 'assert "Pa-TAY-to" == "Pa-TAH-to", "TAY-TAH"'
              }
          }
      ]
  }

  mock_goofy_server = False
  mock_spawn_pytest = False

  def runTest(self):
    self.goofy.RunOnce()
    self.assertEqual(
        ['a'], [invoc.test.id for invoc in itervalues(self.goofy.invocations)])
    self.goofy.Wait()
    self.assertEqual(
        TestState.PASSED,
        state.GetInstance().GetTestState(path='test:a').status)

    self.goofy.RunOnce()
    self.assertEqual(
        ['b'], [invoc.test.id for invoc in itervalues(self.goofy.invocations)])
    self.goofy.Wait()
    failed_state = state.GetInstance().GetTestState(path='test:b')
    self.assertEqual(TestState.FAILED, failed_state.status)
    self.assertTrue(
        'TAY-TAH' in failed_state.error_msg,
        failed_state.error_msg)


class MultipleIterationsTest(GoofyUITest):
  """Tests running a test multiple times."""
  test_list = {
      'tests': [
          {'id': 'a', 'pytest_name': 'a_A'},
          {'id': 'b', 'pytest_name': 'b_B', 'iterations': 3},
          {'id': 'c', 'pytest_name': 'c_C', 'iterations': 3},
          {'id': 'd', 'pytest_name': 'd_D'},
      ]
  }

  def runTest(self):
    self.CheckOneTest('test:a', 'a_A', TestState.PASSED, '')

    MockPytest('b_B', TestState.PASSED, '')
    MockPytest('b_B', TestState.PASSED, '')
    MockPytest('b_B', TestState.PASSED, '')
    self.CheckOneTest('test:b', 'b_B', TestState.PASSED,
                      '', setup_mocks=False, expected_count=3)

    MockPytest('c_C', TestState.PASSED, '')
    MockPytest('c_C', TestState.FAILED, 'I bent my wookie')
    # iterations=3, but it should stop after the first failed iteration.
    self.CheckOneTest('test:c', 'c_C', TestState.FAILED,
                      'I bent my wookie', setup_mocks=False, expected_count=2)

    self.CheckOneTest('test:d', 'd_D', TestState.PASSED, '')


class RequireRunTest(GoofyUITest):
  """Tests FactoryTest require_run argument."""
  test_list = {
      'options': {
          'auto_run_on_start': False
      },
      'tests': [
          {'id': 'a', 'pytest_name': 'a_A'},
          {'id': 'b', 'pytest_name': 'b_B', 'require_run': 'a'},
      ]
  }

  def runTest(self):
    self.goofy.RestartTests(
        root=self.goofy.test_list.LookupPath('b'))
    self.CheckOneTest('test:b', 'b_B', TestState.FAILED,
                      'Required tests [test:a] have not been run yet',
                      does_not_start=True)

    self.goofy.RestartTests()
    self.CheckOneTest('test:a', 'a_A', TestState.PASSED, '')
    self.CheckOneTest('test:b', 'b_B', TestState.PASSED, '')


class StopOnFailureTest(GoofyUITest):
  """A unittest that checks if the goofy will stop after a test fails."""
  test_list = {
      'options': {
          'auto_run_on_start': True,
          'stop_on_failure': True
      },
      'tests': ABC_TEST_LIST
  }

  def runTest(self):
    MockPytest('a_A', TestState.PASSED, '')
    MockPytest('b_B', TestState.FAILED, 'Oops!')
    self.mocker.ReplayAll()
    # Make sure events are all processed.
    for _ in range(3):
      self.assertTrue(self.goofy.RunOnce())
      self.goofy.Wait()

    state_instance = state.GetInstance()
    self.assertEqual(
        [TestState.PASSED, TestState.FAILED, TestState.UNTESTED],
        [state_instance.GetTestState(x).status
         for x in ['test:a', 'test:b', 'test:c']])
    self._Wait()


class ParallelTest(GoofyUITest):
  """A test for parallel tests, goofy should run them in parallel."""

  test_list = {
      'tests': [
          {
              'id': 'parallel',
              'parallel': True,
              'subtests': [
                  {'id': 'a', 'pytest_name': 'a_A'},
                  {'id': 'b', 'pytest_name': 'b_B'},
                  {'id': 'c', 'pytest_name': 'c_C'},
              ]
          }
      ]
  }

  def runTest(self):
    MockPytest('a_A', TestState.PASSED, '')
    MockPytest('b_B', TestState.PASSED, '')
    MockPytest('c_C', TestState.PASSED, '')
    self.mocker.ReplayAll()

    self.goofy.RunOnce()
    self.assertEqual(
        {'a', 'b', 'c'},
        {invoc.test.id for invoc in itervalues(self.goofy.invocations)})
    self.goofy.Wait()

    self.mocker.VerifyAll()
    self.mocker.ResetAll()


class WaivedTestTest(GoofyUITest):
  """A test to verify that a waived test does not block test list execution."""
  test_list = {
      'options': {
          'auto_run_on_start': True,
          'stop_on_failure': True,
          'phase': 'PROTO',
          'waived_tests': {
              'PROTO': ['waived', 'G']
          },
      },
      'tests': [
          {'id': 'waived', 'pytest_name': 'waived_test'},
          {'id': 'normal', 'pytest_name': 'normal_test'},
          {
              'id': 'G',
              'subtests': [
                  {'id': 'waived', 'pytest_name': 'waived_test'},
              ]
          }
      ]
  }

  def BeforeInitGoofy(self):
    super(WaivedTestTest, self).BeforeInitGoofy()
    # 'G.waived' is already FAILED previously.
    self.state.UpdateTestState(path='test:G.waived', status=TestState.FAILED)

  def runTest(self):
    MockPytest('waived_test', TestState.FAILED, 'Failed')
    MockPytest('normal_test', TestState.PASSED, '')
    self.mocker.ReplayAll()

    # After Goofy init, 'G.waived' should be set to 'FAILED_AND_WAIVED'.
    self.assertEqual(self.state.GetTestState(path='test:G.waived').status,
                     TestState.FAILED_AND_WAIVED)

    for unused_i in range(4):
      self.assertTrue(self.goofy.RunOnce())
      self.goofy.Wait()

    self.assertEqual(
        [TestState.FAILED_AND_WAIVED, TestState.PASSED,
         TestState.FAILED_AND_WAIVED, TestState.FAILED_AND_WAIVED],
        [self.state.GetTestState(x).status
         for x in ['test:waived', 'test:normal', 'test:G', 'test:G.waived']])
    self._Wait()


class SkippedTestTest(GoofyUITest):
  """A test to verify that a waived test does not block test list execution."""

  test_list = {
      'constants': {'has_a2': True},
      'options': {
          'auto_run_on_start': True,
          'stop_on_failure': True,
          'phase': 'PROTO',
          'skipped_tests': {
              'PROTO': ['skipped'],
              'not device.has_a': ['*.A'],
              'constants.has_a2': ['*.A_2']
          }
      },
      'tests': [
          {'id': 'skipped', 'pytest_name': 'normal_test'},
          {'id': 'G',
           'subtests': [
               # This is skipped because device.has_a is not set
               {'id': 'A', 'pytest_name': 'normal_test'},
               # This is skipped because constants.has_a2 is True
               {'id': 'A', 'pytest_name': 'normal_test'},
               # This will be A_3, and it should not be skipped
               {'id': 'A', 'pytest_name': 'normal_test'},
           ]},
          {'id': 'normal', 'pytest_name': 'normal_test'},
      ],
  }

  def runTest(self):
    MockPytest('normal_test', TestState.PASSED, '')
    MockPytest('normal_test', TestState.PASSED, '')
    self.mocker.ReplayAll()

    for _ in range(4):
      self.assertTrue(self.goofy.RunOnce())
      self.goofy.Wait()

    state_instance = state.GetInstance()
    self.assertEqual(
        [TestState.SKIPPED, TestState.SKIPPED, TestState.SKIPPED,
         TestState.PASSED, TestState.PASSED],
        [state_instance.GetTestState(x).status
         for x in ['test:skipped', 'test:G.A', 'test:G.A_2', 'test:G.A_3',
                   'test:normal']])
    self._Wait()


class EndlessLoopTest(GoofyUITest):
  """A test to verify that a waived test does not block test list execution."""

  test_list = {
      'options': {'auto_run_on_start': True},
      'tests': [
          {'id': 'G',
           'iterations': -1,
           'retries': -1,
           'subtests': [
               {'id': 'A', 'pytest_name': 'normal_test'}
           ]}
      ]
  }

  def runTest(self):
    for unused_i in xrange(4):
      MockPytest('normal_test', TestState.PASSED, '')
    for unused_i in xrange(4):
      MockPytest('normal_test', TestState.FAILED, '')
    self.mocker.ReplayAll()

    state_instance = state.GetInstance()

    for i in range(8):
      self.assertTrue(self.goofy.RunOnce())
      self.goofy.Wait()
      self.assertEqual(
          state_instance.GetTestState(path='test:G').iterations_left,
          float('inf'))
      self.assertEqual(
          state_instance.GetTestState(path='test:G').retries_left,
          float('inf'))
      self.assertEqual(state_instance.GetTestState(path='test:G.A').count,
                       i + 1)
      self.assertEqual(state_instance.GetTestState(path='test:G.A').status,
                       TestState.PASSED if i < 4 else TestState.FAILED)
    self._Wait()


class NoHostTest(GoofyUITest):
  """A test to verify that tests marked 'no_host' run without host UI."""

  test_list = {
      'tests': [
          {'id': 'a', 'pytest_name': 'exec_python', 'no_host': True,
           'args': {'script': 'assert "Tomato" == "Tomato"'}},
          {'id': 'b', 'pytest_name': 'exec_python', 'no_host': False,
           'args': {'script': 'assert "Tomato" == "Tomato"'}},
      ]
  }

  mock_spawn_pytest = False

  def runTest(self):
    self.mocker.StubOutWithMock(self.goofy, 'InitUI')

    # No UI for test 'a', should not call InitUI
    self.mocker.ReplayAll()
    self.goofy.RunOnce()
    self._Wait()
    self.assertEqual(
        TestState.PASSED,
        state.GetInstance().GetTestState(path='test:a').status)

    # Start the UI for test 'b'
    self.goofy.InitUI()
    self.mocker.ReplayAll()
    self.goofy.RunOnce()
    self._Wait()
    self.assertEqual(
        TestState.PASSED,
        state.GetInstance().GetTestState(path='test:b').status)


if __name__ == '__main__':
  log_utils.InitLogging()
  goofy.suppress_chroot_warning = True

  unittest.main()
