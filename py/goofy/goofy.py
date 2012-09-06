#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''
The main factory flow that runs the factory test and finalizes a device.
'''

import logging
import os
import Queue
import signal
import sys
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
from cros.factory.event_log import EventLog
from cros.factory.goofy import test_environment
from cros.factory.goofy import time_sanitizer
from cros.factory.goofy import updater
from cros.factory.goofy.event_log_watcher import EventLogWatcher
from cros.factory.goofy.goofy_rpc import GoofyRPC
from cros.factory.goofy.invocation import TestInvocation
from cros.factory.goofy.prespawner import Prespawner
from cros.factory.goofy.web_socket_manager import WebSocketManager
from cros.factory.system.charge_manager import ChargeManager
from cros.factory.test import factory
from cros.factory.test import state
from cros.factory.test import shopfloor
from cros.factory.test import utils
from cros.factory.test.event import Event
from cros.factory.test.event import EventClient
from cros.factory.test.event import EventServer
from cros.factory.test.factory import TestState
from cros.factory.utils.process_utils import Spawn


DEFAULT_TEST_LISTS_DIR = os.path.join(factory.FACTORY_PATH, 'test_lists')
CUSTOM_DIR = os.path.join(factory.FACTORY_PATH, 'custom')
HWID_CFG_PATH = '/usr/local/share/chromeos-hwid/cfg'

# File that suppresses reboot if present (e.g., for development).
NO_REBOOT_FILE = '/var/log/factory.noreboot'

# Value for tests_after_shutdown that forces auto-run (e.g., after
# a factory update, when the available set of tests might change).
FORCE_AUTO_RUN = 'force_auto_run'

RUN_QUEUE_TIMEOUT_SECS = 10

GOOFY_IN_CHROOT_WARNING = '\n' + ('*' * 70) + '''
You are running Goofy inside the chroot.  Autotests are not supported.

To use Goofy in the chroot, first install an Xvnc server:

  sudo apt-get install tightvncserver

...and then start a VNC X server outside the chroot:

  vncserver :10 &
  vncviewer :10

...and run Goofy as follows:

  env --unset=XAUTHORITY DISPLAY=localhost:10 python goofy.py
''' + ('*' * 70)
suppress_chroot_warning = False

def get_hwid_cfg():
  '''
  Returns the HWID config tag, or an empty string if none can be found.
  '''
  if 'CROS_HWID' in os.environ:
    return os.environ['CROS_HWID']
  if os.path.exists(HWID_CFG_PATH):
    with open(HWID_CFG_PATH, 'rt') as hwid_cfg_handle:
      return hwid_cfg_handle.read().strip()
  return ''


def find_test_list():
  '''
  Returns the path to the active test list, based on the HWID config tag.
  '''
  hwid_cfg = get_hwid_cfg()

  search_dirs = [CUSTOM_DIR, DEFAULT_TEST_LISTS_DIR]

  # Try in order: test_list_${hwid_cfg}, test_list, test_list.all
  search_files = ['test_list', 'test_list.all']
  if hwid_cfg:
    search_files.insert(0, hwid_cfg)

  for d in search_dirs:
    for f in search_files:
      test_list = os.path.join(d, f)
      if os.path.exists(test_list):
        return test_list

  logging.warn('Cannot find test lists named any of %s in any of %s',
         search_files, search_dirs)
  return None

_inited_logging = False

class Goofy(object):
  '''
  The main factory flow.

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
    network_enabled: Whether the connection_manager is currently
      enabling connections.
    ui_process: The factory ui process object.
    run_queue: A queue of callbacks to invoke from the main thread.
    invocations: A map from FactoryTest objects to the corresponding
      TestInvocations objects representing active tests.
    tests_to_run: A deque of tests that should be run when the current
      test(s) complete.
    options: Command-line options.
    args: Command-line args.
    test_list: The test list.
    event_handlers: Map of Event.Type to the method used to handle that
      event.  If the method has an 'event' argument, the event is passed
      to the handler.
    exceptions: Exceptions encountered in invocation threads.
  '''
  def __init__(self):
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
    self.network_enabled = True
    self.event_log = None
    self.prespawner = None
    self.ui_process = None
    self.dummy_shopfloor = None
    self.run_queue = Queue.Queue()
    self.invocations = {}
    self.tests_to_run = deque()
    self.visible_test = None
    self.chrome = None

    self.options = None
    self.args = None
    self.test_list = None
    self.on_ui_startup = []
    self.env = None
    self.last_idle = None
    self.last_shutdown_time = None
    self.last_update_check = None
    self.last_sync_time = None

    def test_or_root(event, parent_or_group=True):
      '''Returns the test affected by a particular event.

      Args:
        event: The event containing an optional 'path' attribute.
        parent_on_group: If True, returns the top-level parent for a test (the
          root node of the tests that need to be run together if the given test
          path is to be run).
      '''
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
                                fail=getattr(event, 'fail', False)),
      Event.Type.SET_VISIBLE_TEST:
        lambda event: self.set_visible_test(
          self.test_list.lookup_path(event.path)),
    }

    self.exceptions = []
    self.web_socket_manager = None

  def destroy(self):
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
    if self.prespawner:
      logging.info('Stopping prespawner')
      self.prespawner.stop()
      self.prespawner = None
    if self.event_client:
      logging.info('Closing event client')
      self.event_client.close()
      self.event_client = None
    if self.event_log:
      self.event_log.Close()
      self.event_log = None
    self.check_exceptions()
    logging.info('Done destroying Goofy')

  def start_state_server(self):
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

  def handle_shutdown_complete(self, test, test_state):
    '''
    Handles the case where a shutdown was detected during a shutdown step.

    @param test: The ShutdownStep.
    @param test_state: The test state.
    '''
    test_state = test.update_state(increment_shutdown_count=1)
    logging.info('Detected shutdown (%d of %d)',
           test_state.shutdown_count, test.iterations)

    def log_and_update_state(status, error_msg, **kw):
      self.event_log.Log('rebooted',
                 status=status, error_msg=error_msg, **kw)
      test.update_state(status=status, error_msg=error_msg)

    if not self.last_shutdown_time:
      log_and_update_state(status=TestState.FAILED,
                 error_msg='Unable to read shutdown_time')
      return

    now = time.time()
    logging.info('%.03f s passed since reboot',
           now - self.last_shutdown_time)

    if self.last_shutdown_time > now:
      test.update_state(status=TestState.FAILED,
                error_msg='Time moved backward during reboot')
    elif (isinstance(test, factory.RebootStep) and
        self.test_list.options.max_reboot_time_secs and
        (now - self.last_shutdown_time >
         self.test_list.options.max_reboot_time_secs)):
      # A reboot took too long; fail.  (We don't check this for
      # HaltSteps, because the machine could be halted for a
      # very long time, and even unplugged with battery backup,
      # thus hosing the clock.)
      log_and_update_state(
        status=TestState.FAILED,
        error_msg=('More than %d s elapsed during reboot '
               '(%.03f s, from %s to %s)' % (
            self.test_list.options.max_reboot_time_secs,
            now - self.last_shutdown_time,
            utils.TimeString(self.last_shutdown_time),
            utils.TimeString(now))),
        duration=(now-self.last_shutdown_time))
    elif test_state.shutdown_count == test.iterations:
      # Good!
      log_and_update_state(status=TestState.PASSED,
                 duration=(now - self.last_shutdown_time),
                 error_msg='')
    elif test_state.shutdown_count > test.iterations:
      # Shut down too many times
      log_and_update_state(status=TestState.FAILED,
                 error_msg='Too many shutdowns')
    elif utils.are_shift_keys_depressed():
      logging.info('Shift keys are depressed; cancelling restarts')
      # Abort shutdown
      log_and_update_state(
        status=TestState.FAILED,
        error_msg='Shutdown aborted with double shift keys')
      self.cancel_pending_tests()
    else:
      def handler():
        if self._prompt_cancel_shutdown(
          test, test_state.shutdown_count + 1):
          factory.console.info('Shutdown aborted by operator')
          log_and_update_state(
            status=TestState.FAILED,
            error_msg='Shutdown aborted by operator')
          self.cancel_pending_tests()
          return

        # Time to shutdown again
        log_and_update_state(
          status=TestState.ACTIVE,
          error_msg='',
          iteration=test_state.shutdown_count)

        self.event_log.Log('shutdown', operation='reboot')
        self.state_instance.set_shared_data('shutdown_time',
                        time.time())
        self.env.shutdown('reboot')

      self.on_ui_startup.append(handler)

  def _prompt_cancel_shutdown(self, test, iteration):
    if self.options.ui != 'chrome':
      return False

    pending_shutdown_data = {
      'delay_secs': test.delay_secs,
      'time': time.time() + test.delay_secs,
      'operation': test.operation,
      'iteration': iteration,
      'iterations': test.iterations,
      }

    # Create a new (threaded) event client since we
    # don't want to use the event loop for this.
    with EventClient() as event_client:
      event_client.post_event(Event(Event.Type.PENDING_SHUTDOWN,
                      **pending_shutdown_data))
      aborted = event_client.wait(
        lambda event: event.type == Event.Type.CANCEL_SHUTDOWN,
        timeout=test.delay_secs) is not None
      if aborted:
        event_client.post_event(Event(Event.Type.PENDING_SHUTDOWN))
      return aborted

  def init_states(self):
    '''
    Initializes all states on startup.
    '''
    for test in self.test_list.get_all_tests():
      # Make sure the state server knows about all the tests,
      # defaulting to an untested state.
      test.update_state(update_parent=False, visible=False)

    var_log_messages = None
    mosys_log = None
    ec_console_log = None

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
        self.handle_shutdown_complete(test, test_state)
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
            mosys_log = utils.Spawn(
                ['mosys', 'eventlog', 'list'],
                read_stdout=True, log_stderr_on_error=True).stdout_data
            # Write it to the log also.
            logging.info('System eventlog from mosys:\n%s\n', mosys_log)
          except:  # pylint: disable=W0702
            logging.exception('Unable to read mosys eventlog')

        if ec_console_log is None:
          try:
            ec = system.GetEC()
            ec_console_log = ec.GetConsoleLog()
            logging.info('EC console log after reboot:\n%s\n', ec_console_log)
          except:  # pylint: disable=W0702
            logging.exception('Error retrieving EC console log')

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
    '''
    Updates skipped states based on run_if.
    '''
    for t in self.test_list.walk():
      if t.is_leaf() and t.run_if_table_name:
        skip = False
        try:
          aux = shopfloor.get_selected_aux_data(t.run_if_table_name)
          value = aux.get(t.run_if_col)
          if value is not None:
            skip = (not value) ^ t.run_if_not
        except ValueError:
          # Not available; assume it shouldn't be skipped
          pass

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
    '''
    Rotates to the next visible active test.
    '''
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
    '''
    Handles an event from the event server.
    '''
    handler = self.event_handlers.get(event.type)
    if handler:
      handler(event)
    else:
      # We don't register handlers for all event types - just ignore
      # this event.
      logging.debug('Unbound event type %s', event.type)

  def run_next_test(self):
    '''
    Runs the next eligible test (or tests) in self.tests_to_run.
    '''
    self.reap_completed_tests()
    while self.tests_to_run:
      logging.debug('Tests to run: %s',
              [x.path for x in self.tests_to_run])

      test = self.tests_to_run[0]

      if test in self.invocations:
        logging.info('Next test %s is already running', test.path)
        self.tests_to_run.popleft()
        return

      if test.get_state().skip:
        factory.console.info('Skipping test %s', test.path)
        test.update_state(status=TestState.PASSED,
                          error_msg=TestState.SKIPPED_MSG)
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

      if isinstance(test, factory.ShutdownStep):
        if os.path.exists(NO_REBOOT_FILE):
          test.update_state(
            status=TestState.FAILED, increment_count=1,
            error_msg=('Skipped shutdown since %s is present' %
                       NO_REBOOT_FILE))
          continue

        test.update_state(status=TestState.ACTIVE, increment_count=1,
                  error_msg='', shutdown_count=0)
        if self._prompt_cancel_shutdown(test, 1):
          self.event_log.Log('reboot_cancelled')
          test.update_state(
            status=TestState.FAILED, increment_count=1,
            error_msg='Shutdown aborted by operator',
            shutdown_count=0)
          return

        # Save pending test list in the state server
        self.state_instance.set_shared_data(
          'tests_after_shutdown',
          [t.path for t in self.tests_to_run])
        # Save shutdown time
        self.state_instance.set_shared_data('shutdown_time',
                          time.time())

        with self.env.lock:
          self.event_log.Log('shutdown', operation=test.operation)
          shutdown_result = self.env.shutdown(test.operation)
        if shutdown_result:
          # That's all, folks!
          self.run_queue.put(None)
          return
        else:
          # Just pass (e.g., in the chroot).
          test.update_state(status=TestState.PASSED)
          self.state_instance.set_shared_data(
            'tests_after_shutdown', None)
          # Send event with no fields to indicate that there is no
          # longer a pending shutdown.
          self.event_client.post_event(Event(
              Event.Type.PENDING_SHUTDOWN))
          continue

      self._run_test(test, test.iterations)

  def _run_test(self, test, iterations_left=None):
    invoc = TestInvocation(self, test, on_completion=self.run_next_test)
    new_state = test.update_state(
      status=TestState.ACTIVE, increment_count=1, error_msg='',
      invocation=invoc.uuid, iterations_left=iterations_left)
    invoc.count = new_state.count

    self.invocations[test] = invoc
    if self.visible_test is None and test.has_ui:
      self.set_visible_test(test)
    self.check_connection_manager()
    invoc.start()

  def check_connection_manager(self):
    exclusive_tests = [
      test.path
      for test in self.invocations
      if test.is_exclusive(
        factory.FactoryTest.EXCLUSIVE_OPTIONS.NETWORKING)]
    if exclusive_tests:
      # Make sure networking is disabled.
      if self.network_enabled:
        logging.info('Disabling network, as requested by %s',
               exclusive_tests)
        self.connection_manager.DisableNetworking()
        self.network_enabled = False
    else:
      # Make sure networking is enabled.
      if not self.network_enabled:
        logging.info('Re-enabling network')
        self.connection_manager.EnableNetworking()
        self.network_enabled = True

  def check_for_updates(self):
    '''
    Schedules an asynchronous check for updates if necessary.
    '''
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
          self.run_queue.put(self.update_system_info)

    updater.CheckForUpdateAsync(
      handle_check_for_update,
      self.test_list.options.shopfloor_timeout_secs)

  def cancel_pending_tests(self):
    '''Cancels any tests in the run queue.'''
    self.run_tests([])

  def run_tests(self, subtrees, untested_only=False):
    '''
    Runs tests under subtree.

    The tests are run in order unless one fails (then stops).
    Backgroundable tests are run simultaneously; when a foreground test is
    encountered, we wait for all active tests to finish before continuing.

    @param subtrees: Node or nodes containing tests to run (may either be
      a single test or a list).  Duplicates will be ignored.
    '''
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
        if (untested_only and
          test.get_state().status != TestState.UNTESTED):
          continue
        self.tests_to_run.append(test)
    self.run_next_test()

  def reap_completed_tests(self):
    '''
    Removes completed tests from the set of active tests.

    Also updates the visible test if it was reaped.
    '''
    for t, v in dict(self.invocations).iteritems():
      if v.is_completed():
        new_state = t.update_state(**v.update_state_on_completion)
        del self.invocations[t]

        if new_state.iterations_left and new_state.status == TestState.PASSED:
          # Play it again, Sam!
          self._run_test(t)

    if (self.visible_test is None or
        self.visible_test not in self.invocations):
      self.set_visible_test(None)
      # Make the first running test, if any, the visible test
      for t in self.test_list.walk():
        if t in self.invocations:
          self.set_visible_test(t)
          break

  def kill_active_tests(self, abort, root=None):
    '''
    Kills and waits for all active tests.

    Args:
      abort: True to change state of killed tests to FAILED, False for
        UNTESTED.
      root: If set, only kills tests with root as an ancestor.
    '''
    self.reap_completed_tests()
    for test, invoc in self.invocations.items():
      if root and not test.has_ancestor(root):
        continue

      factory.console.info('Killing active test %s...' % test.path)
      invoc.abort_and_join()
      factory.console.info('Killed %s' % test.path)
      test.update_state(**invoc.update_state_on_completion)
      del self.invocations[test]

      if not abort:
        test.update_state(status=TestState.UNTESTED)
    self.reap_completed_tests()

  def stop(self, root=None, fail=False):
    self.kill_active_tests(fail, root)
    # Remove any tests in the run queue under the root.
    self.tests_to_run = deque([x for x in self.tests_to_run
                               if root and not x.has_ancestor(root)])
    self.run_next_test()

  def abort_active_tests(self):
    self.kill_active_tests(True)

  def main(self):
    try:
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

    self.run()

  def update_system_info(self):
    '''Updates system info.'''
    system_info = system.SystemInfo()
    self.state_instance.set_shared_data('system_info', system_info.__dict__)
    self.event_client.post_event(Event(Event.Type.SYSTEM_INFO,
                       system_info=system_info.__dict__))
    logging.info('System info: %r', system_info.__dict__)

  def update_factory(self, auto_run_on_restart=False, post_update_hook=None):
    '''Commences updating factory software.

    Args:
      auto_run_on_restart: Auto-run when the machine comes back up.
      post_update_hook: Code to call after update but immediately before
        restart.

    Returns:
      Never if the update was successful (we just reboot).
      False if the update was unnecessary (no update available).
    '''
    self.kill_active_tests(False)
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

  def handle_sigint(self, dummy_signum, dummy_frame):
    logging.error('Received SIGINT')
    self.run_queue.put(None)
    raise KeyboardInterrupt()

  def init(self, args=None, env=None):
    '''Initializes Goofy.

    Args:
      args: A list of command-line arguments.  Uses sys.argv if
        args is None.
      env: An Environment instance to use (or None to choose
        FakeChrootEnvironment or DUTEnvironment as appropriate).
    '''
    signal.signal(signal.SIGINT, self.handle_sigint)

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
                      choices=['none', 'gtk', 'chrome'],
                      default=('chrome' if utils.in_chroot() else 'gtk'),
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
    (self.options, self.args) = parser.parse_args(args)

    # Make sure factory directories exist.
    factory.get_log_root()
    factory.get_state_root()
    factory.get_test_data_root()

    global _inited_logging  # pylint: disable=W0603
    if not _inited_logging:
      factory.init_logging('goofy', verbose=self.options.verbose)
      _inited_logging = True

    event_log.IncrementBootSequence()
    self.event_log = EventLog('goofy')

    if (not suppress_chroot_warning and
      factory.in_chroot() and
      self.options.ui == 'gtk' and
      os.environ.get('DISPLAY') in [None, '', ':0', ':0.0']):
      # That's not going to work!  Tell the user how to run
      # this way.
      logging.warn(GOOFY_IN_CHROOT_WARNING)
      time.sleep(1)

    if env:
      self.env = env
    elif factory.in_chroot():
      self.env = test_environment.FakeChrootEnvironment()
      logging.warn(
        'Using chroot environment: will not actually run autotests')
    else:
      self.env = test_environment.DUTEnvironment()
    self.env.goofy = self

    if self.options.restart:
      state.clear_state()

    if self.options.print_test_list:
      print factory.read_test_list(
          self.options.print_test_list).__repr__(recursive=True)
      return

    if self.options.ui_scale_factor != 1 and utils.in_qemu():
      logging.warn(
        'In QEMU; ignoring ui_scale_factor argument')
      self.options.ui_scale_factor = 1

    logging.info('Started')

    self.start_state_server()
    self.state_instance.set_shared_data('hwid_cfg', get_hwid_cfg())
    self.state_instance.set_shared_data('ui_scale_factor',
                      self.options.ui_scale_factor)
    self.last_shutdown_time = (
      self.state_instance.get_shared_data('shutdown_time', optional=True))
    self.state_instance.del_shared_data('shutdown_time', optional=True)

    if not self.options.test_list:
      self.options.test_list = find_test_list()
      if not self.options.test_list:
        logging.error('No test list. Aborting.')
        sys.exit(1)
      logging.info('Using test list %s', self.options.test_list)

    self.test_list = factory.read_test_list(
      self.options.test_list,
      self.state_instance)
    if not self.state_instance.has_shared_data('ui_lang'):
      self.state_instance.set_shared_data('ui_lang',
                        self.test_list.options.ui_lang)
    self.state_instance.set_shared_data(
      'test_list_options',
      self.test_list.options.__dict__)
    self.state_instance.test_list = self.test_list

    if self.options.dummy_shopfloor:
      os.environ[shopfloor.SHOPFLOOR_SERVER_ENV_VAR_NAME] = (
          'http://localhost:%d/' % shopfloor.DEFAULT_SERVER_PORT)
      self.dummy_shopfloor = Spawn(
          [os.path.join(factory.FACTORY_PATH, 'bin', 'shopfloor_server'),
           '--dummy'])
    elif self.test_list.options.shopfloor_server_url:
      shopfloor.set_server_url(self.test_list.options.shopfloor_server_url)

    if self.test_list.options.time_sanitizer:
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
      handle_event_logs_callback=self.handle_event_logs)
    if self.test_list.options.sync_event_log_period_secs:
      self.log_watcher.StartWatchThread()

    self.update_system_info()

    assert ((self.test_list.options.min_charge_pct is None) ==
            (self.test_list.options.max_charge_pct is None))
    if (self.test_list.options.min_charge_pct and
        self.test_list.options.max_charge_pct):
      self.charge_manager = ChargeManager(self.test_list.options.min_charge_pct,
                                          self.test_list.options.max_charge_pct)

    os.environ['CROS_FACTORY'] = '1'
    os.environ['CROS_DISABLE_SITE_SYSINFO'] = '1'

    # Set CROS_UI since some behaviors in ui.py depend on the
    # particular UI in use.  TODO(jsalz): Remove this (and all
    # places it is used) when the GTK UI is removed.
    os.environ['CROS_UI'] = self.options.ui

    if self.options.ui == 'chrome':
      self.env.launch_chrome()
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
    elif self.options.ui == 'gtk':
      self.start_ui()

    def state_change_callback(test, test_state):
      self.event_client.post_event(
        Event(Event.Type.STATE_CHANGE,
            path=test.path, state=test_state))
    self.test_list.state_change_callback = state_change_callback

    for handler in self.on_ui_startup:
      handler()

    self.prespawner = Prespawner()
    self.prespawner.start()

    try:
      tests_after_shutdown = self.state_instance.get_shared_data(
        'tests_after_shutdown')
    except KeyError:
      tests_after_shutdown = None

    force_auto_run = (tests_after_shutdown == FORCE_AUTO_RUN)
    if not force_auto_run and tests_after_shutdown is not None:
      logging.info('Resuming tests after shutdown: %s',
             tests_after_shutdown)
      self.tests_to_run.extend(
        self.test_list.lookup_path(t) for t in tests_after_shutdown)
      self.run_queue.put(self.run_next_test)
    else:
      if force_auto_run or self.test_list.options.auto_run_on_start:
        self.run_queue.put(
          lambda: self.run_tests(self.test_list, untested_only=True))
    self.state_instance.set_shared_data('tests_after_shutdown', None)

  def run(self):
    '''Runs Goofy.'''
    # Process events forever.
    while self.run_once(True):
      pass

  def run_once(self, block=False):
    '''Runs all items pending in the event loop.

    Args:
      block: If true, block until at least one event is processed.

    Returns:
      True to keep going or False to shut down.
    '''
    events = utils.DrainQueue(self.run_queue)
    while not events:
      # Nothing on the run queue.
      self._run_queue_idle()
      if block:
        # Block for at least one event...
        try:
          events.append(self.run_queue.get(timeout=RUN_QUEUE_TIMEOUT_SECS))
        except Queue.Empty:
          # Keep going (calling _run_queue_idle() again at the top of
          # the loop)
          continue
        # ...and grab anything else that showed up at the same
        # time.
        events.extend(utils.DrainQueue(self.run_queue))
      else:
        break

    for event in events:
      if not event:
        # Shutdown request.
        self.run_queue.task_done()
        return False

      try:
        event()
      except:  # pylint: disable=W0702
        logging.exception('Error in event loop')
        self.record_exception(traceback.format_exception_only(
            *sys.exc_info()[:2]))
        # But keep going
      finally:
        self.run_queue.task_done()
    return True

  def _should_sync_time(self):
    '''Returns True if we should attempt syncing time with shopfloor.'''
    return (self.test_list.options.sync_time_period_secs and
            self.time_sanitizer and
            (not self.time_synced) and
            (not factory.in_chroot()))

  def sync_time_with_shopfloor_server(self):
    '''Syncs time with shopfloor server, if not yet synced.

    Returns:
      False if no time sanitizer is available, or True if this sync (or a
      previous sync) succeeded.

    Raises:
      Exception if unable to contact the shopfloor server.
    '''
    if self._should_sync_time():
      self.time_sanitizer.SyncWithShopfloor()
      self.time_synced = True
    return self.time_synced

  def sync_time_in_background(self):
    '''Writes out current time and tries to sync with shopfloor server.'''
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

  def _run_queue_idle(self):
    '''Invoked when the run queue has no events.

    This method must not raise exception.
    '''
    now = time.time()
    if (self.last_idle and
        now < (self.last_idle + RUN_QUEUE_TIMEOUT_SECS - 1)):
      # Don't run more often than once every (RUN_QUEUE_TIMEOUT_SECS -
      # 1) seconds.
      return

    self.last_idle = now

    self.check_connection_manager()
    self.check_for_updates()
    self.sync_time_in_background()
    if self.charge_manager:
      self.charge_manager.AdjustChargeState()

  def handle_event_logs(self, log_name, chunk):
    '''Callback for event watcher.

    Attempts to upload the event logs to the shopfloor server.
    '''
    description = 'event logs (%s, %d bytes)' % (log_name, len(chunk))
    start_time = time.time()
    logging.info('Syncing %s', description)
    shopfloor_client = shopfloor.get_instance(
      detect=True,
      timeout=self.test_list.options.shopfloor_timeout_secs)
    shopfloor_client.UploadEvent(log_name, Binary(chunk))
    logging.info(
      'Successfully synced %s in %.03f s',
      description, time.time() - start_time)

  def run_tests_with_status(self, statuses_to_run, starting_at=None,
    root=None):
    '''Runs all top-level tests with a particular status.

    All active tests, plus any tests to re-run, are reset.

    Args:
      starting_at: If provided, only auto-runs tests beginning with
        this test.
    '''
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

    self.abort_active_tests()

    # Reset all statuses of the tests to run (in case any tests were active;
    # we want them to be run again).
    for test_to_reset in tests_to_reset:
      for test in test_to_reset.walk():
        test.update_state(status=TestState.UNTESTED)

    self.run_tests(tests_to_run, untested_only=True)

  def restart_tests(self, root=None):
    '''Restarts all tests.'''
    root = root or self.test_list

    self.abort_active_tests()
    for test in root.walk():
      test.update_state(status=TestState.UNTESTED)
    self.run_tests(root)

  def auto_run(self, starting_at=None, root=None):
    '''"Auto-runs" tests that have not been run yet.

    Args:
      starting_at: If provide, only auto-runs tests beginning with
        this test.
    '''
    root = root or self.test_list
    self.run_tests_with_status([TestState.UNTESTED, TestState.ACTIVE],
                   starting_at=starting_at,
                   root=root)

  def re_run_failed(self, root=None):
    '''Re-runs failed tests.'''
    root = root or self.test_list
    self.run_tests_with_status([TestState.FAILED], root=root)

  def show_review_information(self):
    '''Event handler for showing review information screen.

    The information screene is rendered by main UI program (ui.py), so in
    goofy we only need to kill all active tests, set them as untested, and
    clear remaining tests.
    '''
    self.kill_active_tests(False)
    self.cancel_pending_tests()

  def handle_switch_test(self, event):
    '''Switches to a particular test.

    @param event: The SWITCH_TEST event.
    '''
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

    self.abort_active_tests()
    for t in test.walk():
      t.update_state(status=TestState.UNTESTED)

    if self.test_list.options.auto_run_on_keypress:
      self.auto_run(starting_at=test)
    else:
      self.run_tests(test)

  def wait(self):
    '''Waits for all pending invocations.

    Useful for testing.
    '''
    while self.invocations:
      for k, v in self.invocations.iteritems():
        logging.info('Waiting for %s to complete...', k)
        v.thread.join()
      self.reap_completed_tests()

  def check_exceptions(self):
    '''Raises an error if any exceptions have occurred in
    invocation threads.'''
    if self.exceptions:
      raise RuntimeError('Exception in invocation thread: %r' %
                 self.exceptions)

  def record_exception(self, msg):
    '''Records an exception in an invocation thread.

    An exception with the given message will be rethrown when
    Goofy is destroyed.'''
    self.exceptions.append(msg)


if __name__ == '__main__':
  goofy = Goofy()
  try:
    goofy.main()
  finally:
    goofy.destroy()
