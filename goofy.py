#!/usr/bin/python -u
#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''
The main factory flow that runs the factory test and finalizes a device.
'''

import array
import fcntl
import glob
import logging
import os
import cPickle as pickle
import pipes
import Queue
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unittest
import uuid
from collections import deque
from optparse import OptionParser
from StringIO import StringIO

import factory_common
from autotest_lib.client.bin.prespawner import Prespawner
from autotest_lib.client.cros import factory
from autotest_lib.client.cros.factory import state
from autotest_lib.client.cros.factory import TestState
from autotest_lib.client.cros.factory import updater
from autotest_lib.client.cros.factory import utils
from autotest_lib.client.cros.factory.event import Event
from autotest_lib.client.cros.factory.event import EventClient
from autotest_lib.client.cros.factory.event import EventServer
from autotest_lib.client.cros.factory.event_log import EventLog
from autotest_lib.client.cros.factory.invocation import TestInvocation
from autotest_lib.client.cros.factory import test_environment
from autotest_lib.client.cros.factory.web_socket_manager import WebSocketManager


DEFAULT_TEST_LIST_PATH = os.path.join(
        factory.CLIENT_PATH , 'site_tests', 'suite_Factory', 'test_list')
HWID_CFG_PATH = '/usr/local/share/chromeos-hwid/cfg'

# File that suppresses reboot if present (e.g., for development).
NO_REBOOT_FILE = '/var/log/factory.noreboot'

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

    # Try in order: test_list, test_list.$hwid_cfg, test_list.all
    if hwid_cfg:
        test_list = '%s_%s' % (DEFAULT_TEST_LIST_PATH, hwid_cfg)
        if os.path.exists(test_list):
            logging.info('Using special test list: %s', test_list)
            return test_list
        logging.info('WARNING: no specific test list for config: %s', hwid_cfg)

    test_list = DEFAULT_TEST_LIST_PATH
    if os.path.exists(test_list):
        return test_list

    test_list = ('%s.all' % DEFAULT_TEST_LIST_PATH)
    if os.path.exists(test_list):
        logging.info('Using default test list: ' + test_list)
        return test_list
    logging.info('ERROR: Cannot find any test list.')


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
        self.event_server = None
        self.event_server_thread = None
        self.event_client = None
        self.event_log = None
        self.prespawner = None
        self.ui_process = None
        self.run_queue = Queue.Queue()
        self.invocations = {}
        self.tests_to_run = deque()
        self.visible_test = None
        self.chrome = None

        self.options = None
        self.args = None
        self.test_list = None

        def test_or_root(event):
            '''Returns the top-level parent for a test (the root node of the
            tests that need to be run together if the given test path is to
            be run).'''
            try:
                path = event.path
            except AttributeError:
                path = None

            if path:
                return (self.test_list.lookup_path(path).
                        get_top_level_parent_or_group())
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
            Event.Type.REVIEW:
                lambda event: self.show_review_information(),
            Event.Type.UPDATE_SYSTEM_INFO:
                lambda event: self.update_system_info(),
            Event.Type.UPDATE_FACTORY:
                lambda event: self.update_factory(),
            Event.Type.STOP:
                lambda event: self.stop(),
        }

        self.exceptions = []
        self.web_socket_manager = None

    def destroy(self):
        if self.chrome:
            self.chrome.kill()
            self.chrome = None
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
        ui_proc_args = [os.path.join(factory.CROS_FACTORY_LIB_PATH, 'ui'),
                        self.options.test_list]
        if self.options.verbose:
            ui_proc_args.append('-v')
        logging.info('Starting ui %s', ui_proc_args)
        self.ui_process = subprocess.Popen(ui_proc_args)
        logging.info('Waiting for UI to come up...')
        self.event_client.wait(
            lambda event: event.type == Event.Type.UI_READY)
        logging.info('UI has started')

    def set_visible_test(self, test):
        if self.visible_test == test:
            return

        if test:
            test.update_state(visible=True)
        if self.visible_test:
            self.visible_test.update_state(visible=False)
        self.visible_test = test

    def handle_shutdown_complete(self, test, state):
        '''
        Handles the case where a shutdown was detected during a shutdown step.

        @param test: The ShutdownStep.
        @param state: The test state.
        '''
        state = test.update_state(increment_shutdown_count=1)
        logging.info('Detected shutdown (%d of %d)',
                     state.shutdown_count, test.iterations)
        if state.shutdown_count == test.iterations:
            # Good!
            test.update_state(status=TestState.PASSED, error_msg='')
        elif state.shutdown_count > test.iterations:
            # Shut down too many times
            test.update_state(status=TestState.FAILED,
                              error_msg='Too many shutdowns')
        elif utils.are_shift_keys_depressed():
            logging.info('Shift keys are depressed; cancelling restarts')
            # Abort shutdown
            test.update_state(
                status=TestState.FAILED,
                error_msg='Shutdown aborted with double shift keys')
        else:
            # Need to shutdown again
            self.event_log.Log('shutdown', operation='reboot')
            self.env.shutdown('reboot')

    def init_states(self):
        '''
        Initializes all states on startup.
        '''
        for test in self.test_list.get_all_tests():
            # Make sure the state server knows about all the tests,
            # defaulting to an untested state.
            test.update_state(update_parent=False, visible=False)

        # Any 'active' tests should be marked as failed now.
        for test in self.test_list.walk():
            state = test.get_state()
            if state.status != TestState.ACTIVE:
                continue
            if isinstance(test, factory.ShutdownStep):
                # Shutdown while the test was active - that's good.
                self.handle_shutdown_complete(test, state)
            else:
                test.update_state(status=TestState.FAILED,
                                  error_msg='Unknown (shutdown?)')

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

            if self.invocations and not (test.backgroundable and all(
                [x.backgroundable for x in self.invocations])):
                logging.debug('Waiting for non-backgroundable tests to '
                              'complete before running %s', test.path)
                return

            self.tests_to_run.popleft()

            if isinstance(test, factory.ShutdownStep):
                if os.path.exists(NO_REBOOT_FILE):
                    test.update_state(
                        status=TestState.FAILED, increment_count=1,
                        error_msg=('Skipped shutdown since %s is present' %
                                   NO_REBOOT_FILE))
                    continue

                test.update_state(status=TestState.ACTIVE, increment_count=1,
                                  error_msg='', shutdown_count=0)
                # Save pending test list in the state server
                self.state_instance.set_shared_data(
                    'tests_after_shutdown',
                    [t.path for t in self.tests_to_run])

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
                    continue

            invoc = TestInvocation(self, test, on_completion=self.run_next_test)
            self.invocations[test] = invoc
            if self.visible_test is None and test.has_ui:
                self.set_visible_test(test)
            invoc.start()

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
                del self.invocations[t]

        if (self.visible_test is None or
            self.visible_test not in self.invocations):
            self.set_visible_test(None)
            # Make the first running test, if any, the visible test
            for t in self.test_list.walk():
                if t in self.invocations:
                    self.set_visible_test(t)
                    break

    def kill_active_tests(self, abort):
        '''
        Kills and waits for all active tests.

        @param abort: True to change state of killed tests to FAILED, False for
                UNTESTED.
        '''
        self.reap_completed_tests()
        for test, invoc in self.invocations.items():
            factory.console.info('Killing active test %s...' % test.path)
            invoc.abort_and_join()
            factory.console.info('Killed %s' % test.path)
            del self.invocations[test]
            if not abort:
                test.update_state(status=TestState.UNTESTED)
        self.reap_completed_tests()

    def stop(self):
        self.kill_active_tests(False)
        self.run_tests([])

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
                except:
                    pass
            raise

        self.run()

    def update_system_info(self):
        '''Updates system info.'''
        system_info = test_environment.SystemInfo(self.env, self.state_instance)
        self.state_instance.set_shared_data('system_info', system_info.__dict__)
        self.event_client.post_event(Event(Event.Type.SYSTEM_INFO,
                                           system_info=system_info.__dict__))
        logging.info('System info: %r', system_info.__dict__)

    def update_factory(self):
        self.kill_active_tests(False)
        self.run_tests([])

        try:
            if updater.TryUpdate(pre_update_hook=self.state_instance.close):
                self.env.shutdown('reboot')
        except:
            factory.console.exception('Unable to update')

    def init(self, args=None, env=None):
        '''Initializes Goofy.

        Args:
            args: A list of command-line arguments.  Uses sys.argv if
                args is None.
            env: An Environment instance to use (or None to choose
                FakeChrootEnvironment or DUTEnvironment as appropriate).
        '''
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
                          default='gtk',
                          help='UI to use')
        parser.add_option('--ui_scale_factor', dest='ui_scale_factor',
                          type='int', default=1,
                          help=('Factor by which to scale UI '
                                '(Chrome UI only)'))
        parser.add_option('--test_list', dest='test_list',
                          metavar='FILE',
                          help='Use FILE as test list')
        (self.options, self.args) = parser.parse_args(args)

        global _inited_logging
        if not _inited_logging:
            factory.init_logging('goofy', verbose=self.options.verbose)
            _inited_logging = True
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
            print (factory.read_test_list(self.options.print_test_list).
                   __repr__(recursive=True))
            return

        logging.info('Started')

        self.start_state_server()
        self.state_instance.set_shared_data('hwid_cfg', get_hwid_cfg())
        self.state_instance.set_shared_data('ui_scale_factor',
                                            self.options.ui_scale_factor)

        self.options.test_list = (self.options.test_list or find_test_list())
        self.test_list = factory.read_test_list(self.options.test_list,
                                                self.state_instance)
        if not self.state_instance.has_shared_data('ui_lang'):
            self.state_instance.set_shared_data('ui_lang',
                                                self.test_list.options.ui_lang)
        logging.info('TEST_LIST:\n%s', self.test_list.__repr__(recursive=True))
        self.state_instance.test_list = self.test_list

        self.init_states()
        self.start_event_server()

        self.update_system_info()

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
            for i in range(100):  # 10 s
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

        self.prespawner = Prespawner()
        self.prespawner.start()

        def state_change_callback(test, state):
            self.event_client.post_event(
                Event(Event.Type.STATE_CHANGE,
                      path=test.path, state=state))
        self.test_list.state_change_callback = state_change_callback

        try:
            tests_after_shutdown = self.state_instance.get_shared_data(
                'tests_after_shutdown')
        except KeyError:
            tests_after_shutdown = None

        if tests_after_shutdown is not None:
            logging.info('Resuming tests after shutdown: %s',
                         tests_after_shutdown)
            self.state_instance.set_shared_data('tests_after_shutdown', None)
            self.tests_to_run.extend(
                self.test_list.lookup_path(t) for t in tests_after_shutdown)
            self.run_queue.put(self.run_next_test)
        else:
            if self.test_list.options.auto_run_on_start:
                self.run_queue.put(
                    lambda: self.run_tests(self.test_list, untested_only=True))

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
        events = []
        if block:
            # Get at least one event
            events.append(self.run_queue.get())
        while True:
            try:
                events.append(self.run_queue.get_nowait())
            except Queue.Empty:
                break

        for event in events:
            if not event:
                # Shutdown request.
                self.run_queue.task_done()
                return False

            try:
                event()
            except Exception as e:  # pylint: disable=W0703
                logging.error('Error in event loop: %s', e)
                traceback.print_exc(sys.stderr)
                self.record_exception(traceback.format_exception_only(
                        *sys.exc_info()[:2]))
                # But keep going
            finally:
                self.run_queue.task_done()
        return True

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
        self.run_tests([])

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
            self.event_client.post_event(
                Event(Event.Type.SET_VISIBLE_TEST, path=test.path))
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
        for k, v in self.invocations.iteritems():
            logging.info('Waiting for %s to complete...', k)
            v.thread.join()

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
    Goofy().main()
