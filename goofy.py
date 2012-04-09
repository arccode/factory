#!/usr/bin/python -u
#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
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
import pickle
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
from collections import deque
from optparse import OptionParser

import factory_common
from autotest_lib.client.bin.prespawner import Prespawner
from autotest_lib.client.cros import factory
from autotest_lib.client.cros.factory import state
from autotest_lib.client.cros.factory import TestState
from autotest_lib.client.cros.factory.event import Event
from autotest_lib.client.cros.factory.event import EventClient
from autotest_lib.client.cros.factory.event import EventServer


SCRIPT_PATH = os.path.realpath(__file__)
CROS_FACTORY_LIB_PATH = os.path.dirname(SCRIPT_PATH)
FACTORY_UI_PATH = os.path.join(CROS_FACTORY_LIB_PATH, 'ui')
CLIENT_PATH = os.path.realpath(os.path.join(CROS_FACTORY_LIB_PATH, '..', '..'))
DEFAULT_TEST_LIST_PATH = os.path.join(
        CLIENT_PATH , 'site_tests', 'suite_Factory', 'test_list')
HWID_CFG_PATH = '/usr/local/share/chromeos-hwid/cfg'

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

# TODO(jsalz): Move utility functions (e.g., is_process_alive,
# kill_process_tree, are_shift_keys_depressed) into a separate
# utilities module.

def is_process_alive(pid):
    '''
    Returns true if the named process is alive and not a zombie.
    '''
    try:
        with open("/proc/%d/stat" % pid) as f:
            return f.readline().split()[2] != 'Z'
    except IOError:
        return False


def kill_process_tree(process, caption):
    '''
    Kills a process and all its subprocesses.

    @param process: The process to kill (opened with the subprocess module).
    @param caption: A caption describing the process.
    '''
    # os.kill does not kill child processes. os.killpg kills all processes
    # sharing same group (and is usually used for killing process tree). But in
    # our case, to preserve PGID for autotest and upstart service, we need to
    # iterate through each level until leaf of the tree.

    def get_all_pids(root):
        ps_output = subprocess.Popen(['ps','--no-headers','-eo','pid,ppid'],
                                     stdout=subprocess.PIPE)
        children = {}
        for line in ps_output.stdout:
            match = re.findall('\d+', line)
            children.setdefault(int(match[1]), []).append(int(match[0]))
        pids = []
        def add_children(pid):
            pids.append(pid)
            map(add_children, children.get(pid, []))
        add_children(root)
        # Reverse the list to first kill children then parents.
        # Note reversed(pids) will return an iterator instead of real list, so
        # we must explicitly call pids.reverse() here.
        pids.reverse()
        return pids

    pids = get_all_pids(process.pid)
    for sig in [signal.SIGTERM, signal.SIGKILL]:
        logging.info('Stopping %s (pid=%s)...', caption, sorted(pids))

        for i in range(25):  # Try 25 times (200 ms between tries)
            for pid in pids:
                try:
                    logging.info("Sending signal %s to %d", sig, pid)
                    os.kill(pid, sig)
                except OSError:
                    pass
            pids = filter(is_process_alive, pids)
            if not pids:
                return
            time.sleep(0.2)  # Sleep 200 ms and try again

    logging.warn('Failed to stop %s process. Ignoring.', caption)


def are_shift_keys_depressed():
    '''Returns True if both shift keys are depressed.'''
    # From #include <linux/input.h>
    KEY_LEFTSHIFT = 42
    KEY_RIGHTSHIFT = 54

    for kbd in glob.glob("/dev/input/by-path/*kbd"):
        try:
            f = os.open(kbd, os.O_RDONLY)
        except OSError as e:
            if factory.in_chroot():
                # That's OK; we're just not root
                continue
            else:
                raise
        buf = array.array('b', [0] * 96)

        # EVIOCGKEY (from #include <linux/input.h>)
        fcntl.ioctl(f, 0x80604518, buf)

        def is_pressed(key):
            return (buf[key / 8] & (1 << (key % 8))) != 0

        if is_pressed(KEY_LEFTSHIFT) and is_pressed(KEY_RIGHTSHIFT):
            return True

    return False


class Environment(object):
    '''
    Abstract base class for external test operations, e.g., run an autotest,
    shutdown, or reboot.

    The Environment is assumed not to be thread-safe: callers must grab the lock
    before calling any methods.  This is primarily necessary because we mock out
    this Environment with mox, and unfortunately mox is not thread-safe.
    TODO(jsalz): Try to write a thread-safe wrapper for mox.
    '''
    lock = threading.Lock()

    def shutdown(self, operation):
        '''
        Shuts the machine down (from a ShutdownStep).

        Args:
            operation: 'reboot' or 'halt'.

        Returns:
            True if Goofy should gracefully exit, or False if Goofy
                should just consider the shutdown to have suceeded (e.g.,
                in the chroot).
        '''
        raise NotImplementedError()


    def spawn_autotest(self, name, args, env_additions, result_file):
        '''
        Spawns a process to run an autotest.

        Args:
            name: Name of the autotest to spawn.
            args: Command-line arguments.
            env_additions: Additions to the environment.
            result_file: Expected location of the result file.
        '''
        raise NotImplementedError()


class DUTEnvironment(Environment):
    '''
    A real environment on a device under test.
    '''
    def shutdown(self, operation):
        assert operation in ['reboot', 'halt']
        logging.info('Shutting down: %s', operation)
        subprocess.check_call('sync')
        subprocess.check_call(operation)
        time.sleep(30)
        assert False, 'Never reached (should %s)' % operation

    def spawn_autotest(self, name, args, env_additions, result_file):
        return self.goofy.prespawner.spawn(args, env_additions)


class ChrootEnvironment(Environment):
    '''
    A chroot environment that doesn't actually shutdown or run autotests.
    '''
    def shutdown(self, operation):
        assert operation in ['reboot', 'halt']
        logging.warn('In chroot: skipping %s', operation)
        return False

    def spawn_autotest(self, name, args, env_additions, result_file):
        logging.warn('In chroot: skipping autotest %s', name)
        # Just mark it as passed
        with open(result_file, 'w') as out:
            pickle.dump((TestState.PASSED, 'Passed'), out)
        # Start a process that will return with a true exit status in
        # 2 seconds (just like a happy autotest).
        return subprocess.Popen(['sleep', '2'])


class TestInvocation(object):
    '''
    State for an active test.
    '''
    def __init__(self, goofy, test, on_completion=None):
        '''Constructor.

        @param goofy: The controlling Goofy object.
        @param test: The FactoryTest object to test.
        @param on_completion: Callback to invoke in the goofy event queue
            on completion.
        '''
        self.goofy = goofy
        self.test = test
        self.thread = threading.Thread(target=self._run,
                                       name='TestInvocation-%s' % test.path)
        self.on_completion = on_completion

        self._lock = threading.Lock()
        # The following properties are guarded by the lock.
        self._aborted = False
        self._completed = False
        self._process = None

    def __repr__(self):
        return 'TestInvocation(_aborted=%s, _completed=%s)' % (
            self._aborted, self._completed)

    def start(self):
        '''Starts the test thread.'''
        self.thread.start()

    def abort_and_join(self):
        '''
        Aborts a test (must be called from the event controller thread).
        '''
        with self._lock:
            self._aborted = True
            if self._process:
                kill_process_tree(self._process, 'autotest')
        if self.thread:
            self.thread.join()
        with self._lock:
            # Should be set by the thread itself, but just in case...
            self._completed = True

    def is_completed(self):
        '''
        Returns true if the test has finished.
        '''
        with self._lock:
            return self._completed

    def _invoke_autotest(self, test, dargs):
        '''
        Invokes an autotest test.

        This method encapsulates all the magic necessary to run a single
        autotest test using the 'autotest' command-line tool and get a
        sane pass/fail status and error message out.  It may be better
        to just write our own command-line wrapper for job.run_test
        instead.

        @param test: the autotest to run
        @param dargs: the argument map
        @return: tuple of status (TestState.PASSED or TestState.FAILED) and
            error message, if any
        '''
        status = TestState.FAILED
        error_msg = 'Unknown'

        try:
            client_dir = CLIENT_PATH

            output_dir = '%s/results/%s' % (client_dir, test.path)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            tmp_dir = tempfile.mkdtemp(prefix='tmp', dir=output_dir)

            control_file = os.path.join(tmp_dir, 'control')
            result_file = os.path.join(tmp_dir, 'result')
            args_file = os.path.join(tmp_dir, 'args')

            with open(args_file, 'w') as f:
                pickle.dump(dargs, f)

            # Create a new control file to use to run the test
            with open(control_file, 'w') as f:
                print >> f, 'import common, traceback, utils'
                print >> f, 'import cPickle as pickle'
                print >> f, ("success = job.run_test("
                            "'%s', **pickle.load(open('%s')))" % (
                    test.autotest_name, args_file))

                print >> f, (
                    "pickle.dump((success, "
                    "str(job.last_error) if job.last_error else None), "
                    "open('%s', 'w'), protocol=2)"
                    % result_file)

            args = ['%s/bin/autotest' % client_dir,
                    '--output_dir', output_dir,
                    control_file]

            factory.console.info('Running test %s' % test.path)
            logging.debug('Test command line: %s', ' '.join(
                    [pipes.quote(arg) for arg in args]))

            with self._lock:
                with self.goofy.env.lock:
                    self._process = self.goofy.env.spawn_autotest(
                        test.autotest_name, args,
                        {'CROS_FACTORY_TEST_PATH': test.path}, result_file)

            returncode = self._process.wait()
            with self._lock:
                if self._aborted:
                    error_msg = 'Aborted by operator'
                    return

            if returncode:
                # Only happens when there is an autotest-level problem (not when
                # the test actually failed).
                error_msg = 'autotest returned with code %d' % returncode
                return

            with open(result_file) as f:
                try:
                    success, error_msg = pickle.load(f)
                except:  # pylint: disable=W0702
                    logging.exception('Unable to retrieve autotest results')
                    error_msg = 'Unable to retrieve autotest results'
                    return

            if success:
                status = TestState.PASSED
                error_msg = ''
        except Exception:  # pylint: disable=W0703
            traceback.print_exc(sys.stderr)
            # Make sure Goofy reports the exception upon destruction
            # (e.g., for testing)
            self.goofy.record_exception(traceback.format_exception_only(
                    *sys.exc_info()[:2]))
        finally:
            factory.console.info('Test %s: %s' % (test.path, status))
            return status, error_msg  # pylint: disable=W0150

    def _run(self):
        with self._lock:
            if self._aborted:
                return

        count = self.test.update_state(
            status=TestState.ACTIVE, increment_count=1, error_msg='').count

        test_tag = '%s_%s' % (self.test.path, count)
        dargs = dict(self.test.dargs)
        dargs.update({'tag': test_tag,
                      'test_list_path': self.goofy.options.test_list})

        status, error_msg = self._invoke_autotest(self.test, dargs)
        self.test.update_state(status=status, error_msg=error_msg,
                               visible=False)
        with self._lock:
            self._completed = True

        self.goofy.run_queue.put(self.goofy.reap_completed_tests)
        if self.on_completion:
            self.goofy.run_queue.put(self.on_completion)


_inited_logging = False

class Goofy(object):
    '''
    The main factory flow.

    Note that all methods in this class must be invoked from the main
    (event) thread.  Other threads, such as callbacks and TestInvocation
    methods, should instead post events on the run queue.

    TODO: Unit tests. (chrome-os-partner:7409)

    Properties:
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
        self.state_instance = None
        self.state_server = None
        self.state_server_thread = None
        self.event_server = None
        self.event_server_thread = None
        self.event_client = None
        self.prespawner = None
        self.ui_process = None
        self.run_queue = Queue.Queue()
        self.invocations = {}
        self.tests_to_run = deque()
        self.visible_test = None

        self.options = None
        self.args = None
        self.test_list = None

        self.event_handlers = {
            Event.Type.SWITCH_TEST: self.handle_switch_test,
            Event.Type.SHOW_NEXT_ACTIVE_TEST:
                lambda event: self.show_next_active_test(),
            Event.Type.RESTART_TESTS:
                lambda event: self.restart_tests(),
            Event.Type.AUTO_RUN:
                lambda event: self.auto_run(),
            Event.Type.RE_RUN_FAILED:
                lambda event: self.re_run_failed(),
            Event.Type.REVIEW:
                lambda event: self.show_review_information(),
        }

        self.exceptions = []

    def destroy(self):
        if self.ui_process:
            kill_process_tree(self.ui_process, 'ui')
            self.ui_process = None
        if self.state_server_thread:
            logging.info('Stopping state server')
            self.state_server.shutdown()
            self.state_server_thread.join()
            self.state_server.server_close()
            self.state_server_thread = None
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
            self.event_client.close()
        self.check_exceptions()

    def start_state_server(self):
        self.state_instance, self.state_server = state.create_server()
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

    def start_ui(self):
        ui_proc_args = [FACTORY_UI_PATH, self.options.test_list]
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
        elif are_shift_keys_depressed():
            logging.info('Shift keys are depressed; cancelling restarts')
            # Abort shutdown
            test.update_state(
                status=TestState.FAILED,
                error_msg='Shutdown aborted with double shift keys')
        else:
            # Need to shutdown again
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
                test.update_state(status=TestState.ACTIVE, increment_count=1,
                                  error_msg='', shutdown_count=0)
                # Save pending test list in the state server
                self.state_instance.set_shared_data(
                    'tests_after_shutdown',
                    [t.path for t in self.tests_to_run])

                with self.env.lock:
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

    def abort_active_tests(self):
        self.kill_active_tests(True)

    def main(self):
        self.init()
        self.run()

    def init(self, args=None, env=None):
        '''Initializes Goofy.

        Args:
            args: A list of command-line arguments.  Uses sys.argv if
                args is None.
            env: An Environment instance to use (or None to choose
                ChrootEnvironment or DUTEnvironment as appropriate).
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
        parser.add_option('--noui', dest='ui',
                          action='store_false', default=True,
                          help='Disable the UI')
        parser.add_option('--test_list', dest='test_list',
                          metavar='FILE',
                          help='Use FILE as test list')
        (self.options, self.args) = parser.parse_args(args)

        global _inited_logging
        if not _inited_logging:
            factory.init_logging('goofy', verbose=self.options.verbose)
            _inited_logging = True

        if (not suppress_chroot_warning and
            factory.in_chroot() and
            os.environ.get('DISPLAY') in [None, '', ':0', ':0.0']):
            # That's not going to work!  Tell the user how to run
            # this way.
            logging.warn(GOOFY_IN_CHROOT_WARNING)
            time.sleep(1)

        if env:
            self.env = env
        elif factory.in_chroot():
            self.env = ChrootEnvironment()
            logging.warn(
                'Using chroot environment: will not actually run autotests')
        else:
            self.env = DUTEnvironment()
        self.env.goofy = self

        if self.options.restart:
            state.clear_state()

        if self.options.print_test_list:
            print (factory.read_test_list(self.options.print_test_list).
                   __repr__(recursive=True))
            return

        logging.info('Started')

        self.start_state_server()
        # Update HWID configuration tag.
        self.state_instance.set_shared_data('hwid_cfg', get_hwid_cfg())

        self.options.test_list = (self.options.test_list or find_test_list())
        self.test_list = factory.read_test_list(self.options.test_list,
                                                self.state_instance)
        logging.info('TEST_LIST:\n%s', self.test_list.__repr__(recursive=True))

        self.init_states()
        self.start_event_server()
        if self.options.ui:
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

    def run_tests_with_status(self, statuses_to_run, starting_at=None):
        '''Runs all top-level tests with a particular status.

        All active tests, plus any tests to re-run, are reset.

        Args:
            starting_at: If provided, only auto-runs tests beginning with
                this test.
        '''
        if starting_at:
            # Make sure they passed a test, not a string.
            assert isinstance(starting_at, factory.FactoryTest)

        tests_to_reset = []
        tests_to_run = []

        found_starting_at = False

        for test in self.test_list.get_top_level_tests():
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

    def restart_tests(self):
        '''Restarts all tests.'''
        self.abort_active_tests()
        for test in self.test_list.walk():
            test.update_state(status=TestState.UNTESTED)
        self.run_tests(self.test_list)

    def auto_run(self, starting_at=None):
        '''"Auto-runs" tests that have not been run yet.

        Args:
            starting_at: If provide, only auto-runs tests beginning with
                this test.
        '''
        self.run_tests_with_status([TestState.UNTESTED, TestState.ACTIVE],
                                   starting_at=starting_at)

    def re_run_failed(self):
        '''Re-runs failed tests.'''
        self.run_tests_with_status([TestState.FAILED])

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
