#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Classes and Methods related to invoking a pytest or autotest."""

import copy
import fnmatch
import logging
import os
import cPickle as pickle
import pipes
import re
import signal
import syslog
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
import unittest
import yaml
from optparse import OptionParser
from setproctitle import setproctitle

import factory_common  # pylint: disable=W0611
from cros.factory import event_log
from cros.factory.privacy import FilterDict
from cros.factory.system.service_manager import ServiceManager
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import utils
from cros.factory.test.args import Args
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.event import Event
from cros.factory.test.factory import TestState
from cros.factory.test.test_lists.test_lists import BuildAllTestLists
from cros.factory.test.test_lists.test_lists import OldStyleTestList
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.string_utils import DecodeUTF8


# Number of bytes to include from the log of a failed test.
ERROR_LOG_TAIL_LENGTH = 8*1024

# pylint: disable=W0702

# A file that stores override test list dargs for factory test automation.
OVERRIDE_TEST_LIST_DARGS_FILE = os.path.join(
    factory.get_state_root(), 'override_test_list_dargs.yaml')


class InvocationError(Exception):
  """Invocation error."""
  pass


class TestArgEnv(object):
  """Environment for resolving test arguments.

  Properties:
    state: Instance to obtain factory test.
    device_data: Cached device data from shopfloor.
  """
  def __init__(self):
    self.state = factory.get_state_instance()
    self.device_data = None

  def GetMACAddress(self, interface):
    return open('/sys/class/net/%s/address' % interface).read().strip()

  def GetDeviceData(self):
    """Returns shopfloor.GetDeviceData().

    The value is cached to avoid extra calls to GetDeviceData().
    """
    if self.device_data is None:
      self.device_data = shopfloor.GetDeviceData()
    return self.device_data

  def InEngineeringMode(self):
    """Returns if goofy is in engineering mode."""
    return factory.get_shared_data('engineering_mode')


def ResolveTestArgs(dargs):
  """Resolves an argument dictionary by evaluating any functions.

  For instance, in a test list:

    OperatorTest(
      ...
      dargs={
          'method': 'Foo',
          'args': lambda env: [
              env.state.get_shared_data('mlb_serial_number'),
              env.shopfloor.get_serial_number(),
              env.GetMACAddress('wlan0'),
          ]
      })

  This will be resolved to something like this before the test is run:

    OperatorTest(
      ...
      dargs={
          'method': 'Foo',
          'args': ['MLB12345', 'X67890', '00:11:22:33:44:55']
      })

  Args:
    dargs: An test argument dictionary from the test list.

  Returns:
    dargs, except that any values that are lambdas are replaced with the
      results of evaluating them with a single argument, 'env',
      which is an instance of the TestArgEnv class.
  """
  def ResolveArg(k, v):
    """Resolves a single argument."""
    if not isinstance(v, types.FunctionType):
      return v

    v = v(TestArgEnv())
    logging.info('Resolved argument %s to %r', k, FilterDict(v))
    return v

  return dict((k, ResolveArg(k, v)) for k, v in dargs.iteritems())


class PyTestInfo(object):
  """A class to hold all the data needed when invoking a test.

  Properties:
    test_list: The test list name or ID to get the factory test info from.
    path: The path of the test in the test list.
    pytest_name: The name of the factory test to run.
    args: Arguments passing down to the factory test.
    results_path: The path to the result file.
    test_case_id: The ID of the test case to run.
    automation_mode: The enabled automation mode.
  """

  # A special test case ID to tell RunPytest to run the pytest directly instead
  # of invoking it in a subprocess.
  NO_SUBPROCESS = '__NO_SUBPROCESS__'

  def __init__(self, test_list, path, pytest_name, args, results_path,
               test_case_id=None, automation_mode=None):
    self.test_list = test_list
    self.path = path
    self.pytest_name = pytest_name
    self.args = args
    self.results_path = results_path
    self.test_case_id = test_case_id
    self.automation_mode = automation_mode

  def ReadTestList(self):
    """Reads and returns the test list."""
    if os.sep in self.test_list:
      # It's a path pointing to an old-style test list; use it.
      return factory.read_test_list(self.test_list)
    else:
      all_test_lists = BuildAllTestLists(
          force_generic=(self.automation_mode is not None))
      test_list = all_test_lists[self.test_list]
      if isinstance(test_list, OldStyleTestList):
        return test_list.Load()
      else:
        return test_list


class TestInvocation(object):
  """State for an active test.

  Properties:
    update_state_on_completion: State for Goofy to update on
      completion; Goofy will call test.update_state(
      **update_state_on_completion).  So update_state_on_completion
      will have at least status and error_msg properties to update
      the test state.
    aborted_reason: A reason that the test was aborted (e.g.,
      'Stopped by operator' or 'Factory update')
  """
  def __init__(self, goofy, test, on_completion=None):
    """Constructor.

    Args:
      goofy: The controlling Goofy object.
      test: The FactoryTest object to test.
      on_completion: Callback to invoke in the goofy event queue
        on completion.
    """
    self.goofy = goofy
    self.test = test
    self.thread = threading.Thread(
        target=self._run, name='TestInvocation-%s' % test.path)
    self.on_completion = on_completion
    post_shutdown_tag = state.POST_SHUTDOWN_TAG % test.path
    if factory.get_shared_data(post_shutdown_tag):
      # If this is going to be a post-shutdown run of an active shutdown test,
      # reuse the existing invocation as uuid so that we can accumulate all the
      # logs in the same log file.
      self.uuid = factory.get_shared_data(post_shutdown_tag)
    else:
      self.uuid = event_log.TimedUuid()
    self.output_dir = os.path.join(factory.get_test_data_root(),
                                   '%s-%s' % (self.test.path,
                                              self.uuid))
    utils.TryMakeDirs(self.output_dir)

    # Create a symlink for the latest test run, so if we're looking at the
    # logs we don't need to enter the whole UUID.
    latest_symlink = os.path.join(factory.get_test_data_root(),
                                  self.test.path)
    try:
      os.remove(latest_symlink)
    except OSError:
      pass
    try:
      os.symlink(os.path.basename(self.output_dir), latest_symlink)
    except OSError:
      logging.exception('Unable to create symlink %s', latest_symlink)

    self.metadata_file = os.path.join(self.output_dir, 'metadata')
    self.env_additions = {'CROS_FACTORY_TEST_PATH': self.test.path,
                          'CROS_FACTORY_TEST_INVOCATION': self.uuid,
                          'CROS_FACTORY_TEST_METADATA': self.metadata_file}
    self.metadata = {}
    self.update_metadata(path=test.path,
                         init_time=time.time(),
                         invocation=str(self.uuid),
                         label_en=test.label_en,
                         label_zh=test.label_zh)
    self.count = None
    self.log_path = os.path.join(self.output_dir, 'log')
    self.update_state_on_completion = {}

    self._lock = threading.Lock()
    # The following properties are guarded by the lock.
    self._aborted = False
    self._aborted_reason = None
    self._completed = False
    self._process = None

  def __repr__(self):
    return 'TestInvocation(_aborted=%s, _completed=%s)' % (
      self._aborted, self._completed)

  def update_metadata(self, **kwargs):
    self.metadata.update(kwargs)
    tmp = self.metadata_file + '.tmp'
    with open(tmp, 'w') as f:
      yaml.dump(self.metadata, f, default_flow_style=False)
    os.rename(tmp, self.metadata_file)

  def start(self):
    """Starts the test thread."""
    self.thread.start()

  def abort_and_join(self, reason=None):
    """Aborts a test (must be called from the event controller thread)."""
    with self._lock:
      self._aborted = True
      self._aborted_reason = reason
      process = self._process
    if process:
      utils.kill_process_tree(process, 'autotest')
    if self.thread:
      self.thread.join()
    with self._lock:
      # Should be set by the thread itself, but just in case...
      self._completed = True

  def is_completed(self):
    """Returns true if the test has finished."""
    return self._completed

  def _aborted_message(self):
    """Returns an error message describing why the test was aborted."""
    return 'Aborted' + (
        (': ' + self._aborted_reason) if self._aborted_reason else '')

  def _invoke_autotest(self):
    """Invokes an autotest test.

    This method encapsulates all the magic necessary to run a single
    autotest test using the 'autotest' command-line tool and get a
    sane pass/fail status and error message out.  It may be better
    to just write our own command-line wrapper for job.run_test
    instead.

    Returns:
      tuple of status (TestState.PASSED or TestState.FAILED) and error message,
      if any
    """
    assert self.test.autotest_name

    test_tag = '%s_%s' % (self.test.path, self.count)
    dargs = dict(self.test.dargs)
    dargs.update({
        'tag': test_tag,
        'test_list_path': self.goofy.options.test_list
    })

    status = TestState.FAILED
    error_msg = 'Unknown'

    try:
      # Symlink client.INFO to the log path.
      os.symlink('results/default/debug/client.INFO',
                 self.log_path)
      tmp_dir = tempfile.mkdtemp(prefix='tmp', dir=self.output_dir)

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
          self.test.autotest_name, args_file))

        print >> f, (
          "pickle.dump((success, "
          "str(job.last_error) if job.last_error else None), "
          "open('%s', 'w'), protocol=2)"
          % result_file)

      args = [os.path.join(os.path.dirname(factory.FACTORY_PATH),
                 'autotest/bin/autotest'),
          '--output_dir', self.output_dir,
          control_file]

      logging.debug('Test command line: %s', ' '.join(
          [pipes.quote(arg) for arg in args]))

      self.env_additions['CROS_PROC_TITLE'] = (
          '%s.py (factory autotest %s)' % (
              self.test.autotest_name, self.output_dir))

      with self._lock:
        with self.goofy.env.lock:
          self._process = self.goofy.env.spawn_autotest(
            self.test.autotest_name, args, self.env_additions,
            result_file)

      returncode = self._process.wait()
      with self._lock:
        if self._aborted:
          error_msg = self._aborted_message()
          return

      if returncode:
        # Only happens when there is an autotest-level problem (not when
        # the test actually failed).
        error_msg = 'autotest returned with code %d' % returncode
        return

      with open(result_file) as f:
        try:
          success, error_msg = pickle.load(f)
        except:
          logging.exception('Unable to retrieve autotest results')
          error_msg = 'Unable to retrieve autotest results'
          return

      if success:
        status = TestState.PASSED
        error_msg = ''
    except Exception:  # pylint: disable=W0703
      logging.exception('Exception in autotest driver')
      # Make sure Goofy reports the exception upon destruction
      # (e.g., for testing)
      self.goofy.record_exception(traceback.format_exception_only(
          *sys.exc_info()[:2]))
    finally:
      self.clean_autotest_logs()
      return status, error_msg  # pylint: disable=W0150

  def _invoke_pytest(self):
    """Invokes a pyunittest-based test."""
    assert self.test.pytest_name

    files_to_delete = []
    try:
      def make_tmp(prefix):
        ret = tempfile.mktemp(
          prefix='%s-%s-' % (self.test.path, prefix))
        files_to_delete.append(ret)
        return ret

      info_path = make_tmp('info')
      results_path = make_tmp('results')

      log_dir = os.path.join(factory.get_test_data_root())
      if not os.path.exists(log_dir):
        os.makedirs(log_dir)

      try:
        args = ResolveTestArgs(self.test.dargs)
      except Exception, e:
        logging.exception('Unable to resolve test arguments')
        return TestState.FAILED, 'Unable to resolve test arguments: %s' % e

      pytest_name = self.test.pytest_name
      if self.goofy.options.automation_mode != AutomationMode.NONE:
        # Load override test list dargs if OVERRIDE_TEST_LIST_DARGS_FILE exists.
        if os.path.exists(OVERRIDE_TEST_LIST_DARGS_FILE):
          with open(OVERRIDE_TEST_LIST_DARGS_FILE) as f:
            override_dargs_from_file = yaml.safe_load(f.read())
          args.update(override_dargs_from_file.get(self.test.path, {}))
        logging.warn(args)

        if self.test.has_automator:
          logging.info('Enable factory test automator for %r', pytest_name)
          if os.path.exists(os.path.join(
              factory.FACTORY_PATH, 'py', 'test', 'pytests', pytest_name,
              pytest_name + '_automator_private.py')):
            pytest_name += '_automator_private'
          elif os.path.exists(os.path.join(
              factory.FACTORY_PATH, 'py', 'test', 'pytests', pytest_name,
              pytest_name + '_automator.py')):
            pytest_name += '_automator'
          else:
            raise InvocationError('Cannot find automator for %r' % pytest_name)

      with open(info_path, 'w') as info:
        pickle.dump(PyTestInfo(
            test_list=self.goofy.options.test_list,
            path=self.test.path,
            pytest_name=pytest_name,
            args=args,
            results_path=results_path,
            automation_mode=self.goofy.options.automation_mode), info)

      # Invoke the unittest driver in a separate process.
      with open(self.log_path, 'ab', 0) as log:
        this_file = os.path.realpath(__file__)
        this_file = re.sub(r'\.pyc$', '.py', this_file)
        args = [this_file, '--pytest', info_path]

        cmd_line = ' '.join([pipes.quote(arg) for arg in args])
        print >> log, 'Running test: %s' % cmd_line

        logging.debug('Test command line: %s >& %s',
                      cmd_line, self.log_path)

        self.env_additions['CROS_PROC_TITLE'] = (
            '%s.py (factory pytest %s)' % (pytest_name, self.output_dir))

        env = dict(os.environ)
        env.update(self.env_additions)
        with self._lock:
          if self._aborted:
            return TestState.FAILED, (
                'Before starting: %s' % self._aborted_message())

          self._process = Spawn(
              args,
              env=env,
              stdin=open(os.devnull, "w"),
              stdout=subprocess.PIPE,
              stderr=subprocess.STDOUT)

        # Tee process's stderr to both the log and our stderr; this
        # will end when the process dies.
        while True:
          line = self._process.stdout.readline()
          if not line:
            break
          log.write(line)
          sys.stderr.write('%s> %s' % (self.test.path, line))

        self._process.wait()
        with self._lock:
          if self._aborted:
            return TestState.FAILED, self._aborted_message()
        if self._process.returncode:
          return TestState.FAILED, (
            'Test returned code %d' % self._process.returncode)

      if not os.path.exists(results_path):
        return TestState.FAILED, 'pytest did not complete'

      with open(results_path) as f:
        return pickle.load(f)
    except:
      logging.exception('Unable to retrieve pytest results')
      return TestState.FAILED, 'Unable to retrieve pytest results'
    finally:
      for f in files_to_delete:
        try:
          if os.path.exists(f):
            os.unlink(f)
        except:
          logging.exception('Unable to delete temporary file %s',
                    f)

  def _invoke_target(self):
    """Invokes a target directly within Goofy."""
    try:
      self.test.invocation_target(self)
      return TestState.PASSED, ''
    except:
      logging.exception('Exception while invoking target')

      if sys.exc_info()[0] == factory.FactoryTestFailure:
        # Use the status from the exception.
        status = sys.exc_info()[1].status
      else:
        status = TestState.FAILED

      return status, traceback.format_exc()

  def clean_autotest_logs(self):
    globs = self.goofy.test_list.options.preserve_autotest_results
    if '*' in globs:
      # Keep everything
      return

    deleted_count = 0
    preserved_count = 0
    for root, unused_dirs, files in os.walk(self.output_dir, topdown=False):
      for f in files:
        if f in ['log', 'metadata'] or any(fnmatch.fnmatch(f, g)
                                           for g in globs):
          # Keep it
          preserved_count = 1
        else:
          try:
            os.unlink(os.path.join(root, f))
            deleted_count += 1
          except:
            logging.exception('Unable to remove %s',
                              os.path.join(root, f))
      try:
        # Try to remove the directory (in case it's empty now)
        os.rmdir(root)
      except OSError:
        # Not empty; that's OK
        pass
    logging.info('Preserved %d files matching %s and removed %d',
           preserved_count, globs, deleted_count)

  def _run(self):
    with self._lock:
      if self._aborted:
        return

    iteration_string = ''
    retries_string = ''
    if self.test.iterations > 1:
      iteration_string = ' [%s/%s]' % (
        self.test.iterations -
        self.test.get_state().iterations_left + 1,
        self.test.iterations)
    if self.test.retries > 0:
      retries_string = ' [retried %s/%s]' % (
        self.test.retries -
        self.test.get_state().retries_left,
        self.test.retries)
    logging.info('Running test %s%s%s', self.test.path,
                 iteration_string, retries_string)

    service_manager = ServiceManager()
    service_manager.SetupServices(enable_services=self.test.enable_services,
                                  disable_services=self.test.disable_services)

    log_args = dict(
      path=self.test.path,
      # Use Python representation for dargs, since some elements
      # may not be representable in YAML.
      dargs=repr(self.test.dargs),
      invocation=self.uuid)
    if self.test.autotest_name:
      log_args['autotest_name'] = self.test.autotest_name
    if self.test.pytest_name:
      log_args['pytest_name'] = self.test.pytest_name

    self.goofy.event_log.Log('start_test', **log_args)

    self.update_metadata(start_time=time.time(), **log_args)
    start_time = time.time()

    syslog.syslog('Test %s (%s) starting' % (
        self.test.path, self.uuid))

    try:
      if self.test.prepare:
        self.test.prepare()
    except:
      logging.exception('Exception while invoking before_callback %s',
          traceback.format_exc())

    try:
      status, error_msg = None, None
      if self.test.autotest_name:
        status, error_msg = self._invoke_autotest()
      elif self.test.pytest_name:
        status, error_msg = self._invoke_pytest()
      elif self.test.invocation_target:
        status, error_msg = self._invoke_target()
      else:
        status = TestState.FAILED
        error_msg = (
          'No autotest_name, pytest_name, or invocation_target')
    finally:
      if error_msg:
        error_msg = DecodeUTF8(error_msg)

      try:
        self.goofy.event_client.post_event(
            Event(Event.Type.DESTROY_TEST,
                  test=self.test.path,
                  invocation=self.uuid))
      except:
        logging.exception('Unable to post DESTROY_TEST event')

      syslog.syslog('Test %s (%s) completed: %s%s' % (
          self.test.path, self.uuid, status,
          (' (%s)' % error_msg if error_msg else '')))

      try:
        # Leave all items in log_args; this duplicates
        # things but will make it easier to grok the output.
        end_time = time.time()
        log_args.update(dict(status=status,
                             duration=(end_time - start_time)))
        if error_msg:
          log_args['error_msg'] = error_msg
        if (status != TestState.PASSED and
            self.log_path and
            os.path.exists(self.log_path)):
          try:
            log_size = os.path.getsize(self.log_path)
            offset = max(0, log_size - ERROR_LOG_TAIL_LENGTH)
            with open(self.log_path) as f:
              f.seek(offset)
              log_args['log_tail'] = DecodeUTF8(f.read())
          except:
            logging.exception('Unable to read log tail')
        self.goofy.event_log.Log('end_test', **log_args)
        self.update_metadata(end_time=end_time, **log_args)
      except:
        logging.exception('Unable to log end_test event')

    service_manager.RestoreServices()

    logging.info(u'Test %s%s %s', self.test.path, iteration_string,
                 ': '.join([status, error_msg]))

    decrement_iterations_left = 0
    decrement_retries_left = 0

    if status == TestState.FAILED:
      reason = error_msg.split('\n')[0]
      factory.console.error('Test %s%s %s: %s', self.test.path,
                            iteration_string, status, reason)
      decrement_retries_left = 1
    elif status == TestState.PASSED:
      decrement_iterations_left = 1

    try:
      if self.test.finish:
        self.test.finish(status)
    except:
      logging.exception('Exception while invoking finish_callback %s',
          traceback.format_exc())

    with self._lock:
      self.update_state_on_completion = dict(
        status=status, error_msg=error_msg,
        visible=False, decrement_iterations_left=decrement_iterations_left,
        decrement_retries_left=decrement_retries_left)
      self._completed = True

    self.goofy.run_queue.put(self.goofy.reap_completed_tests)
    if self.on_completion:
      self.goofy.run_queue.put(self.on_completion)


def _RecursiveApply(func, suite):
  """Recursively applies a function to all the test cases in a test suite.

  Args:
    suite: A TestSuite object.
    func: A callable object to map.
  """
  for test in suite:
    if isinstance(test, unittest.TestSuite):
      _RecursiveApply(func, test)
    elif isinstance(test, unittest.TestCase):
      func(test)
    else:
      raise ValueError('Expect only TestSuite and TestCase: %r' % type(test))


def GetTestCases(suite):
  """Gets the list of test case IDs in the given suite.

  Args:
    suite: A TestSuite instance.

  Retuns:
    A list of strings of test case IDs.
  """
  test_cases = []
  def FilterTestCase(test):
    # Filter out the test case from base Automator class.
    if test.id() == 'cros.factory.test.e2e_test.automator.Automator.runTest':
      return
    test_cases.append(test.id())

  _RecursiveApply(FilterTestCase, suite)
  return test_cases


def InvokeTestCase(suite, test_case_id, test_info):
  """Invokes a test case in another process.

  This function is called in the top level of invocation.py.  It recursively
  searches for the given test case in the given test suite.  A new TestInfo
  instance with new test_case_id and results_path is prepared along with a new
  test invocation.  All the new info is passed to a subprocess which actually
  runs the test case with RunTestCase.

  Args:
    suite: A TestSuite object.
    test_case_id: The ID of the test case to invoke.
    test_info: A PyTestInfo object containing information about what to
      run.

  Returns:
    The test result of the test case.
  """
  results = []

  def _InvokeByID(test_case):
    if test_case.id() == test_case_id:
      logging.debug('[%s] Really invoke test case: %s',
                   os.getpid(), test_case_id)
      with file_utils.UnopenedTemporaryFile() as info_path, \
          file_utils.UnopenedTemporaryFile() as results_path:
        # Update test_info attributes for the test case.
        new_info = copy.deepcopy(test_info)
        new_info.test_case_id = test_case_id
        new_info.results_path = results_path
        with open(info_path, 'w') as f:
          pickle.dump(new_info, f)

        # Set up subprocess args.
        this_file = os.path.realpath(__file__)
        this_file = re.sub(r'\.pyc$', '.py', this_file)
        args = [this_file, '--pytest', info_path]

        # Generate an invocation and set it in the env of subprocess.
        # We need a new invocation uuid here to have a new UI context. We
        # propagate down the original invocation uuid as the parent of the new
        # uuid, so we can properly clean up all associated invocations later.
        subenv = dict(os.environ)
        pytest_invoc = event_log.TimedUuid()
        parent_invoc = os.environ['CROS_FACTORY_TEST_INVOCATION']
        subenv.update({
            'CROS_FACTORY_TEST_INVOCATION': pytest_invoc,
            'CROS_FACTORY_TEST_PARENT_INVOCATION': parent_invoc
        })

        # Wait for the subprocess to end and load the results.
        process = Spawn(args, env=subenv)
        process.wait()
        with open(results_path) as f:
          results.append(pickle.load(f))

  _RecursiveApply(_InvokeByID, suite)
  assert len(results) == 1, 'Should have exactly one test result'
  return results[0]


def RunTestCase(suite, test_case_id):
  """Runs the given test case.

  This is the actual test case runner.  It recursively searches for the given
  test case in the given test suite, runs the test case if found, and returns
  the test results.

  Args:
    suite: A TestSuite object.
    test_case_id: The ID of the test case to run.

  Returns:
    The test result of the test case.
  """
  results = []

  def _RunByID(test_case):
    if (test_case.id() == test_case_id or
        test_case_id == PyTestInfo.NO_SUBPROCESS):
      logging.debug('[%s] Really run test case: %s', os.getpid(), test_case_id)
      result = unittest.TestResult()
      test_case.run(result)
      results.append(result)

  _RecursiveApply(_RunByID, suite)
  assert len(results) == 1, 'Should have exactly one test result'
  return results[0]


def LoadPytestModule(pytest_name):
  """Loads the given pytest module.

  This function tries to load the module with

      cros.factory.test.pytests.<pytest_base_name>.<pytest_name>

  first and falls back to

      cros.factory.test.pytests.<pytest_name>

  for backward compatibility.

  Args:
    pytest_name: The name of the pytest module.

  Returns:
    The loaded pytest module object.
  """
  from cros.factory.test import pytests
  base_pytest_name = pytest_name
  for suffix in ('_e2etest', '_automator', '_automator_private'):
    base_pytest_name = re.sub(suffix, '', base_pytest_name)

  try:
    __import__('cros.factory.test.pytests.%s.%s' %
               (base_pytest_name, pytest_name))
    return getattr(getattr(pytests, base_pytest_name), pytest_name)
  except ImportError:
    logging.info(
        ('Cannot import cros.factory.test.pytests.%s.%s. '
         'Fall back to cros.factory.test.pytests.%s'),
        base_pytest_name, pytest_name, pytest_name)
    __import__('cros.factory.test.pytests.%s' % pytest_name)
    return getattr(pytests, pytest_name)


def RunPytest(test_info):
  """Runs a pytest, saving a pickled (status, error_msg) tuple to the
  appropriate results file.

  Args:
    test_info: A PyTestInfo object containing information about what to
      run.
  """
  try:
    module = LoadPytestModule(test_info.pytest_name)
    suite = unittest.TestLoader().loadTestsFromModule(module)

    # Register a handler for SIGTERM, so that Python interpreter has
    # a chance to do clean up procedures when SIGTERM is received.
    def _SIGTERMHandler(signum, frame):  # pylint: disable=W0613
      logging.error('SIGTERM received')
      raise factory.FactoryTestFailure('SIGTERM received')

    signal.signal(signal.SIGTERM, _SIGTERMHandler)

    error_msg = ''
    if test_info.test_case_id is None:
      # Top-level test suite: Invoke each TestCase in a separate subprocess.
      results = []
      for test in GetTestCases(suite):
        logging.debug('[%s] Invoke test case: %s', os.getpid(), test)
        results.append(InvokeTestCase(suite, test, test_info))

      # The results will be a list of tuples (status, error_msg) for each
      # test case.
      error_msgs = []
      for status, msg in results:
        if status == TestState.PASSED:
          continue
        error_msgs.append(msg)

      if error_msgs:
        error_msg = '; '.join(error_msgs)
    else:
      # Invoked by InvokeTestCase: Run the specified TestCase.
      logging.debug('[%s] Start test case: %s',
                    os.getpid(), test_info.test_case_id)

      # Recursively set
      def SetTestInfo(test):
        if isinstance(test, unittest.TestCase):
          test.test_info = test_info
          arg_spec = getattr(test, 'ARGS', None)
          if arg_spec:
            try:
              setattr(test, 'args', Args(*arg_spec).Parse(test_info.args))
            except ValueError as e:
              # Do not raise exceptions for E2ETest, as 'dargs' is optional
              # to it.
              from cros.factory.test.e2e_test import e2e_test
              if (re.match(r'^Required argument .* not specified$', str(e)) and
                  isinstance(test, e2e_test.E2ETest)):
                pass
              else:
                raise e
        elif isinstance(test, unittest.TestSuite):
          for x in test:
            SetTestInfo(x)

      SetTestInfo(suite)
      result = RunTestCase(suite, test_info.test_case_id)

      def FormatErrorMessage(trace):
        """Formats a trace so that the actual error message is in the last
        line.
        """
        # The actual error is in the last line.
        trace, _, error_msg = trace.strip().rpartition('\n')
        error_msg = error_msg.replace('FactoryTestFailure: ', '')
        return error_msg + '\n' + trace

      all_failures = result.failures + result.errors + test_ui.exception_list
      if all_failures:
        error_msg = '\n'.join(FormatErrorMessage(trace)
                              for test_name, trace in all_failures)

    if error_msg:
      status = TestState.FAILED
      if test_info.test_case_id:
        logging.info('pytest failure: %s', error_msg)
    else:
      status = TestState.PASSED
  except:
    logging.exception('Unable to run pytest')
    status = TestState.FAILED
    error_msg = traceback.format_exc()

  with open(test_info.results_path, 'w') as results:
    pickle.dump((status, error_msg), results)


def main():
  parser = OptionParser()
  parser.add_option('--pytest', dest='pytest_info',
                    help='Info for pytest to run')
  (options, unused_args) = parser.parse_args()

  assert options.pytest_info

  test_ui.exception_list = []

  info = pickle.load(open(options.pytest_info))
  factory.init_logging(info.path)
  proc_title = os.environ.get('CROS_PROC_TITLE')
  if proc_title:
    setproctitle(proc_title)
  RunPytest(info)

if __name__ == '__main__':
  main()
