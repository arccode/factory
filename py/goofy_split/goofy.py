#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The main factory flow that runs the factory test and finalizes a device."""

import glob
import logging
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
from collections import deque
from optparse import OptionParser

import factory_common  # pylint: disable=W0611
from cros.factory import event_log
from cros.factory import system
from cros.factory.event_log import EventLog, FloatDigit
from cros.factory.event_log_watcher import EventLogWatcher
from cros.factory.goofy_split import test_environment
from cros.factory.goofy_split import time_sanitizer
from cros.factory.goofy_split import updater
from cros.factory.goofy_split.goofy_base import GoofyBase
from cros.factory.goofy_split.goofy_rpc import GoofyRPC
from cros.factory.goofy_split.invocation import TestArgEnv
from cros.factory.goofy_split.invocation import TestInvocation
from cros.factory.goofy_split.link_manager import PresenterLinkManager
from cros.factory.goofy_split.prespawner import Prespawner
from cros.factory.goofy_split.system_log_manager import SystemLogManager
from cros.factory.goofy_split.web_socket_manager import WebSocketManager
from cros.factory.system.board import Board, BoardException
from cros.factory.system.charge_manager import ChargeManager
from cros.factory.system.core_dump_manager import CoreDumpManager
from cros.factory.system.cpufreq_manager import CpufreqManager
from cros.factory.system import disk_space
from cros.factory.test import factory
from cros.factory.test import phase
from cros.factory.test import state
from cros.factory.test import shopfloor
from cros.factory.test import utils
from cros.factory.test.test_lists import test_lists
from cros.factory.test.e2e_test.common import (
    AutomationMode, AutomationModePrompt, ParseAutomationMode)
from cros.factory.test.event import Event
from cros.factory.test.event import EventClient
from cros.factory.test.event import EventServer
from cros.factory.test.factory import TestState
from cros.factory.test.utils import Enum
from cros.factory.tools.key_filter import KeyFilter
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn


HWID_CFG_PATH = '/usr/local/share/chromeos-hwid/cfg'
CACHES_DIR = os.path.join(factory.get_state_root(), "caches")

CLEANUP_LOGS_PAUSED = '/var/lib/cleanup_logs_paused'

# Value for tests_after_shutdown that forces auto-run (e.g., after
# a factory update, when the available set of tests might change).
FORCE_AUTO_RUN = 'force_auto_run'

# Sync disks when battery level is higher than this value.
# Otherwise, power loss during disk sync operation may incur even worse outcome.
MIN_BATTERY_LEVEL_FOR_DISK_SYNC = 1.0

MAX_CRASH_FILE_SIZE = 64*1024

Status = Enum(['UNINITIALIZED', 'INITIALIZING', 'RUNNING',
               'TERMINATING', 'TERMINATED'])

def get_hwid_cfg():
  """Returns the HWID config tag, or an empty string if none can be found."""
  if 'CROS_HWID' in os.environ:
    return os.environ['CROS_HWID']
  if os.path.exists(HWID_CFG_PATH):
    with open(HWID_CFG_PATH, 'rt') as hwid_cfg_handle:
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
    connection_manager: The connection_manager object.
    system_log_manager: The SystemLogManager object.
    core_dump_manager: The CoreDumpManager object.
    ui_process: The factory ui process object.
    invocations: A map from FactoryTest objects to the corresponding
      TestInvocations objects representing active tests.
    tests_to_run: A deque of tests that should be run when the current
      test(s) complete.
    options: Command-line options.
    args: Command-line args.
    test_list: The test list.
    test_lists: All new-style test lists.
    run_id: The identifier for latest test run.
    scheduled_run_tests: The list of tests scheduled for latest test run.
    event_handlers: Map of Event.Type to the method used to handle that
      event.  If the method has an 'event' argument, the event is passed
      to the handler.
    last_log_disk_space_message: The last message we logged about disk space
      (to avoid duplication).
    last_kick_sync_time: The last time to kick system_log_manager to sync
      because of core dump files (to avoid kicking too soon then abort the
      sync.)
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
    self.connection_manager = None
    self.charge_manager = None
    self.time_sanitizer = None
    self.time_synced = False
    self.log_watcher = None
    self.system_log_manager = None
    self.core_dump_manager = None
    self.event_log = None
    self.prespawner = None
    self.ui_process = None
    self.dummy_shopfloor = None
    self.invocations = {}
    self.tests_to_run = deque()
    self.visible_test = None
    self.chrome = None
    self.hooks = None
    self.cpu_usage_watcher = None

    self.options = None
    self.args = None
    self.test_list = None
    self.test_lists = None
    self.run_id = None
    self.scheduled_run_tests = None
    self.on_ui_startup = []
    self.env = None
    self.last_idle = None
    self.last_shutdown_time = None
    self.last_update_check = None
    self.last_sync_time = None
    self.last_log_disk_space_time = None
    self.last_log_disk_space_message = None
    self.last_check_battery_time = None
    self.last_check_battery_message = None
    self.last_kick_sync_time = None
    self.exclusive_items = set()
    self.event_log = None
    self.key_filter = None
    self.cpufreq_manager = None
    self.status = Status.UNINITIALIZED
    self.ready_for_ui_connection = False
    self.link_manager = None

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
      Event.Type.SHOW_NEXT_ACTIVE_TEST:
        lambda event: self.show_next_active_test(),
      Event.Type.RESTART_TESTS:
        lambda event: self.restart_tests(root=test_or_root(event)),
      Event.Type.AUTO_RUN:
        lambda event: self.auto_run(root=test_or_root(event)),
      Event.Type.RE_RUN_FAILED:
        lambda event: self.re_run_failed(root=test_or_root(event)),
      Event.Type.RUN_TESTS_WITH_STATUS:
        lambda event: self.run_tests_with_status(
          event.status,
          root=test_or_root(event)),
      Event.Type.REVIEW:
        lambda event: self.show_review_information(),
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
        lambda event: self.clear_state(self.test_list.lookup_path(event.path)),
    }

    self.web_socket_manager = None

  def destroy(self):
    """ Performs any shutdown tasks. Overrides base class method. """
    self.status = Status.TERMINATING
    if self.chrome:
      self.chrome.kill()
      self.chrome = None
    if self.dummy_shopfloor:
      self.dummy_shopfloor.kill()
      self.dummy_shopfloor = None
    if self.ui_process:
      utils.kill_process_tree(self.ui_process, 'ui')
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
    if self.system_log_manager:
      if self.system_log_manager.IsThreadRunning():
        self.system_log_manager.Stop()
      self.system_log_manager = None
    if self.prespawner:
      logging.info('Stopping prespawner')
      self.prespawner.stop()
      self.prespawner = None
    if self.event_client:
      logging.info('Closing event client')
      self.event_client.close()
      self.event_client = None
    if self.cpufreq_manager:
      self.cpufreq_manager.Stop()
    if self.event_log:
      self.event_log.Close()
      self.event_log = None
    if self.key_filter:
      self.key_filter.Stop()
    if self.cpu_usage_watcher:
      self.cpu_usage_watcher.terminate()
    if self.link_manager:
      self.link_manager.Stop()
      self.link_manager = None

    super(Goofy, self).destroy()
    logging.info('Done destroying Goofy')
    self.status = Status.TERMINATED

  def start_state_server(self):
    # Before starting state server, remount stateful partitions with
    # no commit flag.  The default commit time (commit=600) makes corruption
    # too likely.
    utils.ResetCommitTime()

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
    self.state_server.add_handler("/event",
      self.web_socket_manager.handle_web_socket)

  def start_ui(self):
    ui_proc_args = [
      os.path.join(factory.FACTORY_PACKAGE_PATH, 'test', 'ui.py'),
      self.options.test_list]
    if self.options.verbose:
      ui_proc_args.append('-v')
    logging.info('Starting ui %s', ui_proc_args)
    self.ui_process = Spawn(ui_proc_args)
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
    if utils.in_chroot():
      return

    try:
      var_log_messages = (
        utils.var_log_messages_before_reboot())
      logging.info(
        'Tail of /var/log/messages before last reboot:\n'
        '%s', ('\n'.join(
            '  ' + x for x in var_log_messages)))
    except:  # pylint: disable=W0702
      logging.exception('Unable to grok /var/log/messages')

    try:
      mosys_log = Spawn(
          ['mosys', 'eventlog', 'list'],
          read_stdout=True, log_stderr_on_error=True).stdout_data
      logging.info('System eventlog from mosys:\n%s\n', mosys_log)
    except:  # pylint: disable=W0702
      logging.exception('Unable to read mosys eventlog')

    try:
      board = system.GetBoard()
      ec_console_log = board.GetECConsoleLog()
      logging.info('EC console log after reboot:\n%s\n', ec_console_log)
    except:  # pylint: disable=W0702
      logging.exception('Error retrieving EC console log')

    try:
      board = system.GetBoard()
      ec_panic_info = board.GetECPanicInfo()
      logging.info('EC panic info after reboot:\n%s\n', ec_panic_info)
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
        'tests_after_shutdown',
        [t.path for t in self.tests_to_run])
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
      self.state_instance.set_shared_data('tests_after_shutdown', None)
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

    # Insert current shutdown test at the front of the list of tests to run
    # after shutdown.  This is to continue on post-shutdown verification in the
    # shutdown step.
    tests_after_shutdown = self.state_instance.get_shared_data(
        'tests_after_shutdown', optional=True)
    if not tests_after_shutdown:
      self.state_instance.set_shared_data('tests_after_shutdown', [test.path])
    elif isinstance(tests_after_shutdown, list):
      self.state_instance.set_shared_data(
          'tests_after_shutdown', [test.path] + tests_after_shutdown)

    # Set 'post_shutdown' to inform shutdown test that a shutdown just occurred.
    self.state_instance.set_shared_data('post_shutdown', True)

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
            var_log_messages = (
              utils.var_log_messages_before_reboot())
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

        if mosys_log is None and not utils.in_chroot():
          try:
            mosys_log = Spawn(
                ['mosys', 'eventlog', 'list'],
                read_stdout=True, log_stderr_on_error=True).stdout_data
            # Write it to the log also.
            logging.info('System eventlog from mosys:\n%s\n', mosys_log)
          except:  # pylint: disable=W0702
            logging.exception('Unable to read mosys eventlog')

        if ec_console_log is None:
          try:
            board = system.GetBoard()
            ec_console_log = board.GetECConsoleLog()
            logging.info('EC console log after reboot:\n%s\n', ec_console_log)
          except:  # pylint: disable=W0702
            logging.exception('Error retrieving EC console log')

        if ec_panic_info is None:
          try:
            board = system.GetBoard()
            ec_panic_info = board.GetECPanicInfo()
            logging.info('EC panic info after reboot:\n%s\n', ec_panic_info)
          except:  # pylint: disable=W0702
            logging.exception('Error retrieving EC panic info')

        error_msg = 'Unexpected shutdown while test was running'
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

        if not test.never_fails:
          # For "never_fails" tests (such as "Start"), don't cancel
          # pending tests, since reboot is expected.
          factory.console.info('Unexpected shutdown while test %s '
                               'running; cancelling any pending tests',
                               test.path)
          self.state_instance.set_shared_data('tests_after_shutdown', [])

    self.update_skipped_tests()

  def update_skipped_tests(self):
    """Updates skipped states based on run_if."""
    env = TestArgEnv()
    def _evaluate_skip_from_run_if(test):
      """Returns the run_if evaluation of the test.

      Args:
        test: A FactoryTest object.

      Returns:
        The run_if evaluation result. Returns False if the test has no
        run_if argument.
      """
      value = None
      if test.run_if_expr:
        try:
          value = test.run_if_expr(env)
        except:  # pylint: disable=W0702
          logging.exception('Unable to evaluate run_if expression for %s',
                            test.path)
          # But keep going; we have no choice.  This will end up
          # always activating the test.
      elif test.run_if_table_name:
        try:
          aux = shopfloor.get_selected_aux_data(test.run_if_table_name)
          value = aux.get(test.run_if_col)
        except ValueError:
          # Not available; assume it shouldn't be skipped
          pass

      if value is None:
        skip = False
      else:
        skip = (not value) ^ t.run_if_not
      return skip

    # Gets all run_if evaluation, and stores results in skip_map.
    skip_map = dict()
    for t in self.test_list.walk():
      skip_map[t.path] = _evaluate_skip_from_run_if(t)

    # Propagates the skip value from root of tree and updates skip_map.
    def _update_skip_map_from_node(test, skip_from_parent):
      """Updates skip_map from a given node.

      Given a FactoryTest node and the skip value from parent, updates the
      skip value of current node in the skip_map if skip value from parent is
      True. If this node has children, recursively propagate this value to all
      its children, that is, all its subtests.
      Note that this function only updates value in skip_map, not the actual
      test_list tree.

      Args:
        test: The given FactoryTest object. It is a node in the test_list tree.
        skip_from_parent: The skip value which propagates from the parent of
          input node.
      """
      skip_this_tree = skip_from_parent or skip_map[test.path]
      if skip_this_tree:
        logging.info('Skip from node %r', test.path)
        skip_map[test.path] = True
      if test.is_leaf():
        return
      # Propagates skip value to its subtests
      for subtest in test.subtests:
        _update_skip_map_from_node(subtest, skip_this_tree)

    _update_skip_map_from_node(self.test_list, False)

    # Updates the skip value from skip_map to test_list tree. Also, updates test
    # status if needed.
    for t in self.test_list.walk():
      skip = skip_map[t.path]
      test_state = t.get_state()
      if ((not skip) and
          (test_state.status == TestState.PASSED) and
          (test_state.error_msg == TestState.SKIPPED_MSG)):
        # It was marked as skipped before, but now we need to run it.
        # Mark as untested.
        t.update_state(skip=skip, status=TestState.UNTESTED, error_msg='')
      else:
        t.update_state(skip=skip)

  def show_next_active_test(self):
    """Rotates to the next visible active test."""
    self.reap_completed_tests()
    active_tests = [
      t for t in self.test_list.walk()
      if t.is_leaf() and t.get_state().status == TestState.ACTIVE]
    if not active_tests:
      return

    try:
      next_test = active_tests[
        (active_tests.index(self.visible_test) + 1) % len(active_tests)]
    except ValueError:  # visible_test not present in active_tests
      next_test = active_tests[0]

    self.set_visible_test(next_test)

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

  def run_next_test(self):
    """Runs the next eligible test (or tests) in self.tests_to_run."""
    self.reap_completed_tests()
    if self.tests_to_run and self.check_critical_factory_note():
      self.tests_to_run.clear()
      return
    while self.tests_to_run:
      logging.debug('Tests to run: %s', [x.path for x in self.tests_to_run])

      test = self.tests_to_run[0]

      if test in self.invocations:
        logging.info('Next test %s is already running', test.path)
        self.tests_to_run.popleft()
        return

      for requirement in test.require_run:
        for i in requirement.test.walk():
          if i.get_state().status == TestState.ACTIVE:
            logging.info('Waiting for active test %s to complete '
                         'before running %s', i.path, test.path)
            return

      if self.invocations and not (test.backgroundable and all(
        [x.backgroundable for x in self.invocations])):
        logging.debug('Waiting for non-backgroundable tests to '
                      'complete before running %s', test.path)
        return

      if test.get_state().skip:
        factory.console.info('Skipping test %s', test.path)
        test.update_state(status=TestState.PASSED,
                          error_msg=TestState.SKIPPED_MSG)
        self.tests_to_run.popleft()
        continue

      self.tests_to_run.popleft()

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

      if (isinstance(test, factory.ShutdownStep) and
          self.state_instance.get_shared_data('post_shutdown', optional=True)):
        # Invoking post shutdown method of shutdown test. We should retain the
        # iterations_left and retries_left of the original test state.
        test_state = self.state_instance.get_test_state(test.path)
        self._run_test(test, test_state.iterations_left,
                       test_state.retries_left)
      else:
        # Starts a new test run; reset iterations and retries.
        self._run_test(test, test.iterations, test.retries)

  def _run_test(self, test, iterations_left=None, retries_left=None):
    invoc = TestInvocation(self, test, on_completion=self.run_next_test)
    new_state = test.update_state(
        status=TestState.ACTIVE, increment_count=1, error_msg='',
        invocation=invoc.uuid, iterations_left=iterations_left,
        retries_left=retries_left,
        visible=(self.visible_test == test))
    invoc.count = new_state.count

    self.invocations[test] = invoc
    if self.visible_test is None and test.has_ui:
      self.set_visible_test(test)
    self.check_exclusive()
    invoc.start()

  def check_exclusive(self):
    # alias since this is really long
    EXCL_OPT = factory.FactoryTest.EXCLUSIVE_OPTIONS

    current_exclusive_items = set([
        item for item in EXCL_OPT
        if any([test.is_exclusive(item) for test in self.invocations])])

    new_exclusive_items = current_exclusive_items - self.exclusive_items
    if EXCL_OPT.NETWORKING in new_exclusive_items:
      logging.info('Disabling network')
      self.connection_manager.DisableNetworking()
    if EXCL_OPT.CHARGER in new_exclusive_items:
      logging.info('Stop controlling charger')

    new_non_exclusive_items = self.exclusive_items - current_exclusive_items
    if EXCL_OPT.NETWORKING in new_non_exclusive_items:
      logging.info('Re-enabling network')
      self.connection_manager.EnableNetworking()
    if EXCL_OPT.CHARGER in new_non_exclusive_items:
      logging.info('Start controlling charger')

    if self.cpufreq_manager:
      enabled = EXCL_OPT.CPUFREQ not in current_exclusive_items
      try:
        self.cpufreq_manager.SetEnabled(enabled)
      except:  # pylint: disable=W0702
        logging.exception('Unable to %s cpufreq services',
                          'enable' if enabled else 'disable')

    # Only adjust charge state if not excluded
    if (EXCL_OPT.CHARGER not in current_exclusive_items and
        not utils.in_chroot()):
      if self.charge_manager:
        self.charge_manager.AdjustChargeState()
      else:
        try:
          system.GetBoard().SetChargeState(Board.ChargeState.CHARGE)
        except BoardException:
          logging.exception('Unable to set charge state on this board')

    self.exclusive_items = current_exclusive_items

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
        if system.SystemInfo.update_md5sum != new_update_md5sum:
          logging.info('Received new update MD5SUM: %s', new_update_md5sum)
          system.SystemInfo.update_md5sum = new_update_md5sum
          self.run_enqueue(self.update_system_info)

    updater.CheckForUpdateAsync(
      handle_check_for_update,
      self.test_list.options.shopfloor_timeout_secs)

  def cancel_pending_tests(self):
    """Cancels any tests in the run queue."""
    self.run_tests([])

  def restore_active_run_state(self):
    """Restores active run id and the list of scheduled tests."""
    self.run_id = self.state_instance.get_shared_data('run_id', optional=True)
    self.scheduled_run_tests = self.state_instance.get_shared_data(
        'scheduled_run_tests', optional=True)

  def set_active_run_state(self):
    """Sets active run id and the list of scheduled tests."""
    self.run_id = str(uuid.uuid4())
    self.scheduled_run_tests = [test.path for test in self.tests_to_run]
    self.state_instance.set_shared_data('run_id', self.run_id)
    self.state_instance.set_shared_data('scheduled_run_tests',
                                        self.scheduled_run_tests)

  def run_tests(self, subtrees, untested_only=False):
    """Runs tests under subtree.

    The tests are run in order unless one fails (then stops).
    Backgroundable tests are run simultaneously; when a foreground test is
    encountered, we wait for all active tests to finish before continuing.

    Args:
      subtrees: Node or nodes containing tests to run (may either be
        a single test or a list).  Duplicates will be ignored.
      untested_only: True to run untested tests only.
    """
    if type(subtrees) != list:
      subtrees = [subtrees]

    # Nodes we've seen so far, to avoid duplicates.
    seen = set()

    self.tests_to_run = deque()
    for subtree in subtrees:
      for test in subtree.walk():
        if test in seen:
          continue
        seen.add(test)

        if not test.is_leaf():
          continue
        if (untested_only and test.get_state().status != TestState.UNTESTED):
          continue
        self.tests_to_run.append(test)
    if subtrees:
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

        # Stop on failure if flag is true.
        if (self.test_list.options.stop_on_failure and
            new_state.status == TestState.FAILED):
          # Clean all the tests to cause goofy to stop.
          self.tests_to_run = []
          factory.console.info("Stop on failure triggered. Empty the queue.")

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
    for test, invoc in self.invocations.items():
      if root and not test.has_ancestor(root):
        continue

      factory.console.info('Killing active test %s...' % test.path)
      invoc.abort_and_join(reason)
      factory.console.info('Killed %s' % test.path)
      test.update_state(**invoc.update_state_on_completion)
      del self.invocations[test]

      if not abort:
        test.update_state(status=TestState.UNTESTED)
    self.reap_completed_tests()

  def stop(self, root=None, fail=False, reason=None):
    self.kill_active_tests(fail, root, reason)
    # Remove any tests in the run queue under the root.
    self.tests_to_run = deque([x for x in self.tests_to_run
                               if root and not x.has_ancestor(root)])
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
    except:
      if self.event_log:
        try:
          self.event_log.Log('goofy_init',
                     success=False,
                     trace=traceback.format_exc())
        except:  # pylint: disable=W0702
          pass
      raise

    self.status = Status.RUNNING
    syslog.syslog('Goofy (factory test harness) starting')
    self.run()

  def update_system_info(self):
    """Updates system info."""
    system_info = system.SystemInfo()
    self.state_instance.set_shared_data('system_info', system_info.__dict__)
    self.event_client.post_event(Event(Event.Type.SYSTEM_INFO,
                       system_info=system_info.__dict__))
    logging.info('System info: %r', system_info.__dict__)

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
        self.state_instance.set_shared_data('tests_after_shutdown',
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
        mtime = utils.TimeString(stat.st_mtime)
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
            kcrash_dir = factory.get_factory_root('kcrash')
            utils.TryMakeDirs(kcrash_dir)
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
    """Reads in all test lists and sets the active test list."""
    self.test_lists = test_lists.BuildAllTestLists(
        force_generic=(self.options.automation_mode is not None))
    logging.info('Loaded test lists: [%s]',
                 test_lists.DescribeTestLists(self.test_lists))

    if not self.options.test_list:
      self.options.test_list = test_lists.GetActiveTestListId()

    if os.sep in self.options.test_list:
      # It's a path pointing to an old-style test list; use it.
      self.test_list = factory.read_test_list(self.options.test_list)
    else:
      self.test_list = self.GetTestList(self.options.test_list)

    logging.info('Active test list: %s', self.test_list.test_list_id)

    if isinstance(self.test_list, test_lists.OldStyleTestList):
      # Actually load it in.  (See OldStyleTestList for an explanation
      # of why this is necessary.)
      self.test_list = self.test_list.Load()

    self.test_list.state_instance = self.state_instance

  def init_hooks(self):
    """Initializes hooks.

    Must run after self.test_list ready.
    """
    module, cls = self.test_list.options.hooks_class.rsplit('.', 1)
    self.hooks = getattr(__import__(module, fromlist=[cls]), cls)()
    assert isinstance(self.hooks, factory.Hooks), (
        "hooks should be of type Hooks but is %r" % type(self.hooks))
    self.hooks.test_list = self.test_list
    self.hooks.OnCreatedTestList()

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
                      metavar='FILE',
                      help='Read and print test list FILE, and exit')
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
                      metavar='FILE',
                      help='Use FILE as test list')
    parser.add_option('--dummy_shopfloor', action='store_true',
                      help='Use a dummy shopfloor server')
    parser.add_option('--automation-mode',
                      choices=[m.lower() for m in AutomationMode],
                      default='none', help="Factory test automation mode.")
    parser.add_option('--no-auto-run-on-start', dest='auto_run_on_start',
                      action='store_false', default=True,
                      help=('do not automatically run the test list on goofy '
                            'start; this is only valid when factory test '
                            'automation is enabled'))
    parser.add_option('--guest_login', dest='guest_login', default=False,
                      action='store_true',
                      help='Log in as guest. This will not own the TPM.')
    parser.add_option('--use-telemetry', dest='use_telemetry',
                      action='store_true', default=False,
                      help='Use Telemetry for Chrome UI invocation.')
    (self.options, self.args) = parser.parse_args(args)

    signal.signal(signal.SIGINT, self.handle_sigint)
    # TODO(hungte) SIGTERM does not work properly without Telemetry and should
    # be fixed.
    if self.options.use_telemetry:
      signal.signal(signal.SIGTERM, self.handle_sigterm)

    # Make sure factory directories exist.
    factory.get_log_root()
    factory.get_state_root()
    factory.get_test_data_root()

    global _inited_logging  # pylint: disable=W0603
    if not _inited_logging:
      factory.init_logging('goofy', verbose=self.options.verbose)
      _inited_logging = True

    if self.options.print_test_list:
      print factory.read_test_list(
          self.options.print_test_list).__repr__(recursive=True)
      sys.exit(0)

    event_log.IncrementBootSequence()
    # Don't defer logging the initial event, so we can make sure
    # that device_id, reimage_id, etc. are all set up.
    self.event_log = EventLog('goofy', defer=False)

    if env:
      self.env = env
    elif factory.in_chroot():
      self.env = test_environment.FakeChrootEnvironment()
      logging.warn(
        'Using chroot environment: will not actually run autotests')
    elif self.options.ui == 'chrome':
      if self.options.use_telemetry:
        if self.options.guest_login:
          os.mknod(test_environment.DUTTelemetryEnvironment.GUEST_MODE_TAG_FILE)
        self.env = test_environment.DUTTelemetryEnvironment()
      else:
        self.env = test_environment.DUTEnvironment()
    self.env.goofy = self
    # web_socket_manager will be initialized later
    # pylint: disable=W0108
    self.env.has_sockets = lambda: self.web_socket_manager.has_sockets()

    if self.options.restart:
      state.clear_state()

    if self.options.ui_scale_factor != 1 and utils.in_qemu():
      logging.warn(
        'In QEMU; ignoring ui_scale_factor argument')
      self.options.ui_scale_factor = 1

    logging.info('Started')

    self.link_manager = PresenterLinkManager(check_interval=1)

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

    # Set use_telemetry in shared data so that factory tests can look it up.
    self.state_instance.set_shared_data('use_telemetry',
                                        self.options.use_telemetry)

    try:
      self.InitTestLists()
    except:  # pylint: disable=W0702
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

    if system.SystemInfo().firmware_version is None and not utils.in_chroot():
      self.state_instance.set_shared_data('startup_error',
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
          'http://localhost:%d/' % shopfloor.DEFAULT_SERVER_PORT)
      self.dummy_shopfloor = Spawn(
          [os.path.join(factory.FACTORY_PATH, 'bin', 'shopfloor_server'),
           '--dummy'])
    elif self.test_list.options.shopfloor_server_url:
      shopfloor.set_server_url(self.test_list.options.shopfloor_server_url)
      shopfloor.set_enabled(True)

    if self.test_list.options.time_sanitizer and not utils.in_chroot():
      self.time_sanitizer = time_sanitizer.TimeSanitizer(
        base_time=time_sanitizer.GetBaseTimeFromFile(
          # lsb-factory is written by the factory install shim during
          # installation, so it should have a good time obtained from
          # the mini-Omaha server.  If it's not available, we'll use
          # /etc/lsb-factory (which will be much older, but reasonably
          # sane) and rely on a shopfloor sync to set a more accurate
          # time.
          '/usr/local/etc/lsb-factory',
          '/etc/lsb-release'))
      self.time_sanitizer.RunOnce()

    if self.test_list.options.check_cpu_usage_period_secs:
      self.cpu_usage_watcher = Spawn(['py/tools/cpu_usage_monitor.py',
          '-p', str(self.test_list.options.check_cpu_usage_period_secs)],
          cwd=factory.FACTORY_PATH)

    self.init_states()
    self.start_event_server()
    self.connection_manager = self.env.create_connection_manager(
      self.test_list.options.wlans,
      self.test_list.options.scan_wifi_period_secs)
    # Note that we create a log watcher even if
    # sync_event_log_period_secs isn't set (no background
    # syncing), since we may use it to flush event logs as well.
    self.log_watcher = EventLogWatcher(
      self.test_list.options.sync_event_log_period_secs,
      event_log_db_file=None,
      handle_event_logs_callback=self.handle_event_logs)
    if self.test_list.options.sync_event_log_period_secs:
      self.log_watcher.StartWatchThread()

    # Creates a system log manager to scan logs periocially.
    # A scan includes clearing logs and optionally syncing logs if
    # enable_syng_log is True. We kick it to sync logs.
    self.system_log_manager = SystemLogManager(
      sync_log_paths=self.test_list.options.sync_log_paths,
      sync_log_period_secs=self.test_list.options.sync_log_period_secs,
      scan_log_period_secs=self.test_list.options.scan_log_period_secs,
      clear_log_paths=self.test_list.options.clear_log_paths,
      clear_log_excluded_paths=self.test_list.options.clear_log_excluded_paths)
    self.system_log_manager.Start()

    self.update_system_info()

    assert ((self.test_list.options.min_charge_pct is None) ==
            (self.test_list.options.max_charge_pct is None))
    if utils.in_chroot():
      logging.info('In chroot, ignoring charge manager and charge state')
    elif (self.test_list.options.enable_charge_manager and
          self.test_list.options.min_charge_pct is not None):
      self.charge_manager = ChargeManager(self.test_list.options.min_charge_pct,
                                          self.test_list.options.max_charge_pct)
      system.SystemStatus.charge_manager = self.charge_manager
    else:
      # Goofy should set charger state to charge if charge_manager is disabled.
      try:
        system.GetBoard().SetChargeState(Board.ChargeState.CHARGE)
      except BoardException:
        logging.exception('Unable to set charge state on this board')

    self.core_dump_manager = CoreDumpManager(
        self.test_list.options.core_dump_watchlist)

    os.environ['CROS_FACTORY'] = '1'
    os.environ['CROS_DISABLE_SITE_SYSINFO'] = '1'

    if not utils.in_chroot() and self.test_list.options.use_cpufreq_manager:
      logging.info('Enabling CPU frequency manager')
      self.cpufreq_manager = CpufreqManager(event_log=self.event_log)

    # Startup hooks may want to skip some tests.
    self.update_skipped_tests()

    self.find_kcrashes()

    # Should not move earlier.
    self.hooks.OnStartup()

    # Only after this point the Goofy backend is ready for UI connection.
    self.ready_for_ui_connection = True

    if self.options.ui == 'chrome':
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

    # Create download path for autotest beforehand or autotests run at
    # the same time might fail due to race condition.
    if not factory.in_chroot():
      utils.TryMakeDirs(os.path.join('/usr/local/autotest', 'tests',
                                     'download'))

    def state_change_callback(test, test_state):
      self.event_client.post_event(
          Event(Event.Type.STATE_CHANGE, path=test.path, state=test_state))
    self.test_list.state_change_callback = state_change_callback

    for handler in self.on_ui_startup:
      handler()

    self.prespawner = Prespawner()
    self.prespawner.start()

    tests_after_shutdown = self.state_instance.get_shared_data(
        'tests_after_shutdown', optional=True)

    force_auto_run = (tests_after_shutdown == FORCE_AUTO_RUN)
    if not force_auto_run and tests_after_shutdown is not None:
      logging.info('Resuming tests after shutdown: %s', tests_after_shutdown)
      self.tests_to_run.extend(
          self.test_list.lookup_path(t) for t in tests_after_shutdown)
      self.run_enqueue(self.run_next_test)
    else:
      if force_auto_run or self.test_list.options.auto_run_on_start:
        # If automation mode is enabled, allow suppress auto_run_on_start.
        if (self.options.automation_mode == 'NONE' or
            self.options.auto_run_on_start):
          self.run_enqueue(
              lambda: self.run_tests(self.test_list, untested_only=True))
    self.state_instance.set_shared_data('tests_after_shutdown', None)
    self.restore_active_run_state()

    self.may_disable_cros_shortcut_keys()

  def may_disable_cros_shortcut_keys(self):
    test_options = self.test_list.options
    if test_options.disable_cros_shortcut_keys:
      logging.info('Filter ChromeOS shortcut keys.')
      self.key_filter = KeyFilter(
          unmap_caps_lock=test_options.disable_caps_lock,
          caps_lock_keycode=test_options.caps_lock_keycode)
      self.key_filter.Start()

  def _should_sync_time(self, foreground=False):
    """Returns True if we should attempt syncing time with shopfloor.

    Args:
      foreground: If True, synchronizes even if background syncing
        is disabled (e.g., in explicit sync requests from the
        SyncShopfloor test).
    """
    return ((foreground or
             self.test_list.options.sync_time_period_secs) and
            self.time_sanitizer and
            (not self.time_synced) and
            (not factory.in_chroot()))

  def sync_time_with_shopfloor_server(self, foreground=False):
    """Syncs time with shopfloor server, if not yet synced.

    Args:
      foreground: If True, synchronizes even if background syncing
        is disabled (e.g., in explicit sync requests from the
        SyncShopfloor test).

    Returns:
      False if no time sanitizer is available, or True if this sync (or a
      previous sync) succeeded.

    Raises:
      Exception if unable to contact the shopfloor server.
    """
    if self._should_sync_time(foreground):
      self.time_sanitizer.SyncWithShopfloor()
      self.time_synced = True
    return self.time_synced

  def log_disk_space_stats(self):
    if (utils.in_chroot() or
        not self.test_list.options.log_disk_space_period_secs):
      return

    now = time.time()
    if (self.last_log_disk_space_time and
        now - self.last_log_disk_space_time <
        self.test_list.options.log_disk_space_period_secs):
      return
    self.last_log_disk_space_time = now

    # Upload event if stateful partition usage is above threshold.
    # Stateful partition is mounted on /usr/local, while
    # encrypted stateful partition is mounted on /var.
    # If there are too much logs in the factory process,
    # these two partitions might get full.
    try:
      vfs_infos = disk_space.GetAllVFSInfo()
      stateful_info, encrypted_info = None, None
      for vfs_info in vfs_infos.values():
        if '/usr/local' in vfs_info.mount_points:
          stateful_info = vfs_info
        if '/var' in vfs_info.mount_points:
          encrypted_info = vfs_info

      stateful = disk_space.GetPartitionUsage(stateful_info)
      encrypted = disk_space.GetPartitionUsage(encrypted_info)

      above_threshold =  (
          self.test_list.options.stateful_usage_threshold and
          max(stateful.bytes_used_pct,
              stateful.inodes_used_pct,
              encrypted.bytes_used_pct,
              encrypted.inodes_used_pct) >
              self.test_list.options.stateful_usage_threshold)

      if above_threshold:
        self.event_log.Log('stateful_partition_usage',
            partitions={
                'stateful': {
                    'bytes_used_pct': FloatDigit(stateful.bytes_used_pct, 2),
                    'inodes_used_pct': FloatDigit(stateful.inodes_used_pct, 2)},
                'encrypted_stateful': {
                    'bytes_used_pct': FloatDigit(encrypted.bytes_used_pct, 2),
                    'inodes_used_pct': FloatDigit(encrypted.inodes_used_pct, 2)}
            })
        self.log_watcher.ScanEventLogs()
        if (not utils.in_chroot() and
            self.test_list.options.stateful_usage_above_threshold_action):
          Spawn(self.test_list.options.stateful_usage_above_threshold_action,
                call=True)

      message = disk_space.FormatSpaceUsedAll(vfs_infos)
      if message != self.last_log_disk_space_message:
        if above_threshold:
          logging.warning(message)
        else:
          logging.info(message)
        self.last_log_disk_space_message = message
    except:  # pylint: disable=W0702
      logging.exception('Unable to get disk space used')

  def check_battery(self):
    """Checks the current battery status.

    Logs current battery charging level and status to log. If the battery level
    is lower below warning_low_battery_pct, send warning event to shopfloor.
    If the battery level is lower below critical_low_battery_pct, flush disks.
    """
    if not self.test_list.options.check_battery_period_secs:
      return

    now = time.time()
    if (self.last_check_battery_time and
        now - self.last_check_battery_time <
        self.test_list.options.check_battery_period_secs):
      return
    self.last_check_battery_time = now

    message = ''
    log_level = logging.INFO
    try:
      power = system.GetBoard().power
      if not power.CheckBatteryPresent():
        message = 'Battery is not present'
      else:
        ac_present = power.CheckACPresent()
        charge_pct = power.GetChargePct(get_float=True)
        message = ('Current battery level %.1f%%, AC charger is %s' %
                   (charge_pct, 'connected' if ac_present else 'disconnected'))

        if charge_pct > self.test_list.options.critical_low_battery_pct:
          critical_low_battery = False
        else:
          critical_low_battery = True
          # Only sync disks when battery level is still above minimum
          # value. This can be used for offline analysis when shopfloor cannot
          # be connected.
          if charge_pct > MIN_BATTERY_LEVEL_FOR_DISK_SYNC:
            logging.warning('disk syncing for critical low battery situation')
            os.system('sync; sync; sync')
          else:
            logging.warning('disk syncing is cancelled '
                            'because battery level is lower than %.1f',
                            MIN_BATTERY_LEVEL_FOR_DISK_SYNC)

        # Notify shopfloor server
        if (critical_low_battery or
            (not ac_present and
             charge_pct <= self.test_list.options.warning_low_battery_pct)):
          log_level = logging.WARNING

          self.event_log.Log('low_battery',
                             battery_level=charge_pct,
                             charger_connected=ac_present,
                             critical=critical_low_battery)
          self.log_watcher.KickWatchThread()
          if self.test_list.options.enable_sync_log:
            self.system_log_manager.KickToSync()
    except: # pylint: disable=W0702
      logging.exception('Unable to check battery or notify shopfloor')
    finally:
      if message != self.last_check_battery_message:
        logging.log(log_level, message)
        self.last_check_battery_message = message

  def check_core_dump(self):
    """Checks if there is any core dumped file.

    Removes unwanted core dump files immediately.
    Syncs those files matching watch list to server with a delay between
    each sync. After the files have been synced to server, deletes the files.
    """
    core_dump_files = self.core_dump_manager.ScanFiles()
    if core_dump_files:
      now = time.time()
      if (self.last_kick_sync_time and now - self.last_kick_sync_time <
          self.test_list.options.kick_sync_min_interval_secs):
        return
      self.last_kick_sync_time = now

      # Sends event to server
      self.event_log.Log('core_dumped', files=core_dump_files)
      self.log_watcher.KickWatchThread()

      # Syncs files to server
      if self.test_list.options.enable_sync_log:
        self.system_log_manager.KickToSync(
            core_dump_files, self.core_dump_manager.ClearFiles)

  def check_log_rotation(self):
    """Checks log rotation file presence/absence according to test_list option.

    Touch /var/lib/cleanup_logs_paused if test_list.options.disable_log_rotation
    is True, delete it otherwise. This must be done in idle loop because
    autotest client will touch /var/lib/cleanup_logs_paused each time it runs
    an autotest.
    """
    if utils.in_chroot():
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
          CLEANUP_LOGS_PAUSED, utils.FormatExceptionOnly())

  def sync_time_in_background(self):
    """Writes out current time and tries to sync with shopfloor server."""
    if not self.time_sanitizer:
      return

    # Write out the current time.
    self.time_sanitizer.SaveTime()

    if not self._should_sync_time():
      return

    now = time.time()
    if self.last_sync_time and (
        now - self.last_sync_time <
        self.test_list.options.sync_time_period_secs):
      # Not yet time for another check.
      return
    self.last_sync_time = now

    def target():
      try:
        self.sync_time_with_shopfloor_server()
      except:  # pylint: disable=W0702
        # Oh well.  Log an error (but no trace)
        logging.info(
          'Unable to get time from shopfloor server: %s',
          utils.FormatExceptionOnly())

    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()

  def perform_periodic_tasks(self):
    """Override of base method to perform periodic work.

    This method must not raise exceptions.
    """
    super(Goofy, self).perform_periodic_tasks()

    self.check_exclusive()
    self.check_for_updates()
    self.sync_time_in_background()
    self.log_disk_space_stats()
    self.check_battery()
    self.check_core_dump()
    self.check_log_rotation()

  def handle_event_logs(self, chunks):
    """Callback for event watcher.

    Attempts to upload the event logs to the shopfloor server.

    Args:
      chunks: A list of Chunk objects.
    """
    first_exception = None
    exception_count = 0

    for chunk in chunks:
      try:
        description = 'event logs (%s)' % str(chunk)
        start_time = time.time()
        shopfloor_client = shopfloor.get_instance(
          detect=True,
          timeout=self.test_list.options.shopfloor_timeout_secs)
        shopfloor_client.UploadEvent(chunk.log_name + "." +
                                     event_log.GetReimageId(),
                                     Binary(chunk.chunk))
        logging.info(
          'Successfully synced %s in %.03f s',
          description, time.time() - start_time)
      except: # pylint: disable=W0702
        first_exception = (first_exception or (chunk.log_name + ': ' +
                                               utils.FormatExceptionOnly()))
        exception_count += 1

    if exception_count:
      if exception_count == 1:
        msg = 'Log upload failed: %s' % first_exception
      else:
        msg = '%d log upload failed; first is: %s' % (
            exception_count, first_exception)
      raise Exception(msg)


  def run_tests_with_status(self, statuses_to_run, starting_at=None,
    root=None):
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

    if starting_at:
      # Make sure they passed a test, not a string.
      assert isinstance(starting_at, factory.FactoryTest)

    tests_to_reset = []
    tests_to_run = []

    found_starting_at = False

    for test in root.get_top_level_tests():
      if starting_at:
        if test == starting_at:
          # We've found starting_at; do auto-run on all
          # subsequent tests.
          found_starting_at = True
        if not found_starting_at:
          # Don't start this guy yet
          continue

      status = test.get_state().status
      if status == TestState.ACTIVE or status in statuses_to_run:
        # Reset the test (later; we will need to abort
        # all active tests first).
        tests_to_reset.append(test)
      if status in statuses_to_run:
        tests_to_run.append(test)

    self.abort_active_tests('Operator requested run/re-run of certain tests')

    # Reset all statuses of the tests to run (in case any tests were active;
    # we want them to be run again).
    for test_to_reset in tests_to_reset:
      for test in test_to_reset.walk():
        test.update_state(status=TestState.UNTESTED)

    self.run_tests(tests_to_run, untested_only=True)

  def restart_tests(self, root=None):
    """Restarts all tests."""
    root = root or self.test_list

    self.abort_active_tests('Operator requested restart of certain tests')
    for test in root.walk():
      test.update_state(status=TestState.UNTESTED)
    self.run_tests(root)

  def auto_run(self, starting_at=None, root=None):
    """"Auto-runs" tests that have not been run yet.

    Args:
      starting_at: If provide, only auto-runs tests beginning with
        this test.
      root: If provided, the root of tests to run. If not provided, the root
        will be test_list (root of all tests).
    """
    root = root or self.test_list
    self.run_tests_with_status([TestState.UNTESTED, TestState.ACTIVE],
                   starting_at=starting_at,
                   root=root)

  def re_run_failed(self, root=None):
    """Re-runs failed tests."""
    root = root or self.test_list
    self.run_tests_with_status([TestState.FAILED], root=root)

  def show_review_information(self):
    """Event handler for showing review information screen.

    The information screen is rendered by main UI program (ui.py), so in
    goofy we only need to kill all active tests, set them as untested, and
    clear remaining tests.
    """
    self.kill_active_tests(False)
    self.cancel_pending_tests()

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
    if invoc and test.backgroundable:
      # Already running: just bring to the front if it
      # has a UI.
      logging.info('Setting visible test to %s', test.path)
      self.set_visible_test(test)
      return

    self.abort_active_tests('Operator requested abort (switch_test)')
    for t in test.walk():
      t.update_state(status=TestState.UNTESTED)

    if self.test_list.options.auto_run_on_keypress:
      self.auto_run(starting_at=test)
    else:
      self.run_tests(test)

  def wait(self):
    """Waits for all pending invocations.

    Useful for testing.
    """
    while self.invocations:
      for k, v in self.invocations.iteritems():
        logging.info('Waiting for %s to complete...', k)
        v.thread.join()
      self.reap_completed_tests()


if __name__ == '__main__':
  goofy = Goofy()
  try:
    goofy.main()
  except SystemExit:
    # Propagate SystemExit without logging.
    raise
  except:
    # Log the error before trying to shut down (unless it's a graceful
    # exit).
    logging.exception('Error in main loop')
    raise
  finally:
    goofy.destroy()
