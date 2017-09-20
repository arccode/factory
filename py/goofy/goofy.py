#!/usr/bin/python -u
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The main factory flow that runs the factory test and finalizes a device."""

from __future__ import print_function

import logging
from optparse import OptionParser
import os
import signal
import sys
import threading
import time
import traceback
import uuid
from xmlrpclib import Binary

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.goofy.goofy_base import GoofyBase
from cros.factory.goofy.goofy_rpc import GoofyRPC
from cros.factory.goofy import goofy_server
from cros.factory.goofy.invocation import TestInvocation
from cros.factory.goofy.plugins import plugin_controller
from cros.factory.goofy import prespawner
from cros.factory.goofy import test_environment
from cros.factory.goofy.test_list_iterator import TestListIterator
from cros.factory.goofy import updater
from cros.factory.goofy.web_socket_manager import WebSocketManager
from cros.factory.test import device_data
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.e2e_test.common import AutomationModePrompt
from cros.factory.test.e2e_test.common import ParseAutomationMode
from cros.factory.test.env import goofy_proxy
from cros.factory.test.env import paths
from cros.factory.test.event import Event
from cros.factory.test.event import EventClient
from cros.factory.test.event import EventServer
from cros.factory.test import event_log
from cros.factory.test.event_log import EventLog
from cros.factory.test.event_log import GetBootSequence
from cros.factory.test.event_log_watcher import EventLogWatcher
from cros.factory.test import factory
from cros.factory.test.factory import TestState
from cros.factory.test.i18n import html_translator
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test.i18n import translation
from cros.factory.test.rules import phase
from cros.factory.test import server_proxy
from cros.factory.test import state
from cros.factory.test.test_lists import manager
from cros.factory.test.test_lists import test_lists
from cros.factory.test import testlog_goofy
from cros.factory.testlog import testlog
from cros.factory.tools.key_filter import KeyFilter
from cros.factory.utils import config_utils
from cros.factory.utils import debug_utils
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
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

Status = type_utils.Enum(['UNINITIALIZED', 'INITIALIZING', 'RUNNING',
                          'TERMINATING', 'TERMINATED'])

class Goofy(GoofyBase):
  """The main factory flow.

  Note that all methods in this class must be invoked from the main
  (event) thread.  Other threads, such as callbacks and TestInvocation
  methods, should instead post events on the run queue.

  TODO: Unit tests. (chrome-os-partner:7409)

  Properties:
    uuid: A unique UUID for this invocation of Goofy.
    state_instance: An instance of FactoryState.
    state_server: The FactoryState XML/RPC server.
    state_server_thread: A thread running state_server.
    event_server: The EventServer socket server.
    event_server_thread: A thread running event_server.
    event_client: A client to the event server.
    plugin_controller: The PluginController object.
    invocations: A map from FactoryTest objects to the corresponding
      TestInvocations objects representing active tests.
    options: Command-line options.
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
    super(Goofy, self).__init__()
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

    self.options = None
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
    self.key_filter = None
    self.status = Status.UNINITIALIZED
    self.ready_for_ui_connection = False
    self.is_restart_requested = False
    self.test_list_iterator = None

    self.test_list_manager = manager.Manager()

    self._default_test_ui_html = None

    # TODO(hungte) Support controlling remote DUT.
    self.dut = device_utils.CreateDUTInterface()

    def test_or_root(event, parent_or_group=True):
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
      else:
        return self.test_list.ToFactoryTestList()

    self.event_handlers = {
        Event.Type.RESTART_TESTS:
            lambda event: self.restart_tests(root=test_or_root(event)),
        Event.Type.AUTO_RUN:
            lambda event: self.auto_run(root=test_or_root(event)),
        Event.Type.RUN_TESTS_WITH_STATUS:
            lambda event: self.run_tests_with_status(
                event.status,
                root=test_or_root(event)),
        Event.Type.UPDATE_SYSTEM_INFO:
            lambda event: self.update_system_info(),
        Event.Type.STOP:
            lambda event: self.stop(root=test_or_root(event, False),
                                    fail=getattr(event, 'fail', False),
                                    reason=getattr(event, 'reason', None)),
        Event.Type.CLEAR_STATE:
            lambda event: self.clear_state(
                self.test_list.LookupPath(event.path)),
        Event.Type.KEY_FILTER_MODE: self.handle_key_filter_mode,
    }

    self.web_socket_manager = None

  def destroy(self):
    """Performs any shutdown tasks. Overrides base class method."""
    # To avoid race condition when running shutdown test.
    for test, invoc in self.invocations.iteritems():
      logging.info('Waiting for %s to complete...', test)
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
      self.goofy_server.shutdown()
      self.goofy_server_thread.join()
      self.goofy_server.server_close()
      self.goofy_server_thread = None
    if self.state_instance:
      self.state_instance.close()
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
    if self.key_filter:
      self.key_filter.Stop()
    if self.plugin_controller:
      self.plugin_controller.StopAndDestroyAllPlugins()
      self.plugin_controller = None

    super(Goofy, self).destroy()
    logging.info('Done destroying Goofy')
    self.status = Status.TERMINATED

  def start_goofy_server(self):
    self.goofy_server = goofy_server.GoofyServer(
        (goofy_proxy.DEFAULT_GOOFY_BIND, goofy_proxy.DEFAULT_GOOFY_PORT))
    logging.info('Starting goofy server')
    self.goofy_server_thread = threading.Thread(
        target=self.goofy_server.serve_forever,
        name='GoofyServer')
    self.goofy_server_thread.start()

    static_path = os.path.join(paths.FACTORY_PYTHON_PACKAGE_DIR, 'goofy/static')
    # Setup static file path
    self.goofy_server.RegisterPath('/', static_path)
    # index.html needs to be preprocessed.
    index_path = os.path.join(static_path, 'index.html')
    index_html = html_translator.TranslateHTML(file_utils.ReadFile(index_path))
    self.goofy_server.RegisterData('/index.html', 'text/html', index_html)

    default_test_ui_path = os.path.join(static_path,
                                        'ui_templates/default_test_ui.html')
    self._default_test_ui_html = html_translator.TranslateHTML(
        file_utils.ReadFile(default_test_ui_path))

  def init_state_instance(self):
    # Before starting state server, remount stateful partitions with
    # no commit flag.  The default commit time (commit=600) makes corruption
    # too likely.
    sys_utils.ResetCommitTime()
    self.state_instance = state.FactoryState()
    self.goofy_server.AddRPCInstance(goofy_proxy.STATE_URL, self.state_instance)

    # Setup Goofy RPC.
    # TODO(shunhsingou): separate goofy_rpc and state server instead of
    # injecting goofy_rpc functions into state.
    self.goofy_rpc = GoofyRPC(self)
    self.goofy_rpc.RegisterMethods(self.state_instance)

  def init_i18n(self):
    js_data = 'var goofy_i18n_data = %s;' % translation.GetAllI18nDataJS()
    self.goofy_server.RegisterData('/js/goofy-translations.js',
                                   'application/javascript', js_data)
    self.goofy_server.RegisterData('/css/i18n.css',
                                   'text/css', i18n_test_ui.GetStyleSheet())

  def start_event_server(self):
    self.event_server = EventServer()
    logging.info('Starting factory event server')
    self.event_server_thread = threading.Thread(
        target=self.event_server.serve_forever,
        name='EventServer')
    self.event_server_thread.start()

    self.event_client = EventClient(
        callback=self.handle_event, event_loop=self.run_queue)

    self.web_socket_manager = WebSocketManager(self.uuid)
    self.goofy_server.AddHTTPGetHandler(
        '/event', self.web_socket_manager.handle_web_socket)

  def shutdown(self, operation):
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

    if not (len(active_tests) == 1 and
            isinstance(active_tests[0], factory.ShutdownStep)):
      logging.error(
          'Calling Goofy shutdown outside of the shutdown factory test')
      return

    logging.info('Start Goofy shutdown (%s)', operation)
    # Save pending test list in the state server
    self.state_instance.set_shared_data(
        TESTS_AFTER_SHUTDOWN, self.test_list_iterator)
    # Save shutdown time
    self.state_instance.set_shared_data('shutdown_time', time.time())

    with self.env.lock:
      self.event_log.Log('shutdown', operation=operation)
      shutdown_result = self.env.shutdown(operation)
    if shutdown_result:
      # That's all, folks!
      self.run_enqueue(None)
    else:
      # Just pass (e.g., in the chroot).
      self.state_instance.set_shared_data(TESTS_AFTER_SHUTDOWN, None)
      # Send event with no fields to indicate that there is no
      # longer a pending shutdown.
      self.event_client.post_event(Event(Event.Type.PENDING_SHUTDOWN))

  def handle_shutdown_complete(self, test):
    """Handles the case where a shutdown was detected during a shutdown step.

    Args:
      test: The ShutdownStep.
    """
    test_state = test.UpdateState(increment_shutdown_count=1)
    logging.info('Detected shutdown (%d of %d)',
                 test_state.shutdown_count, test.iterations)

    tests_after_shutdown = self.state_instance.get_shared_data(
        TESTS_AFTER_SHUTDOWN, optional=True)

    # Make this shutdown test the next test to run.  This is to continue on
    # post-shutdown verification in the shutdown step.
    if not tests_after_shutdown:
      goofy_error = 'TESTS_AFTER_SHTUDOWN is not set'
      self.state_instance.set_shared_data(
          TESTS_AFTER_SHUTDOWN, TestListIterator(test))
    else:
      goofy_error = tests_after_shutdown.RestartLastTest()
      self.state_instance.set_shared_data(
          TESTS_AFTER_SHUTDOWN, tests_after_shutdown)

    # Set 'post_shutdown' to inform shutdown test that a shutdown just occurred.
    self.state_instance.set_shared_data(
        state.KEY_POST_SHUTDOWN % test.path,
        {'invocation': self.state_instance.get_test_state(test.path).invocation,
         'goofy_error': goofy_error})

  def init_states(self):
    """Initializes all states on startup."""
    for test in self.test_list.GetAllTests():
      # Make sure the state server knows about all the tests,
      # defaulting to an untested state.
      test.UpdateState(update_parent=False)

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
      if isinstance(test, factory.ShutdownStep):
        # Shutdown while the test was active - that's good.
        self.handle_shutdown_complete(test)
      else:
        is_unexpected_shutdown = True
        error_msg = 'Unexpected shutdown while test was running'
        # TODO(itspeter): Add testlog to collect expired session infos.
        self.event_log.Log('end_test',
                           path=test.path,
                           status=TestState.FAILED,
                           invocation=test.GetState().invocation,
                           error_msg=error_msg)
        test.UpdateState(
            status=TestState.FAILED,
            error_msg=error_msg)
        # Trigger the OnTestFailure callback.
        self.run_queue.put(lambda: self.test_fail(test))

        if not test.never_fails:
          # For "never_fails" tests (such as "Start"), don't cancel
          # pending tests, since reboot is expected.
          factory.console.info('Unexpected shutdown while test %s '
                               'running; cancelling any pending tests',
                               test.path)
          # cancel pending tests by replace the iterator with an empty one
          self.state_instance.set_shared_data(
              TESTS_AFTER_SHUTDOWN,
              TestListIterator(None))

    if is_unexpected_shutdown:
      logging.warning("Unexpected shutdown.")
      self.hooks.OnUnexpectedReboot()

    if self.test_list.options.read_device_data_from_vpd_on_init:
      vpd_data = {}
      for section in [device_data.NAME_RO, device_data.NAME_RW]:
        try:
          vpd_data[section] = self.dut.vpd.boot.GetPartition(section).GetAll()
        except Exception:
          logging.exception('Failed to read %s_VPD, ignored...',
                            section.upper())
      # using None for key_map will use default key_map
      device_data.UpdateDeviceDataFromVPD(None, vpd_data)

    # state_instance is initialized, we can mark skipped and waived tests now.
    self.test_list.SetSkippedAndWaivedTests()

  def handle_event(self, event):
    """Handles an event from the event server."""
    handler = self.event_handlers.get(event.type)
    if handler:
      handler(event)
    else:
      # We don't register handlers for all event types - just ignore
      # this event.
      logging.debug('Unbound event type %s', event.type)

  def check_critical_factory_note(self):
    """Returns True if the last factory note is critical."""
    notes = self.state_instance.get_shared_data('factory_note', True)
    return notes and notes[-1]['level'] == 'CRITICAL'

  def schedule_restart(self):
    """Schedules a restart event when any invocation is completed."""
    self.is_restart_requested = True

  def invocation_completion(self):
    """Callback when an invocation is completed."""
    if self.is_restart_requested:
      logging.info('Restart by scheduled event.')
      self.is_restart_requested = False
      self.restart_tests()
    else:
      self.run_next_test()

  def run_next_test(self):
    """Runs the next eligible test.

    self.test_list_iterator (a TestListIterator object) will determine which
    test should be run.
    """
    self.reap_completed_tests()

    if self.invocations:
      # there are tests still running, we cannot start new tests
      return

    if self.check_critical_factory_note():
      logging.info('has critical factory note, stop running')
      self.test_list_iterator.Stop()
      return

    while True:
      try:
        path = self.test_list_iterator.next()
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
        if self.state_instance.get_shared_data('engineering_mode',
                                               optional=True):
          # In engineering mode, we'll let it go.
          factory.console.warn('In engineering mode; running '
                               '%s even though required tests '
                               '[%s] have not completed',
                               test.path, untested_paths)
        else:
          # Not in engineering mode; mark it failed.
          error_msg = ('Required tests [%s] have not been run yet'
                       % untested_paths)
          factory.console.error('Not running %s: %s',
                                test.path, error_msg)
          test.UpdateState(status=TestState.FAILED,
                           error_msg=error_msg)
          continue

      # okay, let's run the test
      if (isinstance(test, factory.ShutdownStep) and
          self.state_instance.get_shared_data(
              state.KEY_POST_SHUTDOWN % test.path, optional=True)):
        # Invoking post shutdown method of shutdown test. We should retain the
        # iterations_left and retries_left of the original test state.
        test_state = self.state_instance.get_test_state(test.path)
        self._run_test(test, test_state.iterations_left,
                       test_state.retries_left)
      else:
        # Starts a new test run; reset iterations and retries.
        self._run_test(test, test.iterations, test.retries)
      return  # to leave while

  def _run_test(self, test, iterations_left=None, retries_left=None):
    """Invokes the test.

    The argument `test` should be either a leaf test (no subtests) or a parallel
    test (all subtests should be run in parallel).
    """
    if not self._ui_initialized and not test.IsNoHost():
      self.init_ui()

    if test.IsLeaf():
      invoc = TestInvocation(
          self, test, on_completion=self.invocation_completion,
          on_test_failure=lambda: self.test_fail(test))
      new_state = test.UpdateState(
          status=TestState.ACTIVE, increment_count=1, error_msg='',
          invocation=invoc.uuid, iterations_left=iterations_left,
          retries_left=retries_left)
      invoc.count = new_state.count
      self.invocations[test] = invoc
      # Send a INIT_TEST_UI event here, so the test UI are initialized in
      # order, and the tab order would be same as test list order when there
      # are parallel tests with UI.
      self.event_client.post_event(
          Event(
              Event.Type.INIT_TEST_UI,
              html=self._default_test_ui_html,
              test=test.path,
              invocation=invoc.uuid))
      self.check_plugins()
      invoc.start()
    elif test.parallel:
      for subtest in test.subtests:
        # TODO(stimim): what if the subtests *must* be run in parallel?
        # for example, stressapptest and countdown test.

        # Make sure we don't need to skip it:
        if not self.test_list_iterator.CheckSkip(subtest):
          self._run_test(subtest, subtest.iterations, subtest.retries)
    else:
      # This should never happen, there must be something wrong.
      # However, we can't raise an exception, otherwise goofy will be closed
      logging.critical(
          'Goofy should not get a non-leaf test that is not parallel: %r',
          test)
      factory.console.critical(
          'Goofy should not get a non-leaf test that is not parallel: %r',
          test)

  def check_plugins(self):
    """Check plugins to be paused or resumed."""
    exclusive_resources = set()
    for test in self.invocations:
      exclusive_resources = exclusive_resources.union(
          test.GetExclusiveResources())
    self.plugin_controller.PauseAndResumePluginByResource(exclusive_resources)

  def check_for_updates(self):
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

    def handle_check_for_update(
        reached_server, toolkit_version, needs_update):
      if reached_server:
        new_update_toolkit_version = toolkit_version if needs_update else None
        if self.dut.info.update_toolkit_version != new_update_toolkit_version:
          logging.info('Received new update TOOLKIT_VERSION: %s',
                       new_update_toolkit_version)
          self.dut.info.Overrides('update_toolkit_version',
                                  new_update_toolkit_version)
          self.run_enqueue(self.update_system_info)
      elif not self._suppress_periodic_update_messages:
        logging.warning('Suppress error messages for periodic update checking '
                        'after the first one.')
        self._suppress_periodic_update_messages = True

    updater.CheckForUpdateAsync(
        handle_check_for_update, None, self._suppress_periodic_update_messages)

  def cancel_pending_tests(self):
    """Cancels any tests in the run queue."""
    self.run_tests(None)

  def restore_active_run_state(self):
    """Restores active run id and the list of scheduled tests."""
    self.run_id = self.state_instance.get_shared_data('run_id', optional=True)
    self.scheduled_run_tests = self.state_instance.get_shared_data(
        'scheduled_run_tests', optional=True)

  def set_active_run_state(self):
    """Sets active run id and the list of scheduled tests."""
    self.run_id = str(uuid.uuid4())
    # try our best to predict which tests will be run.
    self.scheduled_run_tests = self.test_list_iterator.GetPendingTests()
    self.state_instance.set_shared_data('run_id', self.run_id)
    self.state_instance.set_shared_data('scheduled_run_tests',
                                        self.scheduled_run_tests)

  def run_tests(self, subtree, status_filter=None):
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
      self.set_active_run_state()
    self.run_next_test()

  def reap_completed_tests(self):
    """Removes completed tests from the set of active tests.
    """
    test_completed = False
    for t, v in dict(self.invocations).iteritems():
      if v.is_completed():
        test_completed = True
        new_state = t.UpdateState(**v.update_state_on_completion)
        del self.invocations[t]

        # Stop on failure if flag is true and there is no retry chances.
        if (self.test_list.options.stop_on_failure and
            new_state.retries_left < 0 and
            new_state.status == TestState.FAILED):
          # Clean all the tests to cause goofy to stop.
          factory.console.info('Stop on failure triggered. Empty the queue.')
          self.cancel_pending_tests()

        if new_state.iterations_left and new_state.status == TestState.PASSED:
          # Play it again, Sam!
          self._run_test(t)
        # new_state.retries_left is obtained after update.
        # For retries_left == 0, test can still be run for the last time.
        elif (new_state.retries_left >= 0 and
              new_state.status == TestState.FAILED):
          # Still have to retry, Sam!
          self._run_test(t)

    if test_completed:
      self.log_watcher.KickWatchThread()

  def kill_active_tests(self, abort, root=None, reason=None):
    """Kills and waits for all active tests.

    Args:
      abort: True to change state of killed tests to FAILED, False for
        UNTESTED.
      root: If set, only kills tests with root as an ancestor.
      reason: If set, the abort reason.
    """
    self.reap_completed_tests()
    # since we remove objects while iterating, make a copy
    for test, invoc in dict(self.invocations).iteritems():
      if root and not test.HasAncestor(root):
        continue

      factory.console.info('Killing active test %s...', test.path)
      invoc.abort_and_join(reason)
      factory.console.info('Killed %s', test.path)
      test.UpdateState(**invoc.update_state_on_completion)
      del self.invocations[test]

      if not abort:
        test.UpdateState(status=TestState.UNTESTED)
    self.reap_completed_tests()

  def stop(self, root=None, fail=False, reason=None):
    self.kill_active_tests(fail, root, reason)

    self.test_list_iterator.Stop(root)
    self.run_next_test()

  def clear_state(self, root=None):
    if root is None:
      root = self.test_list
    self.stop(root, reason='Clearing test state')
    for f in root.Walk():
      if f.IsLeaf():
        f.UpdateState(status=TestState.UNTESTED)

  def abort_active_tests(self, reason=None):
    self.kill_active_tests(True, reason=reason)

  def main(self):
    syslog.openlog('goofy')

    try:
      self.status = Status.INITIALIZING
      self.init()
      self.event_log.Log('goofy_init',
                         success=True)
      testlog.Log(
          testlog.StationInit({
              'stationDeviceId': testlog_goofy.GetDeviceID(),
              'stationInstallationId': testlog_goofy.GetInstallationID(),
              'count': testlog_goofy.GetInitCount(),
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
                  'stationDeviceId': testlog_goofy.GetDeviceID(),
                  'stationInstallationId': testlog_goofy.GetInstallationID(),
                  'count': testlog_goofy.GetInitCount(),
                  'success': False,
                  'failureMessage': traceback.format_exc()}))
      except Exception:
        pass
      raise

    self.status = Status.RUNNING
    syslog.syslog('Goofy (factory test harness) starting')
    syslog.syslog('Boot sequence = %d' % GetBootSequence())
    syslog.syslog('Goofy init count = %d' % testlog_goofy.GetInitCount())
    self.run()

  def update_system_info(self):
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

  def update_factory(self, auto_run_on_restart=False, post_update_hook=None):
    """Commences updating factory software.

    Args:
      auto_run_on_restart: Auto-run when the machine comes back up.
      post_update_hook: Code to call after update but immediately before
        restart.

    Returns:
      Never if the update was successful (we just reboot).
      False if the update was unnecessary (no update available).
    """
    self.kill_active_tests(False, reason='Factory software update')
    self.cancel_pending_tests()

    def pre_update_hook():
      if auto_run_on_restart:
        self.state_instance.set_shared_data(TESTS_AFTER_SHUTDOWN,
                                            FORCE_AUTO_RUN)
      self.state_instance.close()

    if updater.TryUpdate(pre_update_hook=pre_update_hook):
      if post_update_hook:
        post_update_hook()
      self.env.shutdown('reboot')

  def handle_signal(self, signum, unused_frame):
    names = [signame for signame in dir(signal) if signame.startswith('SIG') and
             getattr(signal, signame) == signum]
    signal_name = ', '.join(names) if names else 'UNKNOWN'
    logging.error('Received signal %s(%d)', signal_name, signum)
    self.run_enqueue(None)
    raise KeyboardInterrupt()

  def GetTestList(self, test_list_id):
    """Returns the test list with the given ID.

    Raises:
      TestListError: The test list ID is not valid.
    """
    try:
      return self.test_lists[test_list_id]
    except KeyError:
      raise test_lists.TestListError(
          '%r is not a valid test list ID (available IDs are [%s])' % (
              test_list_id, ', '.join(sorted(self.test_lists.keys()))))

  def _RecordStartError(self, error_message):
    """Appends the startup error message into the shared data."""
    KEY = 'startup_error'
    data = self.state_instance.get_shared_data(KEY, optional=True)
    new_data = '%s\n\n%s' % (data, error_message) if data else error_message
    self.state_instance.set_shared_data(KEY, new_data)

  def InitTestLists(self):
    """Reads in all test lists and sets the active test list.

    Returns:
      True if the active test list could be set, False if failed.
    """
    startup_errors = []

    self.test_lists, failed_files = self.test_list_manager.BuildAllTestLists()

    logging.info('Loaded test lists: [%s]',
                 test_lists.DescribeTestLists(self.test_lists))

    # Check for any syntax errors in test list files.
    if failed_files:
      logging.info('Failed test list files: [%s]',
                   ' '.join(failed_files.keys()))
      for f, exc_info in failed_files.iteritems():
        logging.error('Error in test list file: %s', f,
                      exc_info=exc_info)

        # Limit the stack trace to the very last entry.
        exc_type, exc_value, exc_traceback = exc_info
        while exc_traceback and exc_traceback.tb_next:
          exc_traceback = exc_traceback.tb_next

        exc_string = ''.join(
            traceback.format_exception(
                exc_type, exc_value, exc_traceback)).rstrip()
        startup_errors.append('Error in test list file (%s):\n%s'
                              % (f, exc_string))

    if not self.options.test_list:
      self.options.test_list = test_lists.GetActiveTestListId()

    # Check for a non-existent test list ID.
    try:
      self.test_list = self.GetTestList(self.options.test_list)
      logging.info('Active test list: %s', self.test_list.test_list_id)
    except test_lists.TestListError as e:
      logging.exception('Invalid active test list: %s',
                        self.options.test_list)
      startup_errors.append(e.message)

    # We may have failed loading the active test list.
    if self.test_list:
      self.test_list.state_instance = self.state_instance

    # Show all startup errors.
    if startup_errors:
      self._RecordStartError('\n\n'.join(startup_errors))

    # Only return False if failed to load the active test list.
    return bool(self.test_list)

  def init_hooks(self):
    """Initializes hooks.

    Must run after self.test_list ready.
    """
    module, cls = self.test_list.options.hooks_class.rsplit('.', 1)
    self.hooks = getattr(__import__(module, fromlist=[cls]), cls)()
    assert isinstance(self.hooks, factory.Hooks), (
        'hooks should be of type Hooks but is %r' % type(self.hooks))
    self.hooks.test_list = self.test_list
    self.hooks.OnCreatedTestList()

  def init_ui(self):
    """Initialize UI."""
    self._ui_initialized = True
    if self.options.ui == 'chrome':
      logging.info('Waiting for a web socket connection')
      self.web_socket_manager.wait()

  @staticmethod
  def GetCommandLineArgsParser():
    """Returns a parser for Goofy command line arguments."""
    parser = OptionParser()
    parser.add_option('-v', '--verbose', dest='verbose',
                      action='store_true',
                      help='Enable debug logging')
    parser.add_option('--print_test_list', dest='print_test_list',
                      metavar='TEST_LIST_ID',
                      help='Print the content of TEST_LIST_ID and exit')
    parser.add_option('--restart', dest='restart',
                      action='store_true',
                      help='Clear all test state')
    parser.add_option('--ui', dest='ui', type='choice',
                      choices=['none', 'chrome'],
                      default='chrome',
                      help='UI to use')
    parser.add_option('--test_list', dest='test_list',
                      metavar='TEST_LIST_ID',
                      help='Use test list whose id is TEST_LIST_ID')
    parser.add_option('--automation-mode',
                      choices=[m.lower() for m in AutomationMode],
                      default='none', help='Factory test automation mode.')
    parser.add_option('--no-auto-run-on-start', dest='auto_run_on_start',
                      action='store_false', default=True,
                      help=('do not automatically run the test list on goofy '
                            'start; this is only valid when factory test '
                            'automation is enabled'))
    return parser

  def init(self, args=None, env=None):
    """Initializes Goofy.

    Args:
      args: A list of command-line arguments.  Uses sys.argv if
        args is None.
      env: An Environment instance to use (or None to choose
        FakeChrootEnvironment or DUTEnvironment as appropriate).
    """
    (self.options, self.args) = self.GetCommandLineArgsParser().parse_args(args)

    signal.signal(signal.SIGINT, self.handle_signal)
    signal.signal(signal.SIGTERM, self.handle_signal)
    # TODO(hungte) SIGTERM does not work properly without Telemetry and should
    # be fixed.

    # Make sure factory directories exist.
    for path in [
        paths.DATA_LOG_DIR, paths.DATA_STATE_DIR, paths.DATA_TESTS_DIR]:
      file_utils.TryMakeDirs(path)

    try:
      goofy_default_options = config_utils.LoadConfig(validate_schema=False)
      for key, value in goofy_default_options.iteritems():
        if getattr(self.options, key, None) is None:
          logging.info('self.options.%s = %r', key, value)
          setattr(self.options, key, value)
    except Exception:
      logging.exception('failed to load goofy overriding options')

    if self.options.print_test_list:
      all_test_lists, unused_errors = self.test_list_manager.BuildAllTestLists()
      test_list = (
          all_test_lists[self.options.print_test_list].ToFactoryTestList())
      print(test_list.__repr__(recursive=True))
      sys.exit(0)

    event_log.IncrementBootSequence()
    testlog_goofy.IncrementInitCount()

    # Don't defer logging the initial event, so we can make sure
    # that device_id, reimage_id, etc. are all set up.
    self.event_log = EventLog('goofy', defer=False)
    self.testlog = testlog.Testlog(
        log_root=paths.DATA_LOG_DIR, uuid=self.uuid,
        stationDeviceId=testlog_goofy.GetDeviceID(),
        stationInstallationId=testlog_goofy.GetInstallationID())

    if env:
      self.env = env
    elif sys_utils.InChroot():
      self.env = test_environment.FakeChrootEnvironment()
    elif self.options.ui == 'chrome':
      self.env = test_environment.DUTEnvironment()
    self.env.goofy = self

    if self.options.restart:
      state.clear_state()

    logging.info('Started')

    self.start_goofy_server()
    self.init_state_instance()
    self.init_i18n()
    self.last_shutdown_time = (
        self.state_instance.get_shared_data('shutdown_time', optional=True))
    self.state_instance.del_shared_data('shutdown_time', optional=True)
    self.state_instance.del_shared_data('startup_error', optional=True)

    self.options.automation_mode = ParseAutomationMode(
        self.options.automation_mode)
    self.state_instance.set_shared_data('automation_mode',
                                        self.options.automation_mode)
    self.state_instance.set_shared_data(
        'automation_mode_prompt',
        AutomationModePrompt[self.options.automation_mode])

    success = False
    exc_info = None
    try:
      success = self.InitTestLists()
    except Exception:
      exc_info = sys.exc_info()

    if not success:
      if exc_info:
        logging.exception('Unable to initialize test lists')
        self._RecordStartError(
            'Unable to initialize test lists\n%s' % traceback.format_exc())
      if self.options.ui == 'chrome':
        # Create an empty test list with default options so that the rest of
        # startup can proceed.
        self.test_list = manager.LegacyTestList(factory.FactoryTestList(
            [], self.state_instance, factory.Options()))
      else:
        # Bail with an error; no point in starting up.
        sys.exit('No valid test list; exiting.')

    self.init_hooks()

    if self.test_list.options.clear_state_on_start:
      self.state_instance.clear_test_state()

    # If the phase is invalid, this will raise a ValueError.
    phase.SetPersistentPhase(self.test_list.options.phase)

    if not self.state_instance.has_shared_data('ui_locale'):
      ui_locale = self.test_list.options.ui_locale
      self.state_instance.set_shared_data('ui_locale', ui_locale)
    self.state_instance.set_shared_data(
        'test_list_options',
        self.test_list.options.ToDict())
    self.state_instance.test_list = self.test_list

    self.init_states()
    self.start_event_server()

    # Load and run Goofy plugins.
    self.plugin_controller = plugin_controller.PluginController(
        self.test_list.options.plugin_config_name, self)
    self.plugin_controller.StartAllPlugins()

    # TODO(akahuang): Move this part into a pytest.
    # Prepare DUT link after the plugins start running, because the link might
    # need the network connection.
    if success:
      try:
        if self.test_list.options.dut_options:
          logging.info('dut_options set by %s: %r', self.test_list.test_list_id,
                       self.test_list.options.dut_options)
        device_utils.PrepareDUTLink(**self.test_list.options.dut_options)
      except Exception:
        logging.exception('Unable to prepare DUT link.')
        self._RecordStartError(
            'Unable to prepare DUT link.\n%s' % traceback.format_exc())

    # Note that we create a log watcher even if
    # sync_event_log_period_secs isn't set (no background
    # syncing), since we may use it to flush event logs as well.
    self.log_watcher = EventLogWatcher(
        self.test_list.options.sync_event_log_period_secs,
        event_log_db_file=None,
        handle_event_logs_callback=self.handle_event_logs)
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
          Event(Event.Type.STATE_CHANGE, path=test.path, state=test_state))
    self.test_list.state_change_callback = state_change_callback

    self.pytest_prespawner = prespawner.PytestPrespawner()
    self.pytest_prespawner.start()

    tests_after_shutdown = self.state_instance.get_shared_data(
        TESTS_AFTER_SHUTDOWN, optional=True)
    force_auto_run = (tests_after_shutdown == FORCE_AUTO_RUN)

    if not force_auto_run and tests_after_shutdown is not None:
      logging.info('Resuming tests after shutdown: %r', tests_after_shutdown)
      self.test_list_iterator = tests_after_shutdown
      self.test_list_iterator.SetTestList(self.test_list)
      self.run_enqueue(self.run_next_test)
    elif force_auto_run or self.test_list.options.auto_run_on_start:
      # If automation mode is enabled, allow suppress auto_run_on_start.
      if (self.options.automation_mode == 'NONE' or
          self.options.auto_run_on_start):
        status_filter = [TestState.UNTESTED]
        if self.test_list.options.retry_failed_on_start:
          status_filter.append(TestState.FAILED)
        self.run_enqueue(lambda: self.run_tests(self.test_list, status_filter))
    self.state_instance.set_shared_data(TESTS_AFTER_SHUTDOWN, None)
    self.restore_active_run_state()

    self.hooks.OnTestStart()

    self.may_disable_cros_shortcut_keys()

  def may_disable_cros_shortcut_keys(self):
    test_options = self.test_list.options
    if test_options.disable_cros_shortcut_keys:
      logging.info('Filter ChromeOS shortcut keys.')
      self.key_filter = KeyFilter(
          unmap_caps_lock=test_options.disable_caps_lock,
          caps_lock_keycode=test_options.caps_lock_keycode)
      self.key_filter.Start()

  def perform_periodic_tasks(self):
    """Override of base method to perform periodic work.

    This method must not raise exceptions.
    """
    super(Goofy, self).perform_periodic_tasks()

    self.check_plugins()
    self.check_for_updates()

  def handle_event_logs(self, chunks, periodic=False):
    """Callback for event watcher.

    Attempts to upload the event logs to the factory server.

    Args:
      chunks: A list of Chunk objects.
      periodic: This event log handling is periodic. Error messages
                will only be shown for the first time.
    """
    first_exception = None
    exception_count = 0
    # Suppress error messages for periodic event syncing except for the
    # first time. If event syncing is not periodic, always show the error
    # messages.
    quiet = self._suppress_event_log_error_messages if periodic else False

    for chunk in chunks:
      try:
        description = 'event logs (%s)' % str(chunk)
        start_time = time.time()
        proxy = server_proxy.GetServerProxy(quiet=quiet)
        proxy.UploadEvent(
            chunk.log_name + '.' + event_log.GetReimageId(),
            Binary(chunk.chunk))
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

  def run_tests_with_status(self, statuses_to_run, root=None):
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
    self.abort_active_tests('Operator requested run/re-run of certain tests')
    self.run_tests(root, status_filter=statuses_to_run)

  def restart_tests(self, root=None):
    """Restarts all tests."""
    root = root or self.test_list

    self.abort_active_tests('Operator requested restart of certain tests')
    for test in root.Walk():
      test.UpdateState(status=TestState.UNTESTED)
    self.run_tests(root)

  def auto_run(self, root=None):
    """"Auto-runs" tests that have not been run yet.

    Args:
      root: If provided, the root of tests to run. If not provided, the root
        will be test_list (root of all tests).
    """
    root = root or self.test_list
    self.run_tests_with_status([TestState.UNTESTED, TestState.ACTIVE],
                               root=root)

  def handle_key_filter_mode(self, event):
    if self.key_filter:
      if getattr(event, 'enabled'):
        self.key_filter.Start()
      else:
        self.key_filter.Stop()

  def wait(self):
    """Waits for all pending invocations.

    Useful for testing.
    """
    while self.invocations:
      for k, v in self.invocations.iteritems():
        logging.info('Waiting for %s to complete...', k)
        v.thread.join()
      self.reap_completed_tests()

  def test_fail(self, test):
    self.hooks.OnTestFailure(test)


def main():
  # Logging should be solved first.
  (options, unused_args) = Goofy.GetCommandLineArgsParser().parse_args()
  factory.init_logging('goofy', verbose=options.verbose)

  Goofy.run_main_and_exit()


if __name__ == '__main__':
  main()
