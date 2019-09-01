#!/usr/bin/env python2
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Runs unittests in parallel."""

import argparse
import logging
import os
import random
import shutil
import signal
import SocketServer
import struct
from subprocess import STDOUT
import sys
import tempfile
import threading
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.utils.debug_utils import SetupLogging
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils

TEST_PASSED_MARK = '.tests-passed'
KILL_OLD_TESTS_TIMEOUT_SECS = 2
TEST_RUNNER_ENV_VAR = 'CROS_FACTORY_TEST_RUNNER'

# Timeout for running any individual test program.
TEST_TIMEOUT_SECS = 60


def _MaybeSkipTest(tests, isolated_tests):
  """Filters tests according to changed file.

  Args:
    tests: unittest paths.
    isolated_tests: isolated unittest paths.

  Returns:
    A tuple (filtered_tests, filtered_isolated_tests) containing filtered
    tests and isolated tests.
  """
  if not os.path.exists(TEST_PASSED_MARK):
    return (tests, isolated_tests)

  ls_tree = process_utils.CheckOutput(
      ['git', 'ls-tree', '-r', 'HEAD']).split('\n')
  files = [line.split()[3] for line in ls_tree if line]
  last_test_time = os.path.getmtime(TEST_PASSED_MARK)

  try:
    # We can't use os.path.getmtime here, because we don't want it to follow
    # symlink (for example, py_pkg/cros/factory, py/testlog/utils), and those
    # directories would appear changed since we clear all .pyc before running
    # this.
    changed_files = [f for f in files if os.lstat(f).st_mtime > last_test_time]
  except OSError:
    # E.g., file renamed; just run everything
    return (tests, isolated_tests)

  if not changed_files:
    # Nothing to test!
    return ([], [])

  return (tests, isolated_tests)


class _TestProc(object):
  """Creates and runs a subprocess to run an unittest.

  Besides creating a subprocess, it also prepares a temp directory for
  env CROS_FACTORY_DATA_DIR, records a test start time and test path.

  The temp directory will be removed once the object is destroyed.

  Args:
    test_name: unittest path.
    log_name: path of log file for unittest.
  """

  def __init__(self, test_name, log_name, port_server):
    self.test_name = test_name
    self.log_file = open(log_name, 'w')
    self.start_time = time.time()
    self.cros_factory_data_dir = tempfile.mkdtemp(
        prefix='cros_factory_data_dir.')
    self.child_tmp_root = os.path.join(self.cros_factory_data_dir, 'tmp')
    os.mkdir(self.child_tmp_root)
    child_env = os.environ.copy()
    child_env['CROS_FACTORY_DATA_DIR'] = self.cros_factory_data_dir
    # Set TEST_RUNNER_ENV_VAR so we know to kill it later if
    # re-running tests.
    child_env[TEST_RUNNER_ENV_VAR] = os.path.basename(__file__)
    # Set SPT_NOENV so that setproctitle doesn't mess up with /proc/PID/environ,
    # and we can kill old tests correctly.
    child_env['SPT_NOENV'] = '1'
    # Since some tests using `make par` is sensitive to file changes inside py
    # directory, don't generate .pyc file.
    child_env['PYTHONDONTWRITEBYTECODE'] = '1'
    # Change child calls for tempfile.* to be rooted at directory inside
    # cros_factory_data_dir temporary directory, so it would be removed even if
    # the test is terminated.
    child_env['TMPDIR'] = self.child_tmp_root
    # This is used by net_utils.FindUnusedPort, to eliminate the chance of
    # collision of FindUnusedPort between different unittests.
    child_env['CROS_FACTORY_UNITTEST_PORT_DISTRIBUTE_SERVER'] = port_server
    self.proc = process_utils.Spawn(self.test_name, stdout=self.log_file,
                                    stderr=STDOUT, env=child_env)
    self.pid = self.proc.pid

    process_utils.StartDaemonThread(target=self._WatchTest)
    self.returncode = None

  def _WatchTest(self):
    """Watches a test, killing it if it times out."""
    while True:
      time.sleep(1)
      if self.returncode is not None:
        # Test complete!
        return
      if time.time() > self.start_time + TEST_TIMEOUT_SECS:
        break  # Timeout

    logging.error('Test %s still alive after %d secs: killing it',
                  self.test_name, TEST_TIMEOUT_SECS)
    try:
      os.kill(self.proc.pid, signal.SIGKILL)
    except OSError:
      # E.g., it went away... no big deal
      logging.exception('Unable to kill %s', self.test_name)
    return

  def Close(self):
    if os.path.isdir(self.cros_factory_data_dir):
      shutil.rmtree(self.cros_factory_data_dir)


class PortDistributeHandler(SocketServer.StreamRequestHandler):
  def handle(self):
    length = struct.unpack('B', self.rfile.read(1))[0]
    port = self.server.RequestPort(length)
    self.wfile.write(struct.pack('<H', port))


class PortDistributeServer(SocketServer.ThreadingUnixStreamServer):
  def __init__(self):
    self.lock = threading.RLock()
    self.unused_ports = set(
        xrange(net_utils.UNUSED_PORT_LOW, net_utils.UNUSED_PORT_HIGH))
    self.socket_file = tempfile.mktemp(prefix='random_port_socket')
    self.thread = None
    SocketServer.ThreadingUnixStreamServer.__init__(self, self.socket_file,
                                                    PortDistributeHandler)

  def Start(self):
    self.thread = threading.Thread(target=self.serve_forever)
    self.thread.start()

  def Close(self):
    self.server_close()
    if self.thread:
      net_utils.ShutdownTCPServer(self)
      self.thread.join()
    if self.socket_file and os.path.exists(self.socket_file):
      os.unlink(self.socket_file)

  def RequestPort(self, length):
    with self.lock:
      while True:
        port = random.randint(net_utils.UNUSED_PORT_LOW,
                              net_utils.UNUSED_PORT_HIGH - length)
        port_range = xrange(port, port + length)
        if self.unused_ports.issuperset(port_range):
          self.unused_ports.difference_update(port_range)
          break
      return port


class RunTests(object):
  """Runs unittests in parallel.

  Args:
    tests: list of unittest paths.
    max_jobs: maxinum number of parallel tests to run.
    log_dir: base directory to store test logs.
    isolated_tests: list of test to run in isolate mode.
    fallback: True to re-run failed test sequentially.
  """

  def __init__(self, tests, max_jobs, log_dir, isolated_tests=None,
               fallback=True):
    self._tests = tests if tests else []
    self._max_jobs = max_jobs
    self._log_dir = log_dir
    self._isolated_tests = isolated_tests if isolated_tests else []
    self._fallback = fallback
    self._start_time = time.time()

    # A dict to store running subprocesses. pid: (_TestProc, test_name).
    self._running_proc = {}
    self._abort_event = threading.Event()

    self._passed_tests = set()  # set of passed test_name
    self._failed_tests = {}  # dict of failed test name -> log file

    self._run_counts = {}  # dict of test name -> number of runs so far

    def AbortHandler(sig, frame):
      del sig, frame  # Unused.
      if self._abort_event.isSet():
        # Ignore cleanup and force exit if ctrl-c is pressed twice
        print '\033[22;31mGot ctrl-c twice, force shutdown!\033[22;0m'
        raise KeyboardInterrupt
      print '\033[1;33mGot ctrl-c, gracefully shutdown.\033[22;0m'
      self._abort_event.set()

    signal.signal(signal.SIGINT, AbortHandler)

  def Run(self):
    """Runs all unittests.

    Returns:
      0 if all passed; otherwise, 1.
    """
    if self._max_jobs > 1:
      tests = set(self._tests) - set(self._isolated_tests)
      num_total_tests = len(tests) + len(self._isolated_tests)
      self._InfoMessage('Run %d tests in parallel with %d jobs:' %
                        (len(tests), self._max_jobs))
    else:
      tests = set(self._tests) | set(self._isolated_tests)
      num_total_tests = len(tests)
      self._InfoMessage('Run %d tests sequentially:' % len(tests))

    self._RunInParallel(tests, self._max_jobs)
    if self._max_jobs > 1 and self._isolated_tests:
      self._InfoMessage('Run %d isolated tests sequentially:' %
                        len(self._isolated_tests))
      self._RunInParallel(self._isolated_tests, 1)

    self._PassMessage('%d/%d tests passed.' % (len(self._passed_tests),
                                               num_total_tests))

    if self._failed_tests and self._fallback:
      self._InfoMessage('Re-run failed tests sequentially:')
      rerun_tests = sorted(self._failed_tests.keys())
      self._failed_tests.clear()
      self._RunInParallel(rerun_tests, 1)
      self._PassMessage('%d/%d tests passed.' % (len(self._passed_tests),
                                                 len(self._tests)))

    self._InfoMessage('Elapsed time: %.2f s' % (time.time() - self._start_time))

    if self._failed_tests:
      self._FailMessage('Logs of %d failed tests:' % len(self._failed_tests))
      # Log all the values in the dict (i.e., the log file paths)
      for test in sorted(self._failed_tests.values()):
        self._FailMessage(test)
      return 1
    else:
      return 0

  def _GetLogFilename(self, test_path):
    """Composes log filename.

    Log filename is based on unittest path.  We replace '/' with '_' and
    add the run number (1-relative).

    Args:
      test_path: unittest path.

    Returns:
      log filename (with path) for the test.
    """
    if test_path.find('./') == 0:
      test_path = test_path[2:]

    run_count = self._run_counts[test_path] = self._run_counts.get(
        test_path, 0) + 1

    return os.path.join(
        self._log_dir,
        '%s.%d.log' % (test_path.replace('/', '_'), run_count))

  def _RunInParallel(self, tests, max_jobs):
    """Runs tests in parallel.

    It creates subprocesses and runs in parallel for at most max_jobs.
    It is blocked until all tests are done.

    Args:
      tests: list of unittest paths.
      max_jobs: maximum number of tests to run in parallel.
    """
    port_server = PortDistributeServer()
    port_server.Start()
    try:
      for test_name in tests:
        try:
          p = _TestProc(test_name,
                        self._GetLogFilename(test_name),
                        port_server.socket_file)
        except Exception:
          self._FailMessage('Error running test %r' % test_name)
          raise
        self._running_proc[p.pid] = (p, os.path.basename(test_name))
        self._WaitRunningProcessesFewerThan(max_jobs)
      # Wait for all running test.
      self._WaitRunningProcessesFewerThan(1)
    finally:
      port_server.Close()

  def _RecordTestResult(self, p):
    """Records test result.

    Places the completed test to either success or failure list based on
    its returncode. Also print out PASS/FAIL message with elapsed time.

    Args:
      p: _TestProc object.
    """
    duration = time.time() - p.start_time
    if p.returncode == 0:
      self._PassMessage('*** PASS [%.2f s] %s' % (duration, p.test_name))
      self._passed_tests.add(p.test_name)
    else:
      self._FailMessage('*** FAIL [%.2f s] %s (return:%d)' %
                        (duration, p.test_name, p.returncode))
      self._failed_tests[p.test_name] = p.log_file.name

  def _TerminateAndCleanupAll(self):
    """Terminate all running process and cleanup temporary directories.

    Doing terminate gracefully by sending SIGINT to all process first, wait for
    1 second, and then send SIGKILL to process that is still alive.
    """
    for pid in self._running_proc:
      os.kill(pid, signal.SIGINT)
    time.sleep(1)
    for pid, (proc, unused_test_name) in self._running_proc.iteritems():
      if os.waitpid(pid, os.WNOHANG)[0] == 0:
        # Test still alive, kill with SIGKILL
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
      proc.Close()
    raise KeyboardInterrupt

  def _WaitRunningProcessesFewerThan(self, threshold):
    """Waits until #running processes is fewer than specifed.

    It is a blocking call. If #running processes >= thresold, it waits for a
    completion of a child.

    Args:
      threshold: if #running process is fewer than this, the call returns.
    """
    while len(self._running_proc) >= threshold:
      if self._abort_event.isSet():
        # Ctrl-c got, cleanup and exit.
        self._TerminateAndCleanupAll()

      pid, status = os.waitpid(-1, os.WNOHANG)
      if pid != 0:
        p = self._running_proc.pop(pid)[0]
        p.returncode = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
        p.Close()
        self._RecordTestResult(p)
        self._ShowRunningTest()
      else:
        self._abort_event.wait(0.05)

  def _PassMessage(self, message):
    self._ClearLine()
    print '\033[22;32m%s\033[22;0m' % message

  def _FailMessage(self, message):
    self._ClearLine()
    print '\033[22;31m%s\033[22;0m' % message

  def _InfoMessage(self, message):
    self._ClearLine()
    print message

  def _ClearLine(self):
    sys.stderr.write('\r\033[K')

  def _ShowRunningTest(self):
    if not self._running_proc:
      return
    status = '-> %d tests running' % len(self._running_proc)
    running_tests = ', '.join([p[1] for p in self._running_proc.itervalues()])
    if len(status) + 3 + len(running_tests) > 80:
      running_tests = running_tests[:80 - len(status) - 6] + '...'
    sys.stderr.write('%s [%s]' %
                     (status, running_tests))
    sys.stderr.flush()


def KillOldTests():
  """Kills stale test processes.

  Looks for processes that have CROS_FACTORY_TEST_RUNNER=run_tests.py in
  their environment, mercilessly kills them, and waits for them
  to die.  If it can't kill all the processes within
  KILL_OLD_TESTS_TIMEOUT_SECS, returns anyway.
  """
  env_signature = '%s=%s' % (TEST_RUNNER_ENV_VAR, os.path.basename(__file__))

  pids_to_kill = []
  user_id = (os.environ.get('USER') or
             process_utils.CheckOutput(['id', '-un']).strip())
  for pid in process_utils.CheckOutput(['pgrep', '-U', user_id]).splitlines():
    pid = int(pid)
    try:
      environ = file_utils.ReadFile('/proc/%d/environ' % pid)
    except IOError:
      # No worries, maybe the process already disappeared
      continue

    if env_signature in environ.split('\0'):
      pids_to_kill.append(pid)

  if not pids_to_kill:
    return

  logging.warning('Killing stale test processes %s', pids_to_kill)
  for pid in pids_to_kill:
    try:
      os.kill(pid, signal.SIGKILL)
    except OSError:
      if os.path.exists('/proc/%d' % pid):
        # It's still there.  We should have been able to kill it!
        logging.exception('Unable to kill stale test process %s', pid)

  start_time = time.time()
  while True:
    pids_to_kill = [pid for pid in pids_to_kill
                    if os.path.exists('/proc/%d' % pid)]
    if not pids_to_kill:
      logging.warning('Killed all stale test processes')
      return

    if time.time() - start_time > KILL_OLD_TESTS_TIMEOUT_SECS:
      logging.warning('Unable to kill %s', pids_to_kill)
      return

    time.sleep(0.1)


def main():
  parser = argparse.ArgumentParser(description='Runs unittests in parallel.')
  parser.add_argument('--jobs', '-j', type=int, default=1,
                      help='Maximum number of tests to run in parallel.')
  parser.add_argument('--log', '-l', default='',
                      help='directory to place logs.')
  parser.add_argument('--isolated', '-i', nargs='*', default=[],
                      help='Isolated unittests which run sequentially.')
  parser.add_argument('--nofallback', action='store_true',
                      help='Do not re-run failed test sequentially.')
  parser.add_argument('--nofilter', action='store_true',
                      help='Do not filter tests.')
  parser.add_argument('--no-kill-old', action='store_false', dest='kill_old',
                      help='Do not kill old tests.')
  parser.add_argument('test', nargs='+', help='Unittest filename.')
  args = parser.parse_args()

  SetupLogging()

  test, isolated = ((args.test, args.isolated)
                    if args.nofilter
                    else _MaybeSkipTest(args.test, args.isolated))

  if os.path.exists(TEST_PASSED_MARK):
    os.remove(TEST_PASSED_MARK)

  if args.kill_old:
    KillOldTests()

  runner = RunTests(test, args.jobs, args.log,
                    isolated_tests=isolated, fallback=not args.nofallback)
  return_value = runner.Run()
  if return_value == 0:
    with open(TEST_PASSED_MARK, 'a'):
      os.utime(TEST_PASSED_MARK, None)
  sys.exit(return_value)

if __name__ == '__main__':
  main()
