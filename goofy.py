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

import logging, os, pickle, pipes, re, signal, subprocess, sys, tempfile
import threading, time, traceback
from collections import deque
from optparse import OptionParser
from Queue import Queue

import factory_common
from autotest_lib.client.bin import prespawner
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
        self.thread = threading.Thread(target=self._run)
        self.on_completion = on_completion

        self._lock = threading.Lock()
        # The following properties are guarded by the lock.
        self._aborted = False
        self._completed = False
        self._process = None

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
                self._process = prespawner.spawn(
                    args, {'CROS_FACTORY_TEST_PATH': test.path})

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
                      'test_list_path': self.goofy.test_list_path})

        status, error_msg = self._invoke_autotest(self.test, dargs)
        self.test.update_state(status=status, error_msg=error_msg,
                               visible=False)
        with self._lock:
            self._completed = True
        self.goofy.run_queue.put(self.goofy.reap_completed_tests)
        self.goofy.run_queue.put(self.on_completion)


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
        test_list_path: The path to the test list.
        test_list: The test list.
    '''
    def __init__(self):
        self.state_instance = None
        self.state_server = None
        self.state_server_thread = None
        self.event_server = None
        self.event_server_thread = None
        self.event_client = None
        self.ui_process = None
        self.run_queue = Queue()
        self.invocations = {}
        self.tests_to_run = deque()
        self.visible_test = None

        self.options = None
        self.args = None
        self.test_list_path = None
        self.test_list = None

    def __del__(self):
        if self.ui_process:
            kill_process_tree(self.ui_process, 'ui')
        if self.state_server_thread:
            logging.info('Stopping state server')
            self.state_server.shutdown()
            self.state_server_thread.join()
        if self.event_server_thread:
            logging.info('Stopping event server')
            self.event_server.shutdown()  # pylint: disable=E1101
            self.event_server_thread.join()
        prespawner.stop()

    def start_state_server(self):
        self.state_instance, self.state_server = state.create_server()
        logging.info('Starting state server')
        self.state_server_thread = threading.Thread(
            target=self.state_server.serve_forever)
        self.state_server_thread.start()

    def start_event_server(self):
        self.event_server = EventServer()
        logging.info('Starting factory event server')
        self.event_server_thread = threading.Thread(
            target=self.event_server.serve_forever)  # pylint: disable=E1101
        self.event_server_thread.start()

        self.event_client = EventClient(
            callback=self.handle_event, event_loop=self.run_queue)

    def start_ui(self):
        ui_proc_args = [FACTORY_UI_PATH, self.test_list_path]
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

    def handle_reboot_complete(self, test, state):
        '''
        Handles the case where a reboot was detected during a reboot step.

        @param test: The RebootStep.
        @param state: The test state.
        '''
        state = test.update_state(increment_reboot_count=1)
        logging.info('Detected reboot (%d of %d)',
                     state.reboot_count, test.iterations)
        if state.reboot_count == test.iterations:
            # Good!
            test.update_state(status=TestState.PASSED, error_msg='')
        elif state.reboot_count > test.iterations:
            # Rebooted too many times
            test.update_state(status=TestState.FAILED,
                              error_msg='Too many reboots')
        else:
            # Need to reboot again
            self.reboot()

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
            if isinstance(test, factory.InformationScreen):
                test.update_state(status=TestState.UNTESTED, error_msg='')
            elif state.status == TestState.ACTIVE:
                if isinstance(test, factory.RebootStep):
                    # Rebooted while the test was active - that's good.
                    self.handle_reboot_complete(test, state)
                else:
                    test.update_state(status=TestState.FAILED,
                                      error_msg='Unknown (reboot?)')

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
        if event.type == 'kbd_shortcut':
            if event.key == 'Tab':
                self.show_next_active_test()
            test = self.test_list.kbd_shortcut_map.get(event.key)
            if test:
                invoc = self.invocations.get(test)
                if invoc and test.backgroundable:
                    # Already running: just bring to the front if it
                    # has a UI.
                    logging.info('Setting visible test to %s', test.path)
                    self.event_client.post_event(
                        Event(Event.Type.SET_VISIBLE_TEST,
                              path=test.path))

                self.abort_active_tests()
                for t in test.walk():
                    t.update_state(status=TestState.UNTESTED)
                self.run_tests(test)

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

            if isinstance(test, factory.RebootStep):
                test.update_state(status=TestState.ACTIVE, increment_count=1,
                                  error_msg='', reboot_count=0)
                # Save pending test list in the state server
                self.state_instance.set_shared_data(
                    'tests_after_reboot',
                    [t.path for t in self.tests_to_run])
                self.reboot()

            invoc = TestInvocation(self, test, on_completion=self.run_next_test)
            self.invocations[test] = invoc
            if self.visible_test is None and test.has_ui:
                self.set_visible_test(test)
            invoc.start()

    def run_tests(self, root, untested_only=False):
        '''
        Runs tests under root.

        The tests are run in order unless one fails (then stops).
        Backgroundable tests are run simultaneously; when a foreground test is
        encountered, we wait for all active tests to finish before continuing.
        '''
        self.tests_to_run = deque()
        for x in root.walk():
            if not x.is_leaf():
                continue
            if untested_only and x.get_state().status != TestState.UNTESTED:
                continue
            self.tests_to_run.append(x)
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

    def abort_active_tests(self):
        '''
        Kills and waits for all active tests.
        '''
        self.reap_completed_tests()
        for test, invoc in self.invocations.items():
            factory.console.info('Killing active test %s...' % test.path)
            invoc.abort_and_join()
            factory.console.info('Killed %s' % test.path)
            del self.invocations[test]
        self.reap_completed_tests()

    def reboot(self):
        '''
        Reboots the machine (from a RebootTest).
        '''
        logging.info('Rebooting')
        subprocess.check_call('sync')
        subprocess.check_call('reboot')
        time.sleep(30)
        assert False, 'Never reached (should reboot)'

    def main(self):
        parser = OptionParser()
        parser.add_option('-v', '--verbose', dest='verbose',
                          action='store_true',
                          help='Enable debug logging')
        parser.add_option('--print_test_list', dest='print_test_list',
                          metavar='FILE',
                          help='Read and print test list FILE, and exit')
        (self.options, self.args) = parser.parse_args()

        factory.init_logging('goofy', verbose=self.options.verbose)

        if self.options.print_test_list:
            print (factory.read_test_list(self.options.print_test_list).
                   __repr__(recursive=True))
            return

        logging.info('Started')

        self.start_state_server()
        # Update HWID configuration tag.
        self.state_instance.set_shared_data('hwid_cfg', get_hwid_cfg())

        self.test_list_path = find_test_list()
        self.test_list = factory.read_test_list(self.test_list_path,
                                                self.state_instance)
        logging.info('TEST_LIST:\n%s', self.test_list.__repr__(recursive=True))

        self.init_states()
        self.start_event_server()
        self.start_ui()
        prespawner.start()

        def state_change_callback(test, state):
            self.event_client.post_event(
                Event(Event.Type.STATE_CHANGE,
                      path=test.path, state=state))
        self.test_list.state_change_callback = state_change_callback

        try:
            tests_after_reboot = self.state_instance.get_shared_data(
                'tests_after_reboot')
        except KeyError:
            tests_after_reboot = None

        if tests_after_reboot is not None:
            logging.info('Resuming tests after reboot: %s', tests_after_reboot)
            self.state_instance.set_shared_data('tests_after_reboot', None)
            self.tests_to_run.extend(
                self.test_list.lookup_path(t) for t in tests_after_reboot)
            self.run_next_test()
        else:
            self.run_tests(self.test_list, untested_only=True)

        # Process events forever.
        while True:
            event = self.run_queue.get()
            if not event:
                # Shutdown request (although this currently never happens).
                self.run_queue.task_done()
                break

            try:
                event()
            except Exception as e:  # pylint: disable=W0703
                logging.error('Error in event loop: %s', e)
                traceback.print_exc(sys.stderr)
                # But keep going
            finally:
                self.run_queue.task_done()


if __name__ == '__main__':
    Goofy().main()
