#!/usr/bin/env python3
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The main factory flow that runs the factory test and finalizes a device."""

import argparse
import logging
import os
import queue
import signal
import sys
import threading
import time
import traceback
import uuid
import xmlrpc.client

from cros.factory.device import device_utils
from cros.factory.goofy.goofy_rpc import GoofyRPC
from cros.factory.goofy import goofy_server
from cros.factory.goofy import hooks
from cros.factory.goofy.invocation import TestInvocation
from cros.factory.goofy.plugins import plugin_controller
from cros.factory.goofy import prespawner
from cros.factory.goofy import test_environment
from cros.factory.goofy.test_list_iterator import TestListIterator
from cros.factory.goofy import updater
from cros.factory.goofy.web_socket_manager import WebSocketManager
from cros.factory.test import device_data
from cros.factory.test.env import goofy_proxy
from cros.factory.test.env import paths
from cros.factory.test.event import Event
from cros.factory.test.event import EventServer
from cros.factory.test.event import ThreadingEventClient
from cros.factory.test import event_log
from cros.factory.test.event_log import EventLog
from cros.factory.test.event_log import GetBootSequence
from cros.factory.test.event_log_watcher import EventLogWatcher
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test.i18n import translation
from cros.factory.test.rules import phase
from cros.factory.test import server_proxy
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test.state import TestState
from cros.factory.test.test_lists import manager
from cros.factory.test.test_lists import test_object
from cros.factory.testlog import testlog
from cros.factory.utils import config_utils
from cros.factory.utils import debug_utils
from cros.factory.utils import file_utils
from cros.factory.utils import log_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils

from cros.factory.external import syslog


HWID_CFG_PATH = '/usr/local/share/chromeos-hwid/cfg'
CACHES_DIR = os.path.join(paths.DATA_STATE_DIR, 'caches')

# Value for tests_after_shutdown that forces auto-run (e.g., after
# a factory update, when the available set of tests might change).
FORCE_AUTO_RUN = 'force_auto_run'

# Key to load the test list iterator after shutdown test
TESTS_AFTER_SHUTDOWN = 'tests_after_shutdown'

# Key to store active test list id.
ACTIVE_TEST_LIST_ID = 'active_test_list_id'

Status = type_utils.Enum(['UNINITIALIZED', 'INITIALIZING', 'RUNNING',
                          'TERMINATING', 'TERMINATED'])

RUN_QUEUE_TIMEOUT_SECS = 10


class Goofy:
  """The main factory flow.

  Note that all methods in this class must be invoked from the main
  (event) thread.  Other threads, such as callbacks and TestInvocation
  methods, should instead post events on the run queue.

  TODO: Unit tests. (chrome-os-partner:7409)

  Properties:
    run_queue: A queue of callbacks to invoke from the main thread.
    exceptions: List of exceptions encountered in invocation threads.
    last_idle: The most recent time of invoking the idle queue handler, or none.
    uuid: A unique UUID for this invocation of Goofy.
    state_instance: An instance of FactoryState.
    state_server: The FactoryState XML/RPC server.
    state_server_thread: A thread running state_server.
    event_server: The EventServer socket server.
    event_server_thread: A thread running event_server.
    event_client: A client to the event server.
    plugin_controller: The PluginController object.
    invocations: A map from TestInvocation uuid to the corresponding
      TestInvocations objects representing active tests.
    args: Command-line args.
    test_list: The test list.
    test_lists: All new-style test lists.
    run_id: The identifier for latest test run.
    scheduled_run_tests: The list of tests scheduled for latest test run.
    event_handlers: Map of Event.Type to the method used to handle that
      event.  If the method has an 'event' argument, the event is passed
      to the handler.
    hooks: A Hooks object containing hooks for various Goofy actions.
    status: The current Goofy status (a member of the Status enum).
  """

  def __init__(self):
    self.run_queue = queue.Queue()
    self.exceptions = []
    self.last_idle = None

    self.uuid = str(uuid.uuid4())
    self.state_instance = None
    self.goofy_server = None
    self.goofy_server_thread = None
    self.goofy_rpc = None
    self.event_server = None
    self.event_server_thread = None
    self.event_client = None
    self.log_watcher = None
    self.event_log = None
    self.testlog = None
    self.plugin_controller = None
    self.pytest_prespawner = None
    self._ui_initialized = False
    self.invocations = {}
    self.chrome = None
    self.hooks = None

    self.args = None
    self.test_list = None
    self.test_lists = None
    self.run_id = None
    self.scheduled_run_tests = None
    self.env = None
    self.last_idle = None
    self.last_shutdown_time = None
    self.last_update_check = None
    self._suppress_periodic_update_messages = False
    self._suppress_event_log_error_messages = False
    self.exclusive_resources = set()
    self.status = Status.UNINITIALIZED
    self.ready_for_ui_connection = False
    self.is_restart_requested = False
    self.test_list_iterator = None

    self.test_list_manager = manager.Manager()

    # TODO(hungte) Support controlling remote DUT.
    self.dut = device_utils.CreateDUTInterface()

    def TestOrRoot(event, parent_or_group=True):
      """Returns the test affected by a particular event.

      Args:
        event: The event containing an optional 'path' attribute.
        parent_or_group: If True, returns the top-level parent for a test (the
          root node of the tests that need to be run together if the given test
          path is to be run).
      """
      try:
        path = event.path
      except AttributeError:
        path = None

      if path:
        test = self.test_list.LookupPath(path)
        if parent_or_group:
          test = test.GetTopLevelParentOrGroup()
        return test
      return self.test_list.ToFactoryTestList()

    self.event_handlers = {
        Event.Type.RESTART_TESTS:
            lambda event: self.RestartTests(root=TestOrRoot(event)),
        Event.Type.AUTO_RUN:
            lambda event: self._AutoRun(root=TestOrRoot(event)),
        Event.Type.RUN_TESTS_WITH_STATUS:
            lambda event: self._RunTestsWithStatus(
                event.status,
                root=TestOrRoot(event)),
        Event.Type.UPDATE_SYSTEM_INFO:
            lambda event: self._UpdateSystemInfo(),
        Event.Type.STOP:
            lambda event: self.Stop(root=TestOrRoot(event, False),
                                    fail=getattr(event, 'fail', False),
                                    reason=getattr(event, 'reason', None)),
        Event.Type.CLEAR_STATE:
            lambda event: self.ClearState(
                self.test_list.LookupPath(event.path)),
        Event.Type.SET_ITERATIONS_AND_RETRIES:
            lambda event: self.SetIterationsAndRetries(
                test=self.test_list.LookupPath(event.path),
                iterations=getattr(event, 'iterations', None),
                retries=getattr(event, 'retries', None)),
    }

    self.web_socket_manager = None

  def Destroy(self):
    """Performs any shutdown tasks."""
    # To avoid race condition when running shutdown test.
    for invoc in self.invocations.values():
      logging.info('Waiting for %s to complete...', invoc.test)
      invoc.thread.join(3)  # Timeout in 3 seconds.

    self.status = Status.TERMINATING
    if self.chrome:
      self.chrome.kill()
      self.chrome = None
    if self.web_socket_manager:
      logging.info('Stopping web sockets')
      self.web_socket_manager.close()
      self.web_socket_manager = None
    if self.goofy_server_thread:
      logging.info('Stopping goofy server')
      net_utils.ShutdownTCPServer(self.goofy_server)
      self.goofy_server_thread.join()
      self.goofy_server.server_close()
      self.goofy_server_thread = None
    if self.state_instance:
      self.state_instance.Close()
    if self.event_server_thread:
      logging.info('Stopping event server')
      net_utils.ShutdownTCPServer(self.event_server)
      self.event_server_thread.join()
      self.event_server.server_close()
      self.event_server_thread = None
    if self.log_watcher:
      if self.log_watcher.IsThreadStarted():
        self.log_watcher.StopWatchThread()
      self.log_watcher = None
    if self.pytest_prespawner:
      logging.info('Stopping pytest prespawner')
      self.pytest_prespawner.stop()
      self.pytest_prespawner = None
    if self.event_client:
      logging.info('Closing event client')
      self.event_client.close()
      self.event_client = None
    if self.event_log:
      self.event_log.Close()
      self.event_log = None
    if self.testlog:
      self.testlog.Close()
      self.testlog = None
    if self.plugin_controller:
      self.plugin_controller.StopAndDestroyAllPlugins()
      self.plugin_controller = None

    self._CheckExceptions()
    logging.info('Done destroying Goofy')
    self.status = Status.TERMINATED

  def _InitGoofyServer(self):
    self.goofy_server = goofy_server.GoofyServer(
        (goofy_proxy.DEFAULT_GOOFY_BIND, goofy_proxy.DEFAULT_GOOFY_PORT))
    self.goofy_server_thread = threading.Thread(
        target=self.goofy_server.serve_forever,
        name='GoofyServer')
    self.goofy_server_thread.daemon = True

  def _InitStaticFiles(self):
    static_path = os.path.join(paths.FACTORY_PYTHON_PACKAGE_DIR, 'goofy/static')
    # Setup static file path
    self.goofy_server.RegisterPath('/', static_path)

  def _InitStateInstance(self):
    # Before starting state server, remount stateful partitions with
    # no commit flag.  The default commit time (commit=600) makes corruption
    # too likely.
    sys_utils.ResetCommitTime()

    self.state_instance = state.FactoryState()
    self.last_shutdown_time = (
        self.state_instance.DataShelfGetValue('shutdown_time', optional=True))
    self.state_instance.DataShelfDeleteKeys('shutdown_time', optional=True)
    self.state_instance.DataShelfDeleteKeys('startup_error', optional=True)

  def _ResetStateInstance(self):
    PRESERVED_KEYS = ['startup_error']

    # Backup the required data.
    preserved_data = {
        key: self.state_instance.DataShelfGetValue(key, optional=True)
        for key in PRESERVED_KEYS}

    # Reset the state instance.
    self.state_instance.Close()
    state.ClearState()
    self.state_instance = state.FactoryState()

    # Write back the preserved data.
    for key, value in preserved_data.items():
      if value is not None:
        self.state_instance.DataShelfSetValue(key, value)

  def _InitGoofyRPC(self):
    self.goofy_server.AddRPCInstance(goofy_proxy.STATE_URL, self.state_instance)

    # Setup Goofy RPC.
    # TODO(shunhsingou): separate goofy_rpc and state server instead of
    # injecting goofy_rpc functions into state.
    self.goofy_rpc = GoofyRPC(self)
    self.goofy_rpc.RegisterMethods(self.state_instance)

  def _InitI18n(self):
    js_data = 'var goofy_i18n_data = %s;' % translation.GetAllI18nDataJS()
    self.goofy_server.RegisterData('/js/goofy-translations.js',
                                   'application/javascript', js_data)
    self.goofy_server.RegisterData('/css/i18n.css',
                                   'text/css', i18n_test_ui.GetStyleSheet())

  def _StartEventServer(self):
    self.event_server = EventServer()
    logging.info('Starting factory event server')
    self.event_server_thread = process_utils.StartDaemonThread(
        target=self.event_server.serve_forever,
        name='EventServer')

    # pylint 1.5.6 has a false negative on nested lambda, see
    # https://github.com/PyCQA/pylint/issues/760.
    # pylint: disable=undefined-variable
    self.event_client = ThreadingEventClient(
        callback=lambda event: self.RunEnqueue(lambda: self.HandleEvent(event)))
    # pylint: enable=undefined-variable

    self.web_socket_manager = WebSocketManager(self.uuid)
    self.goofy_server.AddHTTPGetHandler(
        '/event', self.web_socket_manager.handle_web_socket)

  def Shutdown(self, operation):
    """Starts shutdown procedure.

    Args:
      operation: The shutdown operation (reboot, full_reboot, or halt).
    """
    active_tests = []
    for test in self.test_list.Walk():
      if not test.IsLeaf():
        continue

      test_state = test.GetState()
      if test_state.status == TestState.ACTIVE:
        active_tests.append(test)

    if operation == 'force_halt':
      # force_halt is a special halt request that shuts DUT down without going
      # through shutdown.py.
      # The use case can be like: if operators need to temporarily shutdown all
      # DUTs (e.g. charging or leaving production line) but don't want to press
      # power button for 10s on each, they can now use 'DUT Shutdown' in CrOS
      # Factory Menu to perform force shutdown.
      if active_tests:
        message = ('Can not force halt while tests are running.  '
                   'Stop all the tests and try again.')
        session.console.error(message)
        return
      operation = 'halt'
    elif not (len(active_tests) == 1 and
              isinstance(active_tests[0], test_object.ShutdownStep)):
      logging.error(
          'Calling Goofy shutdown outside of the shutdown factory test')
      return

    logging.info('Start Goofy shutdown (%s)', operation)
    # Save pending test list in the state server
    self.state_instance.DataShelfSetValue(
        TESTS_AFTER_SHUTDOWN, self.test_list_iterator)
    # Save shutdown time
    self.state_instance.DataShelfSetValue('shutdown_time', time.time())

    with self.env.lock:
      self.event_log.Log('shutdown', operation=operation)
      shutdown_result = self.env.shutdown(operation)
    if shutdown_result:
      # That's all, folks!
      self.RunEnqueue(None)
    else:
      # Just pass (e.g., in the chroot).
      self.state_instance.DataShelfSetValue(TESTS_AFTER_SHUTDOWN, None)
      # Send event with no fields to indicate that there is no
      # longer a pending shutdown.
      self.event_client.post_event(Event(Event.Type.PENDING_SHUTDOWN))

  def _HandleShutdownComplete(self, test):
    """Handles the case where a shutdown was detected during a shutdown step.

    Args:
      test: The ShutdownStep.
    """
    test_state = test.UpdateState(increment_shutdown_count=1)
    logging.info('Detected shutdown (%d of %d)',
                 test_state.shutdown_count, test.iterations)

    tests_after_shutdown = self.state_instance.DataShelfGetValue(
        TESTS_AFTER_SHUTDOWN, optional=True)

    # Make this shutdown test the next test to run.  This is to continue on
    # post-shutdown verification in the shutdown step.
    if not tests_after_shutdown:
      goofy_error = 'TESTS_AFTER_SHUTDOWN is not set'
      self.state_instance.DataShelfSetValue(
          TESTS_AFTER_SHUTDOWN, TestListIterator(test))
    else:
      goofy_error = tests_after_shutdown.RestartLastTest()
      self.state_instance.DataShelfSetValue(
          TESTS_AFTER_SHUTDOWN, tests_after_shutdown)

    # Set 'post_shutdown' to inform shutdown test that a shutdown just occurred.
    self.state_instance.DataShelfSetValue(
        state.KEY_POST_SHUTDOWN % test.path,
        {'invocation': self.state_instance.GetTestState(test.path).invocation,
         'goofy_error': goofy_error})

  def _InitStates(self):
    """Initializes all states on startup."""
    for test in self.test_list.GetAllTests():
      # Make sure the state server knows about all the tests,
      # defaulting to an untested state.
      test.UpdateState(update_parent=False)
    for test in self.test_list.GetAllTests():
      test_state = test.GetState()
      self.SetIterationsAndRetries(test,
                                   test_state.iterations, test_state.retries)

    is_unexpected_shutdown = False

    # Any 'active' tests should be marked as failed now.
    for test in self.test_list.Walk():
      if not test.IsLeaf():
        # Don't bother with parents; they will be updated when their
        # children are updated.
        continue

      test_state = test.GetState()
      if test_state.status != TestState.ACTIVE:
        continue
      if isinstance(test, test_object.ShutdownStep):
        # Shutdown while the test was active - that's good.
        self._HandleShutdownComplete(test)
      elif test.allow_reboot:
        is_unexpected_shutdown = True
        test.UpdateState(status=TestState.UNTESTED)
        # For "allow_reboot" tests (such as "Start"), don't cancel
        # pending tests, since reboot is expected.
        session.console.info('Unexpected shutdown while test %s was running. '
                             'The test is marked as allow_reboot, continuing '
                             'on pending tests.',
                             test.path)
      else:
        def GetUnexpectedShutdownTestRun():
          """Returns a StationTestRun for test not collected properly"""
          station_test_run = testlog.StationTestRun()
          station_test_run['status'] = testlog.StationTestRun.STATUS.FAIL
          station_test_run['endTime'] = time.time()
          station_test_run.AddFailure(
              'GoofyErrorMsg', 'Unexpected shutdown while test was running')
          return station_test_run

        is_unexpected_shutdown = True
        error_msg = 'Unexpected shutdown while test was running'
        self.event_log.Log('end_test',
                           path=test.path,
                           status=TestState.FAILED,
                           invocation=test.GetState().invocation,
                           error_msg=error_msg)
        testlog.CollectExpiredSessions(paths.DATA_LOG_DIR,
                                       GetUnexpectedShutdownTestRun())
        test.UpdateState(
            status=TestState.FAILED,
            error_msg=error_msg)
        # Trigger the OnTestFailure callback.
        self.RunEnqueue(lambda: self._TestFail(test))

        session.console.info('Unexpected shutdown while test %s '
                             'running; cancelling any pending tests',
                             test.path)
        # cancel pending tests by replace the iterator with an empty one
        self.state_instance.DataShelfSetValue(
            TESTS_AFTER_SHUTDOWN,
            TestListIterator(None))

    if is_unexpected_shutdown:
      logging.warning("Unexpected shutdown.")
      self.hooks.OnUnexpectedReboot(self)

    if self.test_list.options.read_device_data_from_vpd_on_init:
      vpd_data = {}
      for section in [device_data.NAME_RO, device_data.NAME_RW]:
        try:
          vpd_data[section] = self.dut.vpd.boot.GetPartition(section).GetAll()
        except Exception:
          logging.warning('Failed to read %s_VPD, ignored...', section.upper())
      # using None for key_map will use default key_map
      device_data.UpdateDeviceDataFromVPD(None, vpd_data)

    # state_instance is initialized, we can mark skipped and waived tests now.
    self.test_list.SetSkippedAndWaivedTests()

  def HandleEvent(self, event):
    """Handles an event from the event server."""
    handler = self.event_handlers.get(event.type)
    if handler:
      handler(event)
    else:
      # We don't register handlers for all event types - just ignore
      # this event.
      logging.debug('Unbound event type %s', event.type)

  def _CheckCriticalFactoryNote(self):
    """Returns True if the last factory note is critical."""
    notes = self.state_instance.DataShelfGetValue('factory_note', optional=True)
    return notes and notes[-1]['level'] == 'CRITICAL'

  def ScheduleRestart(self):
    """Schedules a restart event when any invocation is completed."""
    self.is_restart_requested = True

  def _InvocationCompletion(self):
    """Callback when an invocation is completed."""
    if self.is_restart_requested:
      logging.info('Restart by scheduled event.')
      self.is_restart_requested = False
      self.RestartTests()
    else:
      self._RunNextTest()

  def _RunNextTest(self):
    """Runs the next eligible test.

    self.test_list_iterator (a TestListIterator object) will determine which
    test should be run.
    """
    self.ReapCompletedTests()

    if self.invocations:
      # there are tests still running, we cannot start new tests
      return

    if self._CheckCriticalFactoryNote():
      logging.info('has critical factory note, stop running')
      self.test_list_iterator.Stop()
      return

    while True:
      try:
        path = next(self.test_list_iterator)
        test = self.test_list.LookupPath(path)
      except StopIteration:
        logging.info('no next test, stop running')
        return

      # check if we have run all required tests
      untested = set()
      for requirement in test.require_run:
        for i in requirement.test.Walk():
          if i == test:
            # We've hit this test itself; stop checking
            break
          if ((i.GetState().status == TestState.UNTESTED) or
              (requirement.passed and
               i.GetState().status not in [TestState.SKIPPED,
                                           TestState.PASSED])):
            # Found an untested test; move on to the next
            # element in require_run.
            untested.add(i)
            break

      if untested:
        untested_paths = ', '.join(sorted([x.path for x in untested]))
        if self.state_instance.DataShelfGetValue('engineering_mode',
                                                 optional=True):

          # In engineering mode, we'll let it go.
          session.console.warn('In engineering mode; running '
                               '%s even though required tests '
                               '[%s] have not completed',
                               test.path, untested_paths)
        else:
          # Not in engineering mode; mark it failed.
          error_msg = ('Required tests [%s] have not been run yet'
                       % untested_paths)
          session.console.error('Not running %s: %s',
                                test.path, error_msg)
          test.UpdateState(status=TestState.FAILED,
                           error_msg=error_msg)
          continue

      # okay, let's run the test
      if (isinstance(test, test_object.ShutdownStep) and
          self.state_instance.DataShelfGetValue(
              state.KEY_POST_SHUTDOWN % test.path, optional=True)):
        # Invoking post shutdown method of shutdown test. We should retain the
        # iterations_left and retries_left of the original test state.
        test_state = self.state_instance.GetTestState(test.path)
        self._RunTest(test, test_state.iterations_left, test_state.retries_left)
      else:
        # Starts a new test run; reset iterations and retries.
        self._RunTest(test, test.iterations, test.retries)
      return  # to leave while

  def _RunTest(self, test, iterations_left=None, retries_left=None,
               set_layout=True):
    """Invokes the test.

    The argument `test` should be either a leaf test (no subtests) or a parallel
    test (all subtests should be run in parallel).
    """
    if (self.args.goofy_ui and not self._ui_initialized and
        not test.IsNoHost()):
      self.InitUI()

    if set_layout:
      self.event_client.post_event(
          Event(
              Event.Type.SET_TEST_UI_LAYOUT,
              layout_type=test.layout_type,
              layout_options=test.layout_options))

    if test.IsLeaf():
      invoc = TestInvocation(
          self, test, on_completion=self._InvocationCompletion,
          on_test_failure=lambda: self._TestFail(test))
      new_state = test.UpdateState(
          status=TestState.ACTIVE, increment_count=1, error_msg='',
          invocation=invoc.uuid, iterations_left=iterations_left,
          retries_left=retries_left)
      invoc.count = new_state.count
      self.invocations[invoc.uuid] = invoc
      # Send a INIT_TEST_UI event here, so the test UI are initialized in
      # order, and the tab order would be same as test list order when there
      # are parallel tests with UI.
      self.event_client.post_event(
          Event(
              Event.Type.INIT_TEST_UI,
              test=test.path,
              invocation=invoc.uuid))
      self._CheckPlugins()
      invoc.Start()
    elif test.parallel:
      for subtest in test.subtests:
        # Pass the service lists defined in parallel group down to each
        # subtest.
        # Subtests of a parallel group are not allowed to have their own
        # service lists, so it's fine to override the lists with parallel
        # group's.
        subtest.enable_services = test.enable_services
        subtest.disable_services = test.disable_services

        # TODO(stimim): what if the subtests *must* be run in parallel?
        # for example, stressapptest and countdown test.

        # Make sure we don't need to skip it:
        if not self.test_list_iterator.CheckSkip(subtest):
          self._RunTest(subtest, subtest.iterations, subtest.retries,
                        set_layout=False)
    else:
      # This should never happen, there must be something wrong.
      # However, we can't raise an exception, otherwise goofy will be closed
      logging.critical(
          'Goofy should not get a non-leaf test that is not parallel: %r',
          test)
      session.console.critical(
          'Goofy should not get a non-leaf test that is not parallel: %r',
          test)

  def Run(self):
    """Runs Goofy."""
    # Process events forever.
    while self.RunOnce(True):
      pass

  def RunEnqueue(self, val):
    """Enqueues an object on the event loop.

    Generally this is a function. It may also be None to indicate that the
    run queue should shut down.
    """
    self.run_queue.put(val)

  def RunOnce(self, block=False):
    """Runs all items pending in the event loop.

    Args:
      block: If true, block until at least one event is processed.

    Returns:
      True to keep going or False to shut down.
    """
    events = type_utils.DrainQueue(self.run_queue)
    while not events:
      # Nothing on the run queue.
      self._RunQueueIdle()
      if block:
        # Block for at least one event...
        try:
          events.append(self.run_queue.get(timeout=RUN_QUEUE_TIMEOUT_SECS))
        except queue.Empty:
          # Keep going (calling _RunQueueIdle() again at the top of
          # the loop)
          continue
        # ...and grab anything else that showed up at the same
        # time.
        events.extend(type_utils.DrainQueue(self.run_queue))
      else:
        break

    for event in events:
      if not event:
        # Shutdown request.
        self.run_queue.task_done()
        return False

      try:
        event()
      except Exception:
        logging.exception('Error in event loop')
        self._RecordExceptions(
            traceback.format_exception_only(*sys.exc_info()[:2]))
        # But keep going
      finally:
        self.run_queue.task_done()
    return True

  def _RunQueueIdle(self):
    """Invoked when the run queue has no events.

    This method must not raise exception.
    """
    now = time.time()
    if (self.last_idle and
        now < (self.last_idle + RUN_QUEUE_TIMEOUT_SECS - 1)):
      # Don't run more often than once every (RUN_QUEUE_TIMEOUT_SECS -
      # 1) seconds.
      return

    self.last_idle = now
    self._PerformPeriodicTasks()

  def _CheckExceptions(self):
    """Raises an error if any exceptions have occurred in
    invocation threads.
    """
    if self.exceptions:
      raise RuntimeError('Exception in invocation thread: %r' %
                         self.exceptions)

  def _RecordExceptions(self, msg):
    """Records an exception in an invocation thread.

    An exception with the given message will be rethrown when
    Goofy is destroyed.
    """
    self.exceptions.append(msg)

  @staticmethod
  def DrainNondaemonThreads():
    """Wait for all non-current non-daemon threads to exit.

    This is performed by the Python runtime in an atexit handler,
    but this implementation allows us to do more detailed logging, and
    to support control-C for abrupt shutdown.
    """
    cur_thread = threading.current_thread()
    all_threads_joined = False
    while not all_threads_joined:
      for thread in threading.enumerate():
        if not thread.daemon and thread.is_alive() and thread is not cur_thread:
          logging.info("Waiting for thread '%s'...", thread.name)
          thread.join()
          # We break rather than continue on because the thread list
          # may have changed while we waited
          break
      else:
        # No threads remain
        all_threads_joined = True
    return all_threads_joined

  @staticmethod
  def RunMainAndExit():
    """Instantiate the receiver, run its main function, and exit when done.

    This static method is the "entry point" for Goofy.
    It instantiates the receiver and invokes its main function, while
    handling exceptions. When main() finishes (normally or via an exception),
    it exits the process.
    """
    try:
      cls = Goofy
      goofy = cls()
    except Exception:
      logging.info('Failed to instantiate %s, shutting down.', cls.__name__)
      traceback.print_exc()
      os._exit(1)  # pylint: disable=protected-access
      sys.exit(1)

    try:
      goofy.Main()
    except SystemExit:  # pylint: disable=try-except-raise
      # Propagate SystemExit without logging.
      raise
    except KeyboardInterrupt:
      logging.info('Interrupted, shutting down...')
    except Exception:
      # Log the error before trying to shut down
      logging.exception('Error in main loop')
      raise
    finally:
      try:
        # We drain threads manually, rather than letting Python do it,
        # so that we can report to the user which threads are stuck
        goofy.Destroy()
        cls.DrainNondaemonThreads()
      except (KeyboardInterrupt, Exception):
        # We got a keyboard interrupt while attempting to shut down.
        # The user is waiting impatiently! This can happen if threads get stuck.
        # We need to exit via os._exit, not sys.exit, because sys.exit() will
        # run the main thread's atexit handler, which waits for all threads to
        # exit, which is likely how we got stuck in the first place. However, we
        # do want to capture all logs, so we shut down logging gracefully.
        logging.info('Graceful shutdown interrupted, shutting down abruptly')
        logging.shutdown()
        os._exit(1)  # pylint: disable=protected-access
      # Normal exit path
      sys.exit(0)

  def _CheckPlugins(self):
    """Check plugins to be paused or resumed."""
    exclusive_resources = set()
    for invoc in self.invocations.values():
      exclusive_resources = exclusive_resources.union(
          invoc.test.GetExclusiveResources())
    self.plugin_controller.PauseAndResumePluginByResource(exclusive_resources)

  def _CheckForUpdates(self):
    """Schedules an asynchronous check for updates if necessary."""
    if not self.test_list.options.update_period_secs:
      # Not enabled.
      return

    now = time.time()
    if self.last_update_check and (
        now - self.last_update_check <
        self.test_list.options.update_period_secs):
      # Not yet time for another check.
      return

    self.last_update_check = now

    def _HandleCheckForUpdate(reached_server, toolkit_version, needs_update):
      if reached_server:
        new_update_toolkit_version = toolkit_version if needs_update else None
        if self.dut.info.update_toolkit_version != new_update_toolkit_version:
          logging.info('Received new update TOOLKIT_VERSION: %s',
                       new_update_toolkit_version)
          self.dut.info.Overrides('update_toolkit_version',
                                  new_update_toolkit_version)
          self.RunEnqueue(self._UpdateSystemInfo)
      elif not self._suppress_periodic_update_messages:
        logging.warning('Suppress error messages for periodic update checking '
                        'after the first one.')
        self._suppress_periodic_update_messages = True

    updater.CheckForUpdateAsync(
        _HandleCheckForUpdate, None, self._suppress_periodic_update_messages)

  def CancelPendingTests(self):
    """Cancels any tests in the run queue."""
    self._RunTests(None)

  def _RestoreActiveRunState(self):
    """Restores active run id and the list of scheduled tests."""
    self.run_id = self.state_instance.DataShelfGetValue('run_id', optional=True)
    self.scheduled_run_tests = self.state_instance.DataShelfGetValue(
        'scheduled_run_tests', optional=True)

  def _SetActiveRunState(self):
    """Sets active run id and the list of scheduled tests."""
    self.run_id = str(uuid.uuid4())
    # try our best to predict which tests will be run.
    self.scheduled_run_tests = self.test_list_iterator.GetPendingTests()
    self.state_instance.DataShelfSetValue('run_id', self.run_id)
    self.state_instance.DataShelfSetValue('scheduled_run_tests',
                                          self.scheduled_run_tests)

  def _RunTests(self, subtree, status_filter=None):
    """Runs tests under subtree.

    Run tests under a given subtree.

    Args:
      subtree: root of subtree to run or None to run nothing.
      status_filter: List of available test states. Only run the tests which
        states are in the list. Set to None if all test states are available.
    """
    self.hooks.OnTestStart()
    self.test_list_iterator = TestListIterator(
        subtree, status_filter, self.test_list)
    if subtree is not None:
      self._SetActiveRunState()
    self._RunNextTest()

  def ReapCompletedTests(self):
    """Removes completed tests from the set of active tests."""
    test_completed = False
    # Since items are removed while iterating, make a copy using values()
    # instead of itervalues().
    for invoc in list(self.invocations.values()):
      test = invoc.test
      if invoc.IsCompleted():
        test_completed = True
        new_state = test.UpdateState(**invoc.update_state_on_completion)
        del self.invocations[invoc.uuid]

        # Stop on failure if flag is true and there is no retry chances.
        if (self.test_list.options.stop_on_failure and
            new_state.retries_left < 0 and
            new_state.status == TestState.FAILED):
          # Clean all the tests to cause goofy to stop.
          session.console.info('Stop on failure triggered. Empty the queue.')
          self.CancelPendingTests()

        if new_state.iterations_left and new_state.status == TestState.PASSED:
          # Play it again, Sam!
          self._RunTest(test)
        # new_state.retries_left is obtained after update.
        # For retries_left == 0, test can still be run for the last time.
        elif (new_state.retries_left >= 0 and
              new_state.status == TestState.FAILED):
          # Still have to retry, Sam!
          self._RunTest(test)

    if test_completed:
      self.log_watcher.KickWatchThread()

  def _KillActiveTests(self, abort, root=None, reason=None):
    """Kills and waits for all active tests.

    Args:
      abort: True to change state of killed tests to FAILED, False for
        UNTESTED.
      root: If set, only kills tests with root as an ancestor.
      reason: If set, the abort reason.
    """
    self.ReapCompletedTests()
    # Since items are removed while iterating, make a copy using values()
    # instead of itervalues().
    for invoc in list(self.invocations.values()):
      test = invoc.test
      if root and not test.HasAncestor(root):
        continue

      session.console.info('Killing active test %s...', test.path)
      invoc.AbortAndJoin(reason)
      session.console.info('Killed %s', test.path)
      test.UpdateState(**invoc.update_state_on_completion)
      del self.invocations[invoc.uuid]

      if not abort:
        test.UpdateState(status=TestState.UNTESTED)
    self.ReapCompletedTests()

  def Stop(self, root=None, fail=False, reason=None):
    self._KillActiveTests(fail, root, reason)

    self.test_list_iterator.Stop(root)
    self._RunNextTest()

  def ClearState(self, root=None):
    if root is None:
      root = self.test_list
    self.Stop(root, reason='Clearing test state')
    for f in root.Walk():
      f.UpdateState(status=TestState.UNTESTED if f.IsLeaf() else None,
                    iterations=f.default_iterations,
                    retries=f.default_retries)

  def SetIterationsAndRetries(self, test, iterations, retries):
    """Set iterations and retries in goofy, ui, and shelf.

    If both iterations and retries are None, then set both value to default.
    If any of the two is invalid, then the function does nothing but logs.
    """
    if iterations is None and retries is None:
      iterations = test.default_iterations
      retries = test.default_retries
    try:
      test.SetIterationsAndRetries(iterations, retries)
      test.UpdateState(iterations=iterations, retries=retries)
    except ValueError:
      logging.exception('Unable to set iterations and retries.')

  def _AbortActiveTests(self, reason=None):
    self._KillActiveTests(True, reason=reason)

  def Main(self):
    syslog.openlog('goofy')

    try:
      self.status = Status.INITIALIZING
      self.Init()
      self.event_log.Log('goofy_init',
                         success=True)
      testlog.Log(
          testlog.StationInit({
              'stationDeviceId': session.GetDeviceID(),
              'stationInstallationId': session.GetInstallationID(),
              'count': session.GetInitCount(),
              'success': True}))
    except Exception:
      try:
        if self.event_log:
          self.event_log.Log('goofy_init',
                             success=False,
                             trace=traceback.format_exc())
        if self.testlog:
          testlog.Log(
              testlog.StationInit({
                  'stationDeviceId': session.GetDeviceID(),
                  'stationInstallationId': session.GetInstallationID(),
                  'count': session.GetInitCount(),
                  'success': False,
                  'failureMessage': traceback.format_exc()}))
      except Exception:
        pass
      raise

    self.status = Status.RUNNING
    syslog.syslog('Goofy (factory test harness) starting')
    syslog.syslog('Boot sequence = %d' % GetBootSequence())
    syslog.syslog('Goofy init count = %d' % session.GetInitCount())
    self.Run()

  def _UpdateSystemInfo(self):
    """Updates system info."""
    logging.info('Received a notify to update system info.')
    self.dut.info.Invalidate()

    # Propagate this notify to goofy components
    try:
      status_monitor = plugin_controller.GetPluginRPCProxy(
          'status_monitor.status_monitor')
      status_monitor.UpdateDeviceInfo()
    except Exception:
      logging.debug('Failed to update status monitor plugin.')

  def SetForceAutoRun(self):
    self.state_instance.DataShelfSetValue(TESTS_AFTER_SHUTDOWN, FORCE_AUTO_RUN)

  def UpdateFactory(self, auto_run_on_restart=False, post_update_hook=None):
    """Commences updating factory software.

    Args:
      auto_run_on_restart: Auto-run when the machine comes back up.
      post_update_hook: Code to call after update but immediately before
        restart.

    Returns:
      Never if the update was successful (we just reboot).
      False if the update was unnecessary (no update available).
    """
    self._KillActiveTests(False, reason='Factory software update')
    self.CancelPendingTests()

    def PreUpdateHook():
      if auto_run_on_restart:
        self.SetForceAutoRun()
      self.state_instance.Close()

    if updater.TryUpdate(pre_update_hook=PreUpdateHook):
      if post_update_hook:
        post_update_hook()
      self.env.shutdown('reboot')

  def _HandleSignal(self, signum, unused_frame):
    names = [signame for signame in dir(signal) if signame.startswith('SIG') and
             getattr(signal, signame) == signum]
    signal_name = ', '.join(names) if names else 'UNKNOWN'
    logging.error('Received signal %s(%d)', signal_name, signum)
    self.RunEnqueue(None)
    raise KeyboardInterrupt

  def GetTestList(self, test_list_id):
    """Returns the test list with the given ID.

    Raises:
      TestListError: The test list ID is not valid.
    """
    try:
      return self.test_lists[test_list_id]
    except KeyError:
      raise type_utils.TestListError(
          '%r is not a valid test list ID (available IDs are %r)' % (
              test_list_id, sorted(self.test_lists.keys())))

  def _RecordStartError(self, error_message):
    """Appends the startup error message into the shared data."""
    KEY = 'startup_error'
    data = self.state_instance.DataShelfGetValue(KEY, optional=True)
    new_data = '%s\n\n%s' % (data, error_message) if data else error_message
    self.state_instance.DataShelfSetValue(KEY, new_data)

  def _InitTestLists(self):
    """Reads in all test lists and sets the active test list.

    Returns:
      True if the active test list could be set, False if failed.
    """
    try:
      startup_errors = []

      self.test_lists, failed_test_lists = (
          self.test_list_manager.BuildAllTestLists())

      logging.info('Loaded test lists: %r', sorted(self.test_lists.keys()))

      # Check for any syntax errors in test list files.
      if failed_test_lists:
        logging.info('Failed test list IDs: [%s]',
                     ' '.join(failed_test_lists.keys()))
        for test_list_id, reason in failed_test_lists.items():
          logging.error('Error in test list %s: %s', test_list_id, reason)
          startup_errors.append('Error in test list %s:\n%s'
                                % (test_list_id, reason))

      active_test_list = self.test_list_manager.GetActiveTestListId(self.dut)

      # Check for a non-existent test list ID.
      try:
        self.test_list = self.GetTestList(active_test_list)
        logging.info('Active test list: %s', self.test_list.test_list_id)
      except type_utils.TestListError as e:
        logging.exception('Invalid active test list: %s', active_test_list)
        startup_errors.append(str(e))

      # Show all startup errors.
      if startup_errors:
        self._RecordStartError('\n\n'.join(startup_errors))

    except Exception:
      logging.exception('Unable to initialize test lists')
      self._RecordStartError(
          'Unable to initialize test lists\n%s' % traceback.format_exc())

    success = bool(self.test_list)
    if not success:
      # Create an empty test list with default options so that the rest of
      # startup can proceed.
      # A message box will pop up in UI for the error details.
      self.test_list = manager.DummyTestList(self.test_list_manager)

    # After SKU ID is updated and DUT is reboot, test list might be switched
    # because model name is changed too. In this case, shared state should be
    # cleared; otherwise shared data like TESTS_AFTER_SHUTDOWN prevents tests
    # from running automatically.
    previous_id = self.state_instance.DataShelfGetValue(ACTIVE_TEST_LIST_ID,
                                                        optional=True)
    if previous_id != self.test_list.test_list_id:
      logging.info('Test list is changed from %s to %s.',
                   previous_id, self.test_list.test_list_id)
      if previous_id:
        self._ResetStateInstance()

      self.state_instance.DataShelfSetValue(ACTIVE_TEST_LIST_ID,
                                            self.test_list.test_list_id)

    self.test_list.state_instance = self.state_instance

    # Only return False if failed to load the active test list.
    return success

  def _InitHooks(self):
    """Initializes hooks.

    Must run after self.test_list ready.
    """
    module, cls = self.test_list.options.hooks_class.rsplit('.', 1)
    self.hooks = getattr(__import__(module, fromlist=[cls]), cls)()
    assert isinstance(self.hooks, hooks.Hooks), (
        'hooks should be of type Hooks but is %r' % type(self.hooks))
    self.hooks.test_list = self.test_list
    self.hooks.OnCreatedTestList()

  def InitUI(self):
    """Initialize UI."""
    logging.info('Waiting for a web socket connection')
    self.web_socket_manager.wait()
    self._ui_initialized = True

  @staticmethod
  def GetCommandLineArgsParser():
    """Returns a parser for Goofy command line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable debug logging')
    parser.add_argument('--restart', action='store_true',
                        help='Clear all test state')
    parser.add_argument('--no-goofy-ui', dest='goofy_ui',
                        action='store_false', default=True,
                        help='start without Goofy UI')
    return parser

  def _PrepareDUTLink(self):
    # TODO(akahuang): Move this part into a pytest.
    # Prepare DUT link after the plugins start running, because the link might
    # need the network connection.

    dut_options = self.test_list.options.dut_options
    if dut_options:
      logging.info('dut_options set by %s: %r', self.test_list.test_list_id,
                   self.test_list.options.dut_options)

    def PrepareLink():
      try:
        device_utils.PrepareDUTLink(**dut_options)
      except Exception:
        logging.exception('Unable to prepare DUT link.')

    process_utils.StartDaemonThread(target=PrepareLink)

  def Init(self, args=None, env=None):
    """Initializes Goofy.

    Args:
      args: A list of command-line arguments.  Uses sys.argv if args is None.
      env: An Environment instance to use (or None to use DUTEnvironment).
    """
    self.args = self.GetCommandLineArgsParser().parse_args(args)

    signal.signal(signal.SIGINT, self._HandleSignal)
    signal.signal(signal.SIGTERM, self._HandleSignal)
    # TODO(hungte) SIGTERM does not work properly without Telemetry and should
    # be fixed.

    # Make sure factory directories exist.
    for path in [
        paths.DATA_LOG_DIR, paths.DATA_STATE_DIR, paths.DATA_TESTS_DIR]:
      file_utils.TryMakeDirs(path)

    try:
      goofy_default_options = config_utils.LoadConfig(validate_schema=False)
      for key, value in goofy_default_options.items():
        if getattr(self.args, key, None) is None:
          logging.info('self.args.%s = %r', key, value)
          setattr(self.args, key, value)
    except Exception:
      logging.exception('failed to load goofy overriding options')

    event_log.IncrementBootSequence()
    session.IncrementInitCount()

    # Don't defer logging the initial event, so we can make sure
    # that device_id, reimage_id, etc. are all set up.
    self.event_log = EventLog('goofy', defer=False)
    self.testlog = testlog.Testlog(
        log_root=paths.DATA_LOG_DIR, uuid=self.uuid,
        stationDeviceId=session.GetDeviceID(),
        stationInstallationId=session.GetInstallationID())

    if env:
      self.env = env
    else:
      self.env = test_environment.DUTEnvironment()
    self.env.goofy = self

    if self.args.restart:
      state.ClearState()

    self._InitGoofyServer()
    # Both the i18n file and index.html should be registered to Goofy before we
    # start the Goofy server, to avoid race condition that Goofy would return
    # 404 not found before index.html is registered.
    self._InitI18n()
    self._InitStaticFiles()

    logging.info('Starting goofy server')
    self.goofy_server_thread.start()

    self._InitStateInstance()

    # _InitTestLists might reset the state_instance, all initializations which
    # rely on the state_instance need to be done after this step.
    success = self._InitTestLists()

    self._InitGoofyRPC()

    self._InitHooks()
    self.testlog.init_hooks(self.test_list.options.testlog_hooks)

    if self.test_list.options.clear_state_on_start:
      # TODO(stimim): Perhaps we should check if we are running `shutdown` test?
      self.state_instance.ClearTestState()

    # If the phase is invalid, this will raise a ValueError.
    phase.SetPersistentPhase(self.test_list.options.phase)

    if not self.state_instance.DataShelfHasKey('ui_locale'):
      ui_locale = self.test_list.options.ui_locale
      self.state_instance.DataShelfSetValue('ui_locale', ui_locale)
    self.state_instance.DataShelfSetValue(
        'test_list_options',
        self.test_list.options.ToDict())
    self.state_instance.test_list = self.test_list

    self._InitStates()
    self._StartEventServer()

    # Load and run Goofy plugins.
    self.plugin_controller = plugin_controller.PluginController(
        self.test_list.options.plugin_config_name, self)
    self.plugin_controller.StartAllPlugins()

    if success:
      self._PrepareDUTLink()

    # Note that we create a log watcher even if
    # sync_event_log_period_secs isn't set (no background
    # syncing), since we may use it to flush event logs as well.
    self.log_watcher = EventLogWatcher(
        self.test_list.options.sync_event_log_period_secs,
        event_log_db_file=None,
        handle_event_logs_callback=self._HandleEventLogs)
    if self.test_list.options.sync_event_log_period_secs:
      self.log_watcher.StartWatchThread()

    self.event_client.post_event(
        Event(Event.Type.UPDATE_SYSTEM_INFO))

    os.environ['CROS_FACTORY'] = '1'
    os.environ['CROS_DISABLE_SITE_SYSINFO'] = '1'

    # Should not move earlier.
    self.hooks.OnStartup()

    # Only after this point the Goofy backend is ready for UI connection.
    self.ready_for_ui_connection = True

    def state_change_callback(test, test_state):
      self.event_client.post_event(
          Event(
              Event.Type.STATE_CHANGE,
              path=test.path,
              state=test_state.ToStruct()))
    self.test_list.state_change_callback = state_change_callback

    self.pytest_prespawner = prespawner.PytestPrespawner()
    self.pytest_prespawner.start()

    tests_after_shutdown = self.state_instance.DataShelfGetValue(
        TESTS_AFTER_SHUTDOWN, optional=True)
    force_auto_run = (tests_after_shutdown == FORCE_AUTO_RUN)

    if not force_auto_run and tests_after_shutdown is not None:
      logging.info('Resuming tests after shutdown: %r', tests_after_shutdown)
      self.test_list_iterator = tests_after_shutdown
      self.test_list_iterator.SetTestList(self.test_list)
      self.RunEnqueue(self._RunNextTest)
    elif force_auto_run or self.test_list.options.auto_run_on_start:
      status_filter = [TestState.UNTESTED]
      if self.test_list.options.retry_failed_on_start:
        status_filter.append(TestState.FAILED)
      self.RunEnqueue(lambda: self._RunTests(self.test_list, status_filter))
    self.state_instance.DataShelfSetValue(TESTS_AFTER_SHUTDOWN, None)
    self._RestoreActiveRunState()

    self.hooks.OnTestStart()

  def _PerformPeriodicTasks(self):
    """Perform any periodic work.

    This method must not raise exceptions.
    """
    self._CheckPlugins()
    self._CheckForUpdates()

  def _HandleEventLogs(self, chunks, periodic=False):
    """Callback for event watcher.

    Attempts to upload the event logs to the factory server.

    Args:
      chunks: A list of Chunk objects.
      periodic: This event log handling is periodic. Error messages
                will only be shown for the first time.
    """
    first_exception = None
    exception_count = 0

    for chunk in chunks:
      try:
        description = 'event logs (%s)' % str(chunk)
        start_time = time.time()
        proxy = server_proxy.GetServerProxy()
        proxy.UploadEvent(
            chunk.log_name + '.' + event_log.GetReimageId(),
            xmlrpc.client.Binary(chunk.chunk.encode('utf-8')))
        logging.info(
            'Successfully synced %s in %.03f s',
            description, time.time() - start_time)
      except Exception:
        first_exception = (first_exception or
                           (chunk.log_name + ': ' +
                            debug_utils.FormatExceptionOnly()))
        exception_count += 1

    if exception_count:
      if exception_count == 1:
        msg = 'Log upload failed: %s' % first_exception
      else:
        msg = '%d log upload failed; first is: %s' % (
            exception_count, first_exception)
      # For periodic event log syncing, only show the first error messages.
      if periodic:
        if not self._suppress_event_log_error_messages:
          self._suppress_event_log_error_messages = True
          logging.warning('Suppress periodic factory server error messages for '
                          'event log syncing after the first one.')
          raise Exception(msg)
      # For event log syncing by request, show the error messages.
      else:
        raise Exception(msg)

  def _RunTestsWithStatus(self, statuses_to_run, root=None):
    """Runs all top-level tests with a particular status.

    All active tests, plus any tests to re-run, are reset.

    Args:
      statuses_to_run: The particular status that caller wants to run.
      starting_at: If provided, only auto-runs tests beginning with
        this test.
      root: The root of tests to run. If not provided, it will be
        the root of all tests.
    """
    root = root or self.test_list
    self._AbortActiveTests('Operator requested run/re-run of certain tests')
    self._RunTests(root, status_filter=statuses_to_run)

  def RestartTests(self, root=None):
    """Restarts all tests."""
    root = root or self.test_list

    self._AbortActiveTests('Operator requested restart of certain tests')
    for test in root.Walk():
      test.UpdateState(status=TestState.UNTESTED)
    self._RunTests(root)

  def _AutoRun(self, root=None):
    """"Auto-runs" tests that have not been run yet.

    Args:
      root: If provided, the root of tests to run. If not provided, the root
        will be test_list (root of all tests).
    """
    root = root or self.test_list
    self._RunTestsWithStatus([TestState.UNTESTED, TestState.ACTIVE], root=root)

  def Wait(self):
    """Waits for all pending invocations.

    Useful for testing.
    """
    while self.invocations:
      for invoc in self.invocations.values():
        logging.info('Waiting for %s to complete...', invoc.test)
        invoc.thread.join()
      self.ReapCompletedTests()

  def _TestFail(self, test):
    self.hooks.OnTestFailure(test)


def main():
  # Logging should be solved first.
  args = Goofy.GetCommandLineArgsParser().parse_args()
  log_utils.InitLogging(verbose=args.verbose)

  Goofy.RunMainAndExit()


if __name__ == '__main__':
  main()
