#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The main factory flow that runs the factory test and finalizes a device."""

from __future__ import print_function

import glob
import itertools
import logging
from optparse import OptionParser
import os
import shutil
import signal
import sys
import syslog
import threading
import time
import traceback
import uuid
from xmlrpclib import Binary

import factory_common  # pylint: disable=W0611
from cros.factory.device import device_utils
from cros.factory.goofy.goofy_base import GoofyBase
from cros.factory.goofy.goofy_rpc import GoofyRPC
from cros.factory.goofy.invocation import TestInvocation
from cros.factory.goofy.link_manager import PresenterLinkManager
from cros.factory.goofy.plugins import plugin_controller
from cros.factory.goofy import prespawner
from cros.factory.goofy.terminal_manager import TerminalManager
from cros.factory.goofy import test_environment
from cros.factory.goofy.test_list_iterator import TestListIterator
from cros.factory.goofy import updater
from cros.factory.goofy.web_socket_manager import WebSocketManager
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.e2e_test.common import AutomationModePrompt
from cros.factory.test.e2e_test.common import ParseAutomationMode
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
from cros.factory.test.rules import phase
from cros.factory.test import shopfloor
from cros.factory.test import state
from cros.factory.test.test_lists import test_lists
from cros.factory.test import testlog
from cros.factory.test import testlog_goofy
from cros.factory.tools.key_filter import KeyFilter
from cros.factory.utils import debug_utils
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import time_utils
from cros.factory.utils import type_utils


HWID_CFG_PATH = '/usr/local/share/chromeos-hwid/cfg'
CACHES_DIR = os.path.join(paths.GetStateRoot(), 'caches')

CLEANUP_LOGS_PAUSED = '/var/lib/cleanup_logs_paused'

# Value for tests_after_shutdown that forces auto-run (e.g., after
# a factory update, when the available set of tests might change).
FORCE_AUTO_RUN = 'force_auto_run'

# Key to load the test list iterator after shutdown test
TESTS_AFTER_SHUTDOWN = 'tests_after_shutdown'


MAX_CRASH_FILE_SIZE = 64 * 1024

Status = type_utils.Enum(['UNINITIALIZED', 'INITIALIZING', 'RUNNING',
                          'TERMINATING', 'TERMINATED'])


def get_hwid_cfg():
  """Returns the HWID config tag, or an empty string if none can be found."""
  if 'CROS_HWID' in os.environ:
    return os.environ['CROS_HWID']
  if os.path.exists(HWID_CFG_PATH):
    with open(HWID_CFG_PATH, 'r') as hwid_cfg_handle:
      return hwid_cfg_handle.read().strip()
  return ''


_inited_logging = False


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
    ui_process: The factory ui process object.
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
    link_manager: Instance of PresenterLinkManager for communicating
      with GoofyPresenter
  """

  def __init__(self):
    super(Goofy, self).__init__()
    self.uuid = str(uuid.uuid4())
    self.state_instance = None
    self.state_server = None
    self.state_server_thread = None
    self.goofy_rpc = None
    self.event_server = None
    self.event_server_thread = None
    self.event_client = None
    self.log_watcher = None
    self.event_log = None
    self.testlog = None
    self.autotest_prespawner = None
    self.plugin_controller = None
    self.pytest_prespawner = None
    self.ui_process = None
    self._ui_initialized = False
    self.dummy_shopfloor = None
    self.invocations = {}
    self.visible_test = None
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
    self.link_manager = None
    self.is_restart_requested = False
    self.test_list_iterator = None

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
        test = self.test_list.lookup_path(path)
        if parent_or_group:
          test = test.get_top_level_parent_or_group()
        return test
      else:
        return self.test_list

    self.event_handlers = {
        Event.Type.SWITCH_TEST: self.handle_switch_test,
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
        Event.Type.SET_VISIBLE_TEST:
            lambda event: self.set_visible_test(
                self.test_list.lookup_path(event.path)),
        Event.Type.CLEAR_STATE:
            lambda event: self.clear_state(
                self.test_list.lookup_path(event.path)),
        Event.Type.KEY_FILTER_MODE: self.handle_key_filter_mode,
    }

    self.web_socket_manager = None
    self.terminal_manager = None

  def destroy(self):
    """Performs any shutdown tasks. Overrides base class method."""
    self.status = Status.TERMINATING
    if self.chrome:
      self.chrome.kill()
      self.chrome = None
    if self.dummy_shopfloor:
      self.dummy_shopfloor.kill()
      self.dummy_shopfloor = None
    if self.ui_process:
      process_utils.KillProcessTree(self.ui_process, 'ui')
      self.ui_process = None
    if self.web_socket_manager:
      logging.info('Stopping web sockets')
      self.web_socket_manager.close()
      self.web_socket_manager = None
    if self.state_server_thread:
      logging.info('Stopping state server')
      self.state_server.shutdown()
      self.state_server_thread.join()
      self.state_server.server_close()
      self.state_server_thread = None
    if self.state_instance:
      self.state_instance.close()
    if self.event_server_thread:
      logging.info('Stopping event server')
      self.event_server.shutdown()  # pylint: disable=E1101
      self.event_server_thread.join()
      self.event_server.server_close()
      self.event_server_thread = None
    if self.log_watcher:
      if self.log_watcher.IsThreadStarted():
        self.log_watcher.StopWatchThread()
      self.log_watcher = None
    if self.autotest_prespawner:
      logging.info('Stopping autotest prespawner')
      self.autotest_prespawner.stop()
      self.autotest_prespawner = None
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
    if self.link_manager:
      self.link_manager.Stop()
      self.link_manager = None
    if self.plugin_controller:
      self.plugin_controller.StopAndDestroyAllPlugins()
      self.plugin_controller = None

    super(Goofy, self).destroy()
    logging.info('Done destroying Goofy')
    self.status = Status.TERMINATED

  def start_state_server(self):
    # Before starting state server, remount stateful partitions with
    # no commit flag.  The default commit time (commit=600) makes corruption
    # too likely.
    sys_utils.ResetCommitTime()

    self.state_instance, self.state_server = (
        state.create_server(bind_address='0.0.0.0'))
    self.goofy_rpc = GoofyRPC(self)
    self.goofy_rpc.RegisterMethods(self.state_instance)
    logging.info('Starting state server')
    self.state_server_thread = threading.Thread(
        target=self.state_server.serve_forever,
        name='StateServer')
    self.state_server_thread.start()

  def start_event_server(self):
    self.event_server = EventServer()
    logging.info('Starting factory event server')
    self.event_server_thread = threading.Thread(
        target=self.event_server.serve_forever,
        name='EventServer')  # pylint: disable=E1101
    self.event_server_thread.start()

    self.event_client = EventClient(
        callback=self.handle_event, event_loop=self.run_queue)

    self.web_socket_manager = WebSocketManager(self.uuid)
    self.state_server.add_handler('/event',
                                  self.web_socket_manager.handle_web_socket)

  def start_terminal_server(self):
    self.terminal_manager = TerminalManager()
    self.state_server.add_handler('/pty',
                                  self.terminal_manager.handle_web_socket)

  def start_ui(self):
    ui_proc_args = [
        os.path.join(paths.FACTORY_PACKAGE_PATH, 'test', 'ui.py'),
        self.options.test_list
    ]
    if self.options.verbose:
      ui_proc_args.append('-v')
    logging.info('Starting ui %s', ui_proc_args)
    self.ui_process = process_utils.Spawn(ui_proc_args)
    logging.info('Waiting for UI to come up...')
    self.event_client.wait(
        lambda event: event.type == Event.Type.UI_READY)
    logging.info('UI has started')

  def set_visible_test(self, test):
    if self.visible_test == test:
      return
    if test and not test.has_ui:
      return

    if test:
      test.update_state(visible=True)
    if self.visible_test:
      self.visible_test.update_state(visible=False)
    self.visible_test = test

  def log_startup_messages(self):
    """Logs the tail of var/log/messages and mosys and EC console logs."""
    # TODO(jsalz): This is mostly a copy-and-paste of code in init_states,
    # for factory-3004.B only.  Consolidate and merge back to ToT.
    if sys_utils.InChroot():
      return

    try:
      var_log_messages = sys_utils.GetVarLogMessagesBeforeReboot()
      logging.info(
          'Tail of /var/log/messages before last reboot:\n'
          '%s', ('\n'.join(
              '  ' + x for x in var_log_messages)))
    except:  # pylint: disable=W0702
      logging.exception('Unable to grok /var/log/messages')

    try:
      mosys_log = process_utils.Spawn(
          ['mosys', 'eventlog', 'list'],
          read_stdout=True, log_stderr_on_error=True).stdout_data
      logging.info('System eventlog from mosys:\n%s\n', mosys_log)
    except:  # pylint: disable=W0702
      logging.exception('Unable to read mosys eventlog')

    self.log_ec_console()
    self.log_ec_panic_info()

  @staticmethod
  def log_ec_console():
    """Logs EC console log into logging.info.

    It logs an error message in logging.exception if an exception is raised
    when getting EC console log.
    For unsupported device, it logs unsupport message in logging.info

    Returns:
      EC console log string.
    """
    try:
      ec_console_log = device_utils.CreateDUTInterface().ec.GetECConsoleLog()
      logging.info('EC console log after reboot:\n%s\n', ec_console_log)
      return ec_console_log
    except NotImplementedError:
      logging.info('EC console log not supported')
    except:  # pylint: disable=W0702
      logging.exception('Error retrieving EC console log')

  @staticmethod
  def log_ec_panic_info():
    """Logs EC panic info into logging.info.

    It logs an error message in logging.exception if an exception is raised
    when getting EC panic info.
    For unsupported device, it logs unsupport message in logging.info

    Returns:
      EC panic info string.
    """
    try:
      ec_panic_info = device_utils.CreateDUTInterface().ec.GetECPanicInfo()
      logging.info('EC panic info after reboot:\n%s\n', ec_panic_info)
      return ec_panic_info
    except NotImplementedError:
      logging.info('EC panic info is not supported')
    except:  # pylint: disable=W0702
      logging.exception('Error retrieving EC panic info')

  def shutdown(self, operation):
    """Starts shutdown procedure.

    Args:
      operation: The shutdown operation (reboot, full_reboot, or halt).
    """
    active_tests = []
    for test in self.test_list.walk():
      if not test.is_leaf():
        continue

      test_state = test.get_state()
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
    test_state = test.update_state(increment_shutdown_count=1)
    logging.info('Detected shutdown (%d of %d)',
                 test_state.shutdown_count, test.iterations)

    tests_after_shutdown = self.state_instance.get_shared_data(
        TESTS_AFTER_SHUTDOWN, optional=True)

    # Make this shutdown test the next test to run.  This is to continue on
    # post-shutdown verification in the shutdown step.
    if not tests_after_shutdown:
      self.state_instance.set_shared_data(
          TESTS_AFTER_SHUTDOWN, TestListIterator(test))
    else:
      # unset inited, so we will start from the reboot test.
      tests_after_shutdown.inited = False
      self.state_instance.set_shared_data(
          TESTS_AFTER_SHUTDOWN, tests_after_shutdown)

    # Set 'post_shutdown' to inform shutdown test that a shutdown just occurred.
    self.state_instance.set_shared_data(
        state.POST_SHUTDOWN_TAG % test.path,
        self.state_instance.get_test_state(test.path).invocation)

  def init_states(self):
    """Initializes all states on startup."""
    for test in self.test_list.get_all_tests():
      # Make sure the state server knows about all the tests,
      # defaulting to an untested state.
      test.update_state(update_parent=False, visible=False)

    var_log_messages = None
    mosys_log = None
    ec_console_log = None
    ec_panic_info = None

    # Any 'active' tests should be marked as failed now.
    for test in self.test_list.walk():
      if not test.is_leaf():
        # Don't bother with parents; they will be updated when their
        # children are updated.
        continue

      test_state = test.get_state()
      if test_state.status != TestState.ACTIVE:
        continue
      if isinstance(test, factory.ShutdownStep):
        # Shutdown while the test was active - that's good.
        self.handle_shutdown_complete(test)
      else:
        # Unexpected shutdown.  Grab /var/log/messages for context.
        if var_log_messages is None:
          try:
            var_log_messages = sys_utils.GetVarLogMessagesBeforeReboot()
            # Write it to the log, to make it easier to
            # correlate with /var/log/messages.
            logging.info(
                'Unexpected shutdown. '
                'Tail of /var/log/messages before last reboot:\n'
                '%s', ('\n'.join(
                    '  ' + x for x in var_log_messages)))
          except:  # pylint: disable=W0702
            logging.exception('Unable to grok /var/log/messages')
            var_log_messages = []

        if mosys_log is None and not sys_utils.InChroot():
          try:
            mosys_log = process_utils.Spawn(
                ['mosys', 'eventlog', 'list'],
                read_stdout=True, log_stderr_on_error=True).stdout_data
            # Write it to the log also.
            logging.info('System eventlog from mosys:\n%s\n', mosys_log)
          except:  # pylint: disable=W0702
            logging.exception('Unable to read mosys eventlog')

        if ec_console_log is None:
          ec_console_log = self.log_ec_console()

        if ec_panic_info is None:
          ec_panic_info = self.log_ec_panic_info()

        error_msg = 'Unexpected shutdown while test was running'
        # TODO(itspeter): Add testlog to collect expired session infos.
        self.event_log.Log('end_test',
                           path=test.path,
                           status=TestState.FAILED,
                           invocation=test.get_state().invocation,
                           error_msg=error_msg,
                           var_log_messages='\n'.join(var_log_messages),
                           mosys_log=mosys_log)
        test.update_state(
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
      self.test_list_iterator.stop()
      return

    while True:
      try:
        path = self.test_list_iterator.next()
        test = self.test_list.lookup_path(path)
      except StopIteration:
        logging.info('no next test, stop running')
        return

      # check if we have run all required tests
      untested = set()
      for requirement in test.require_run:
        for i in requirement.test.walk():
          if i == test:
            # We've hit this test itself; stop checking
            break
          if ((i.get_state().status == TestState.UNTESTED) or
              (requirement.passed and i.get_state().status !=
               TestState.PASSED)):
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
          test.update_state(status=TestState.FAILED,
                            error_msg=error_msg)
          continue

      # okay, let's run the test
      if (isinstance(test, factory.ShutdownStep) and
          self.state_instance.get_shared_data(
              state.POST_SHUTDOWN_TAG % test.path, optional=True)):
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
    if not self._ui_initialized and not test.is_no_host():
      self.init_ui()

    if test.is_leaf():
      invoc = TestInvocation(
          self, test, on_completion=self.invocation_completion,
          on_test_failure=lambda: self.test_fail(test))
      new_state = test.update_state(
          status=TestState.ACTIVE, increment_count=1, error_msg='',
          invocation=invoc.uuid, iterations_left=iterations_left,
          retries_left=retries_left,
          visible=(self.visible_test == test))
      invoc.count = new_state.count
      self.invocations[test] = invoc
      if self.visible_test is None and test.has_ui:
        self.set_visible_test(test)
      self.check_plugins()
      invoc.start()
    else:
      assert test.is_parallel()
      for subtest in test.subtests:
        # TODO(stimim): what if the subtests *must* be run in parallel?
        # for example, stressapptest and countdown test.

        # Make sure we don't need to skip it:
        if not self.test_list_iterator.check_skip(subtest):
          self._run_test(subtest, subtest.iterations, subtest.retries)

  def check_plugins(self):
    """Check plugins to be paused or resumed."""
    exclusive_resources = set()
    for test in self.invocations:
      exclusive_resources = exclusive_resources.union(
          test.get_exclusive_resources())
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

    def handle_check_for_update(reached_shopfloor, md5sum, needs_update):
      if reached_shopfloor:
        new_update_md5sum = md5sum if needs_update else None
        if self.dut.info.update_md5sum != new_update_md5sum:
          logging.info('Received new update MD5SUM: %s', new_update_md5sum)
          self.dut.info.Overrides('update_md5sum', new_update_md5sum)
          self.run_enqueue(self.update_system_info)
      else:
        if not self._suppress_periodic_update_messages:
          logging.warning('Suppress error messages for periodic update checking'
                          ' after the first one.')
          self._suppress_periodic_update_messages = True

    updater.CheckForUpdateAsync(
        handle_check_for_update,
        self.test_list.options.shopfloor_timeout_secs,
        self._suppress_periodic_update_messages)

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
    self.scheduled_run_tests = self.test_list_iterator.get_pending_tests()
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
    self.dut.hooks.OnTestStart()
    self.test_list_iterator = TestListIterator(
        subtree, status_filter, self.test_list)
    if subtree is not None:
      self.set_active_run_state()
    self.run_next_test()

  def reap_completed_tests(self):
    """Removes completed tests from the set of active tests.

    Also updates the visible test if it was reaped.
    """
    test_completed = False
    for t, v in dict(self.invocations).iteritems():
      if v.is_completed():
        test_completed = True
        new_state = t.update_state(**v.update_state_on_completion)
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

    if (self.visible_test is None or
        self.visible_test not in self.invocations):
      self.set_visible_test(None)
      # Make the first running test, if any, the visible test
      for t in self.test_list.walk():
        if t in self.invocations:
          self.set_visible_test(t)
          break

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
      if root and not test.has_ancestor(root):
        continue

      factory.console.info('Killing active test %s...', test.path)
      invoc.abort_and_join(reason)
      factory.console.info('Killed %s', test.path)
      test.update_state(**invoc.update_state_on_completion)
      del self.invocations[test]

      if not abort:
        test.update_state(status=TestState.UNTESTED)
    self.reap_completed_tests()

  def stop(self, root=None, fail=False, reason=None):
    self.kill_active_tests(fail, root, reason)

    if not root:
      self.test_list_iterator.stop()
    else:
      # only skip tests under `root`
      self.test_list_iterator = itertools.dropwhile(
          lambda path: self.test_list.lookup_path(path).has_ancestor(root),
          self.test_list_iterator)
    self.run_next_test()

  def clear_state(self, root=None):
    if root is None:
      root = self.test_list
    self.stop(root, reason='Clearing test state')
    for f in root.walk():
      if f.is_leaf():
        f.update_state(status=TestState.UNTESTED)

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
    except:
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
      except:  # pylint: disable=W0702
        pass
      raise

    self.status = Status.RUNNING
    syslog.syslog('Goofy (factory test harness) starting')
    syslog.syslog('Boot sequence = %d' % GetBootSequence())
    syslog.syslog('Goofy init count = %d' % testlog_goofy.GetInitCount())
    self.run()

  def update_system_info(self):
    """Updates system info."""
    info = self.dut.info.GetAll()
    self.state_instance.set_shared_data('system_info', info)
    self.event_client.post_event(Event(Event.Type.SYSTEM_INFO,
                                       system_info=info))
    logging.info('System info: %r', info)

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

  def handle_sigint(self, dummy_signum, dummy_frame):   # pylint: disable=W0613
    logging.error('Received SIGINT')
    self.run_enqueue(None)
    raise KeyboardInterrupt()

  def handle_sigterm(self, dummy_signum, dummy_frame):  # pylint: disable=W0613
    logging.error('Received SIGTERM')
    self.env.terminate()
    self.run_queue.put(None)
    raise RuntimeError('Received SIGTERM')

  def find_kcrashes(self):
    """Finds kcrash files, logs them, and marks them as seen."""
    seen_crashes = set(
        self.state_instance.get_shared_data('seen_crashes', optional=True)
        or [])

    for path in glob.glob('/var/spool/crash/*'):
      if not os.path.isfile(path):
        continue
      if path in seen_crashes:
        continue
      try:
        stat = os.stat(path)
        mtime = time_utils.TimeString(stat.st_mtime)
        logging.info(
            'Found new crash file %s (%d bytes at %s)',
            path, stat.st_size, mtime)
        extra_log_args = {}

        try:
          _, ext = os.path.splitext(path)
          if ext in ['.kcrash', '.meta']:
            ext = ext.replace('.', '')
            with open(path) as f:
              data = f.read(MAX_CRASH_FILE_SIZE)
              tell = f.tell()
            logging.info(
                'Contents of %s%s:%s',
                path,
                ('' if tell == stat.st_size
                 else '(truncated to %d bytes)' % MAX_CRASH_FILE_SIZE),
                ('\n' + data).replace('\n', '\n  ' + ext + '> '))
            extra_log_args['data'] = data

            # Copy to /var/factory/kcrash for posterity
            kcrash_dir = paths.GetFactoryRoot('kcrash')
            file_utils.TryMakeDirs(kcrash_dir)
            shutil.copy(path, kcrash_dir)
            logging.info('Copied to %s',
                         os.path.join(kcrash_dir, os.path.basename(path)))
        finally:
          # Even if something goes wrong with the above, still try to
          # log to event log
          self.event_log.Log('crash_file',
                             path=path, size=stat.st_size, mtime=mtime,
                             **extra_log_args)
      except:  # pylint: disable=W0702
        logging.exception('Unable to handle crash files %s', path)
      seen_crashes.add(path)

    self.state_instance.set_shared_data('seen_crashes', list(seen_crashes))

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

  def InitTestLists(self):
    """Reads in all test lists and sets the active test list.

    Returns:
      True if the active test list could be set, False if failed.
    """
    startup_errors = []
    self.test_lists, failed_files = test_lists.BuildAllTestLists(
        force_generic=(self.options.automation_mode is not None))
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

      # Prepare DUT link.
      if self.test_list.options.dut_options:
        logging.info('dut_options set by %s: %r', self.test_list.test_list_id,
                     self.test_list.options.dut_options)
      device_utils.PrepareDUTLink(**self.test_list.options.dut_options)

    # Show all startup errors.
    if startup_errors:
      self.state_instance.set_shared_data(
          'startup_error', '\n\n'.join(startup_errors))

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
      if self.options.monolithic:
        self.env.launch_chrome()
      else:
        # The presenter is responsible for launching Chrome. Let's just
        # wait here.
        self.env.controller_ready_for_ui()
      logging.info('Waiting for a web socket connection')
      self.web_socket_manager.wait()

      # Wait for the test widget size to be set; this is done in
      # an asynchronous RPC so there is a small chance that the
      # web socket might be opened first.
      for _ in range(100):  # 10 s
        try:
          if self.state_instance.get_shared_data('test_widget_size'):
            break
        except KeyError:
          pass  # Retry
        time.sleep(0.1)  # 100 ms
      else:
        logging.warn('Never received test_widget_size from UI')

  def init(self, args=None, env=None):
    """Initializes Goofy.

    Args:
      args: A list of command-line arguments.  Uses sys.argv if
        args is None.
      env: An Environment instance to use (or None to choose
        FakeChrootEnvironment or DUTEnvironment as appropriate).
    """
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
    parser.add_option('--ui_scale_factor', dest='ui_scale_factor',
                      type='int', default=1,
                      help=('Factor by which to scale UI '
                            '(Chrome UI only)'))
    parser.add_option('--test_list', dest='test_list',
                      metavar='TEST_LIST_ID',
                      help='Use test list whose id is TEST_LIST_ID')
    parser.add_option('--dummy_shopfloor', action='store_true',
                      help='Use a dummy shopfloor server')
    parser.add_option('--automation-mode',
                      choices=[m.lower() for m in AutomationMode],
                      default='none', help='Factory test automation mode.')
    parser.add_option('--no-auto-run-on-start', dest='auto_run_on_start',
                      action='store_false', default=True,
                      help=('do not automatically run the test list on goofy '
                            'start; this is only valid when factory test '
                            'automation is enabled'))
    parser.add_option('--handshake_timeout', dest='handshake_timeout',
                      type='float', default=0.3,
                      help=('RPC timeout when doing handshake between device '
                            'and presenter.'))
    parser.add_option('--standalone', dest='standalone',
                      action='store_true', default=False,
                      help=('Assume the presenter is running on the same '
                            'machines.'))
    parser.add_option('--monolithic', dest='monolithic',
                      action='store_true', default=False,
                      help='Run in monolithic mode (without presenter)')
    (self.options, self.args) = parser.parse_args(args)

    signal.signal(signal.SIGINT, self.handle_sigint)
    # TODO(hungte) SIGTERM does not work properly without Telemetry and should
    # be fixed.

    # Make sure factory directories exist.
    paths.GetLogRoot()
    paths.GetStateRoot()
    paths.GetTestDataRoot()

    global _inited_logging  # pylint: disable=W0603
    if not _inited_logging:
      factory.init_logging('goofy', verbose=self.options.verbose)
      _inited_logging = True

    if self.options.print_test_list:
      test_list = test_lists.BuildTestList(self.options.print_test_list)
      print(test_list.__repr__(recursive=True))
      sys.exit(0)

    event_log.IncrementBootSequence()
    testlog_goofy.IncrementInitCount()

    # Don't defer logging the initial event, so we can make sure
    # that device_id, reimage_id, etc. are all set up.
    self.event_log = EventLog('goofy', defer=False)
    self.testlog = testlog.Testlog(
        log_root=paths.GetLogRoot(), uuid=self.uuid)
    # Direct the logging calls to testlog as well.
    testlog.CapturePythonLogging(
        callback=self.testlog.primary_json.Log,
        level=logging.getLogger().getEffectiveLevel())

    if env:
      self.env = env
    elif sys_utils.InChroot():
      self.env = test_environment.FakeChrootEnvironment()
      logging.warn(
          'Using chroot environment: will not actually run autotests')
    elif self.options.ui == 'chrome':
      self.env = test_environment.DUTEnvironment()
    self.env.goofy = self
    # web_socket_manager will be initialized later
    # pylint: disable=W0108
    self.env.has_sockets = lambda: self.web_socket_manager.has_sockets()

    if self.options.restart:
      state.clear_state()

    if self.options.ui_scale_factor != 1 and sys_utils.InQEMU():
      logging.warn(
          'In QEMU; ignoring ui_scale_factor argument')
      self.options.ui_scale_factor = 1

    logging.info('Started')

    if not self.options.monolithic:
      self.link_manager = PresenterLinkManager(
          check_interval=1,
          handshake_timeout=self.options.handshake_timeout,
          standalone=self.options.standalone)

    self.start_state_server()
    self.state_instance.set_shared_data('hwid_cfg', get_hwid_cfg())
    self.state_instance.set_shared_data('ui_scale_factor',
                                        self.options.ui_scale_factor)
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
    except:  # pylint: disable=W0702
      exc_info = sys.exc_info()

    if not success:
      if exc_info:
        logging.exception('Unable to initialize test lists')
        self.state_instance.set_shared_data(
            'startup_error',
            'Unable to initialize test lists\n%s' % (
                traceback.format_exc()))
      if self.options.ui == 'chrome':
        # Create an empty test list with default options so that the rest of
        # startup can proceed.
        self.test_list = factory.FactoryTestList(
            [], self.state_instance, factory.Options())
      else:
        # Bail with an error; no point in starting up.
        sys.exit('No valid test list; exiting.')

    self.init_hooks()

    if self.test_list.options.clear_state_on_start:
      self.state_instance.clear_test_state()

    # If the phase is invalid, this will raise a ValueError.
    phase.SetPersistentPhase(self.test_list.options.phase)

    # For netboot firmware, mainfw_type should be 'netboot'.
    if (self.dut.info.mainfw_type != 'nonchrome' and
        self.dut.info.firmware_version is None):
      self.state_instance.set_shared_data(
          'startup_error',
          'Netboot firmware detected\n'
          'Connect Ethernet and reboot to re-image.\n'
          u'侦测到网路开机固件\n'
          u'请连接乙太网并重启')

    if not self.state_instance.has_shared_data('ui_lang'):
      self.state_instance.set_shared_data('ui_lang',
                                          self.test_list.options.ui_lang)
    self.state_instance.set_shared_data(
        'test_list_options',
        self.test_list.options.__dict__)
    self.state_instance.test_list = self.test_list

    self.check_log_rotation()

    if self.options.dummy_shopfloor:
      os.environ[shopfloor.SHOPFLOOR_SERVER_ENV_VAR_NAME] = (
          'http://%s:%d/' %
          (net_utils.LOCALHOST, shopfloor.DEFAULT_SERVER_PORT))
      self.dummy_shopfloor = process_utils.Spawn(
          [os.path.join(paths.FACTORY_PATH, 'bin', 'shopfloor_server'),
           '--dummy'])
    elif self.test_list.options.shopfloor_server_url:
      shopfloor.set_server_url(self.test_list.options.shopfloor_server_url)
      shopfloor.set_enabled(True)

    self.init_states()
    self.start_event_server()
    self.start_terminal_server()

    # Load and run Goofy plugins.
    self.plugin_controller = plugin_controller.PluginController(
        self.test_list.options.plugin_config_name, self)
    self.plugin_controller.StartAllPlugins()

    # Set reference to the Instalog plugin.
    self.testlog.SetInstalogPlugin(
        self.plugin_controller.GetPluginInstance('instalog'))

    # Note that we create a log watcher even if
    # sync_event_log_period_secs isn't set (no background
    # syncing), since we may use it to flush event logs as well.
    self.log_watcher = EventLogWatcher(
        self.test_list.options.sync_event_log_period_secs,
        event_log_db_file=None,
        handle_event_logs_callback=self.handle_event_logs)
    if self.test_list.options.sync_event_log_period_secs:
      self.log_watcher.StartWatchThread()

    self.update_system_info()

    os.environ['CROS_FACTORY'] = '1'
    os.environ['CROS_DISABLE_SITE_SYSINFO'] = '1'

    self.find_kcrashes()

    # Should not move earlier.
    self.hooks.OnStartup()

    # Only after this point the Goofy backend is ready for UI connection.
    self.ready_for_ui_connection = True

    # Create download path for autotest beforehand or autotests run at
    # the same time might fail due to race condition.
    if not sys_utils.InChroot():
      file_utils.TryMakeDirs(os.path.join('/usr/local/autotest', 'tests',
                                          'download'))

    def state_change_callback(test, test_state):
      self.event_client.post_event(
          Event(Event.Type.STATE_CHANGE, path=test.path, state=test_state))
    self.test_list.state_change_callback = state_change_callback

    self.autotest_prespawner = prespawner.AutotestPrespawner()
    self.autotest_prespawner.start()

    self.pytest_prespawner = prespawner.PytestPrespawner()
    self.pytest_prespawner.start()

    tests_after_shutdown = self.state_instance.get_shared_data(
        TESTS_AFTER_SHUTDOWN, optional=True)
    force_auto_run = (tests_after_shutdown == FORCE_AUTO_RUN)

    if not force_auto_run and tests_after_shutdown is not None:
      logging.info('Resuming tests after shutdown: %r', tests_after_shutdown)
      self.test_list_iterator = tests_after_shutdown
      self.test_list_iterator.set_test_list(self.test_list)
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

    self.dut.hooks.OnTestStart()

    self.may_disable_cros_shortcut_keys()

  def may_disable_cros_shortcut_keys(self):
    test_options = self.test_list.options
    if test_options.disable_cros_shortcut_keys:
      logging.info('Filter ChromeOS shortcut keys.')
      self.key_filter = KeyFilter(
          unmap_caps_lock=test_options.disable_caps_lock,
          caps_lock_keycode=test_options.caps_lock_keycode)
      self.key_filter.Start()

  def check_log_rotation(self):
    """Checks log rotation file presence/absence according to test_list option.

    Touch /var/lib/cleanup_logs_paused if test_list.options.disable_log_rotation
    is True, delete it otherwise. This must be done in idle loop because
    autotest client will touch /var/lib/cleanup_logs_paused each time it runs
    an autotest.
    """
    if sys_utils.InChroot():
      return
    try:
      if self.test_list.options.disable_log_rotation:
        open(CLEANUP_LOGS_PAUSED, 'w').close()
      else:
        file_utils.TryUnlink(CLEANUP_LOGS_PAUSED)
    except:  # pylint: disable=W0702
      # Oh well.  Logs an error (but no trace)
      logging.info(
          'Unable to %s %s: %s',
          'touch' if self.test_list.options.disable_log_rotation else 'delete',
          CLEANUP_LOGS_PAUSED, debug_utils.FormatExceptionOnly())

  def perform_periodic_tasks(self):
    """Override of base method to perform periodic work.

    This method must not raise exceptions.
    """
    super(Goofy, self).perform_periodic_tasks()

    self.check_plugins()
    self.check_for_updates()
    self.check_log_rotation()

  def handle_event_logs(self, chunks, periodic=False):
    """Callback for event watcher.

    Attempts to upload the event logs to the shopfloor server.

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
        shopfloor_client = shopfloor.get_instance(
            detect=True,
            timeout=self.test_list.options.shopfloor_timeout_secs,
            quiet=quiet)
        shopfloor_client.UploadEvent(chunk.log_name + '.' +
                                     event_log.GetReimageId(),
                                     Binary(chunk.chunk))
        logging.info(
            'Successfully synced %s in %.03f s',
            description, time.time() - start_time)
      except:  # pylint: disable=W0702
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
          logging.warning('Suppress periodic shopfloor error messages for '
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
    for test in root.walk():
      test.update_state(status=TestState.UNTESTED)
    self.run_tests(root)

  def auto_run(self, root=None):
    """"Auto-runs" tests that have not been run yet.

    Args:
      starting_at: If provide, only auto-runs tests beginning with
        this test.
      root: If provided, the root of tests to run. If not provided, the root
        will be test_list (root of all tests).
    """
    root = root or self.test_list
    self.run_tests_with_status([TestState.UNTESTED, TestState.ACTIVE],
                               root=root)

  def handle_switch_test(self, event):
    """Switches to a particular test.

    Args:
      event: The SWITCH_TEST event.
    """
    test = self.test_list.lookup_path(event.path)
    if not test:
      logging.error('Unknown test %r', event.key)
      return

    invoc = self.invocations.get(test)
    if invoc:
      # Already running: just bring to the front if it
      # has a UI.
      logging.info('Setting visible test to %s', test.path)
      self.set_visible_test(test)
      return

    self.abort_active_tests('Operator requested abort (switch_test)')
    for t in test.walk():
      t.update_state(status=TestState.UNTESTED)

    self.run_tests(test)

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
    self.dut.hooks.OnTestFailure(test)
    if self.link_manager:
      self.link_manager.UpdateStatus(False)


if __name__ == '__main__':
  Goofy.run_main_and_exit()
