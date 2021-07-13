# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Classes and Methods related to invoking a test."""

import logging
import os
import pickle
import signal
import sys
import tempfile
import threading
import time

from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test.env import paths
from cros.factory.test.event import Event
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test.state import TestState
from cros.factory.test.test_lists import manager
from cros.factory.test.test_lists import test_object
from cros.factory.test.utils import pytest_utils
from cros.factory.testlog import testlog
from cros.factory.testlog import testlog_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils
from cros.factory.utils.service_utils import ServiceManager
from cros.factory.utils.string_utils import DecodeUTF8
from cros.factory.utils import time_utils

from cros.factory.external import syslog

# Number of bytes to include from the log of a failed test.
ERROR_LOG_TAIL_LENGTH = 8 * 1024


class InvocationError(Exception):
  """Invocation error."""


def ResolveTestArgs(goofy, test, test_list_id, dut_options):
  """Resolves an argument dictionary.

  The dargs will be passed to test_list.ResolveTestArgs(), which will
  evaluate values start with 'eval! ' and 'i18n! '.

  Args:
    goofy: a goofy instance.
    test: a FactoryTest object whose dargs will be resolved.
    test_list_id: ID of the test list the `test` object belongs to.
    dut_options: DUT options for current test.

  Returns:
    Resolved dargs dictionary object.
  """
  dargs = test.dargs
  locals_ = test.locals_

  try:
    test_list = goofy.GetTestList(test_list_id)
  except Exception:
    logging.exception('Goofy does not have test list `%s`', test_list_id)
    raise

  dut_options = dut_options or {}
  dut = device_utils.CreateDUTInterface(**dut_options)
  # TODO(stimim): might need to override station options?
  station = device_utils.CreateStationInterface()
  return test_list.ResolveTestArgs(
      dargs, dut=dut, station=station, locals_=locals_)


class PytestInfo:
  """A class to hold all the data needed when invoking a test.

  Properties:
    test_list: The test list name or ID to get the factory test info from.
    path: The path of the test in the test list.
    pytest_name: The name of the factory test to run.
    args: Arguments passing down to the factory test.
    results_path: The path to the result file.
    dut_options: The options to override default DUT target.
  """

  def __init__(self, test_list, path, pytest_name, args, results_path,
               dut_options=None):
    self.test_list = test_list
    self.path = path
    self.pytest_name = pytest_name
    self.args = args
    self.results_path = results_path
    self.dut_options = dut_options or {}

  def ReadTestList(self):
    """Reads and returns the test list."""
    return manager.Manager().GetTestListByID(self.test_list)


class TestInvocation:
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

  def __init__(self, goofy, test, on_completion=None, on_test_failure=None):
    """Constructor.

    Args:
      goofy: The controlling Goofy object.
      test: The FactoryTest object to test.
      on_completion: Callback to invoke in the goofy event queue
        on completion.
      on_test_failure: Callback to invoke in the goofy event queue
        when the test fails.
    """
    self.goofy = goofy
    self.test = test
    self.thread = threading.Thread(
        target=self._Run, name='TestInvocation-%s' % self.test.path)
    self.thread.daemon = True
    self.count = None
    self.update_state_on_completion = {}
    self._on_completion = on_completion
    self._on_test_failure = on_test_failure

    post_shutdown_state = state.DataShelfGetValue(
        state.KEY_POST_SHUTDOWN % self.test.path)
    self._is_post_shutdown = bool(post_shutdown_state)
    self.uuid = self._ResolveUUID(post_shutdown_state)
    self._env_additions = {session.ENV_TEST_INVOCATION: self.uuid,
                           session.ENV_TEST_PATH: self.test.path}

    self.output_dir = self._SetupOutputDir()
    self._testlog_path = os.path.join(self.output_dir, 'testlog.json')
    self._dargs = None
    self._tag = None
    self._log_path = os.path.join(self.output_dir, 'log')
    self._source_code_path = os.path.join(self.output_dir, 'source_code')

    self._dut_options = self._ResolveDUTOptions()
    self.dut = device_utils.CreateDUTInterface(**self._dut_options)

    self._lock = threading.Lock()
    # The following properties are guarded by the lock.
    self._aborted = False
    self._aborted_reason = None
    self._completed = False
    self._process = None

  @property
  def resolved_dargs(self):
    return self._dargs

  def __repr__(self):
    return 'TestInvocation(_aborted=%s, _completed=%s)' % (
        self._aborted, self._completed)

  def Start(self):
    """Starts the test threads."""
    self.thread.start()

  def AbortAndJoin(self, reason=None):
    """Aborts a test (must be called from the event controller thread)."""
    with self._lock:
      self._aborted = True
      self._aborted_reason = reason
      process = self._process
    if process:
      process_utils.KillProcessTree(process, 'pytest')
    if self.thread:
      self.thread.join()
    with self._lock:
      # Should be set by the thread itself, but just in case...
      self._completed = True

  def IsCompleted(self):
    """Returns true if the test has finished."""
    return self._completed

  def _AbortedMessage(self):
    """Returns an error message describing why the test was aborted."""
    return 'Aborted' + (
        (': ' + self._aborted_reason) if self._aborted_reason else '')

  @classmethod
  def _ResolveUUID(cls, post_shutdown_state):
    if post_shutdown_state:
      # If this is going to be a post-shutdown run of an active shutdown test,
      # reuse the existing invocation as uuid so that we can accumulate all the
      # logs in the same log file.
      return post_shutdown_state['invocation']
    return time_utils.TimedUUID()

  def _SetupOutputDir(self):
    output_dir = os.path.join(paths.DATA_TESTS_DIR,
                              '%s-%s' % (self.test.path, self.uuid))
    file_utils.TryMakeDirs(output_dir)

    # Create a symlink for the latest test run, so if we're looking at the
    # logs we don't need to enter the whole UUID.
    latest_symlink = os.path.join(paths.DATA_TESTS_DIR, self.test.path)
    file_utils.TryUnlink(latest_symlink)
    try:
      os.symlink(os.path.basename(output_dir), latest_symlink)
    except OSError:
      logging.exception('Unable to create symlink %s', latest_symlink)
    return output_dir

  def _ResolveDUTOptions(self):
    """Resolve dut_options.

    Climb the tree of test options and choose the first non-empty dut_options
    encountered. Note we are not stacking the options because most DUT targets
    don't share any options.
    """
    dut_options = {}
    test_node = self.test
    while test_node and not dut_options:
      dut_options = test_node.dut_options
      test_node = test_node.parent
    if not dut_options:
      # Use the options in test list (via test.root).
      dut_options = self.test.root.options.dut_options or {}

    return dut_options

  def _InvokePytest(self):
    """Invokes a pyunittest-based test."""
    assert self.test.pytest_name
    assert self.resolved_dargs is not None

    files_to_delete = []
    try:
      def make_tmp(prefix):
        ret = tempfile.mktemp(
            prefix='%s-%s-' % (self.test.path, prefix))
        files_to_delete.append(ret)
        return ret

      results_path = make_tmp('results')

      log_dir = os.path.join(paths.DATA_TESTS_DIR)
      file_utils.TryMakeDirs(log_dir)

      pytest_name = self.test.pytest_name

      # Invoke the unittest driver in a separate process.
      with open(self._log_path, 'ab', 0) as log:
        log.write(b'Running test: %s\n' % self.test.path.encode('utf-8'))
        self._env_additions['CROS_PROC_TITLE'] = (
            '%s.py (factory pytest %s)' % (pytest_name, self.output_dir))

        env = dict(os.environ)
        env.update(self._env_additions)
        with self._lock:
          if self._aborted:
            return (TestState.FAILED,
                    'Before starting: %s' % self._AbortedMessage())

          self._process = self.goofy.pytest_prespawner.spawn(
              PytestInfo(test_list=self.goofy.test_list.test_list_id,
                         path=self.test.path,
                         pytest_name=pytest_name,
                         args=self.resolved_dargs,
                         results_path=results_path,
                         dut_options=self._dut_options),
              self._env_additions)

        def _LineCallback(line):
          log.write(line.encode('utf-8') + b'\n')
          sys.stderr.write('%s> %s\n' % (self.test.path, line))

        # Tee process's stderr to both the log and our stderr.
        process_utils.PipeStdoutLines(self._process, _LineCallback)

        # Try to kill all subprocess created by the test.
        try:
          os.kill(-self._process.pid, signal.SIGKILL)
        except OSError:
          pass
        with self._lock:
          if self._aborted:
            return TestState.FAILED, self._AbortedMessage()
        if self._process.returncode:
          return (TestState.FAILED,
                  'Test returned code %d' % self._process.returncode)

      if not os.path.exists(results_path):
        return TestState.FAILED, 'pytest did not complete'

      with open(results_path, 'rb') as f:
        result = pickle.load(f)
        assert isinstance(result, pytest_utils.PytestExecutionResult)
        # TODO(yhong): Record the the detail failure reason for advanced
        #     analysis.
        return result.status, '; '.join(f.exc_repr for f in result.failures)
    except Exception as e:
      return TestState.FAILED, 'Unable to retrieve pytest results: %r' % e
    finally:
      for f in files_to_delete:
        try:
          if os.path.exists(f):
            os.unlink(f)
        except Exception:
          logging.exception('Unable to delete temporary file %s', f)

  def _Run(self):
    iteration_string = ''
    retries_string = ''
    if self.test.iterations > 1:
      iteration_string = ' [%s/%s]' % (
          self.test.iterations -
          self.test.GetState().iterations_left + 1,
          self.test.iterations)
    if self.test.retries > 0:
      retries_string = ' [retried %s/%s]' % (
          self.test.retries -
          self.test.GetState().retries_left,
          self.test.retries)
    logging.info('Running test %s%s%s', self.test.path,
                 iteration_string, retries_string)

    if sys_utils.InCrOSDevice():
      process_utils.Spawn(['ghost', '--send-data'])

    service_manager = ServiceManager()
    service_manager.SetupServices(enable_services=self.test.enable_services,
                                  disable_services=self.test.disable_services)
    testlog_helper = _TestInvocationTestLogHelper()
    event_log_helper = _TestInvocationEventLogHelper(self.goofy.event_log)

    status, error_msg = self._PrepareRunPytest(testlog_helper, event_log_helper)

    try:
      if not os.path.exists(self._source_code_path):
        source_code_file = os.path.join(paths.FACTORY_PYTHON_PACKAGE_DIR,
                                        'test', 'pytests',
                                        self.test.pytest_name.replace('.', '/')
                                        + '.py')
        os.symlink(source_code_file, self._source_code_path)
    except Exception:
      logging.exception('Unable to link source code file')

    try:
      # Run the pytest if everything was fine.
      if status is None:
        if self.test.pytest_name:
          status, error_msg = self._InvokePytest()
        else:
          status = TestState.FAILED
          error_msg = 'No pytest_name'
    finally:
      status, error_msg = self._TearDownAfterPytest(
          testlog_helper, event_log_helper, status, error_msg)

    service_manager.RestoreServices()

    log_func = (session.console.error if status == TestState.FAILED
                else logging.info)
    tag_decorator = (' (%s)' % self._tag if self._tag else '')
    log_func(u'Test %s%s%s %s: %s', self.test.path, iteration_string,
             tag_decorator, status, error_msg)

    self._InvokeOnCompleteCallBack(status, error_msg)

  def _PrepareRunPytest(self, testlog_helper, event_log_helper):
    if self._is_post_shutdown:
      tag_name = 'post-shutdown'
      event_name = 'resume_test'
      progressing_verb = 'resuming'
    else:
      tag_name = 'pre-shutdown'
      event_name = 'start_test'
      progressing_verb = 'starting'

    status, error_msg = None, None

    start_time = time.time()
    serial_numbers = device_data.GetAllSerialNumbers()
    if isinstance(self.test, test_object.ShutdownStep):
      self._tag = tag_name
    try:
      logging.debug('Resolving self.test.dargs from test list [%s]...',
                    self.goofy.test_list.test_list_id)
      self._dargs = ResolveTestArgs(
          self.goofy,
          self.test,
          test_list_id=self.goofy.test_list.test_list_id,
          dut_options=self._dut_options)
    except Exception as e:
      logging.exception('Unable to resolve test arguments')
      # Although the test is considered failed already,
      # let's still follow the normal path, so everything is logged properly.
      status = TestState.FAILED
      error_msg = 'Unable to resolve test arguments: %s' % e

    init_data = {
        'testRunId': self.uuid,
        'testName': self.test.path,
        'testType': self.test.pytest_name,
        'startTime': start_time,
        'dargs': self._dargs,
        'serialNumbers': serial_numbers,
        'tag': self._tag
    }
    try:
      testlog_helper.InitSubSession(self.dut, init_data)
    except Exception:
      logging.exception('Unable to log %s event by testlog', event_name)

    # Since the reboot pytest will kill the process and re-run a new process,
    # the testlog file may exist.
    if os.path.exists(self._testlog_path):
      os.unlink(self._testlog_path)
    os.link(testlog_helper.session_json_path, self._testlog_path)

    self._env_additions[
        testlog.TESTLOG_ENV_VARIABLE_NAME] = testlog_helper.session_json_path
    testlog_helper.LogStartEvent()

    # Log the starting event, continue even if fails.
    try:
      event_log_helper.LogStartEvent(event_name, init_data)
    except Exception:
      logging.exception('Unable to log %s event by event_log', event_name)

    syslog.syslog('Test %s (%s) %s' %
                  (self.test.path, self.uuid, progressing_verb))

    return status, error_msg

  def _TearDownAfterPytest(self, testlog_helper, event_log_helper, status,
                           error_msg):
    def _SafelyCreateLogTail():
      log_tail = 'Unable to read log tail'
      if self._log_path and os.path.exists(self._log_path):
        try:
          log_size = os.path.getsize(self._log_path)
          offset = max(0, log_size - ERROR_LOG_TAIL_LENGTH)
          with open(self._log_path) as f:
            f.seek(offset)
            log_tail = DecodeUTF8(f.read())
        except Exception:
          logging.exception('Unable to read log tail')
      return log_tail

    def _HandleLogEndTestEventFail(orig_status, logger_name):
      session.console.exception('Unable to log end_test event by %s. '
                                'Change status from %s to FAILED',
                                orig_status, logger_name)
      status = TestState.FAILED
      error_msg = 'Unable to log end_test event'
      return status, error_msg

    # Shutdown the test.
    if error_msg:
      error_msg = DecodeUTF8(error_msg)
    try:
      self.goofy.event_client.post_event(
          Event(Event.Type.DESTROY_TEST,
                test=self.test.path,
                invocation=self.uuid))
    except Exception:
      logging.exception('Unable to post DESTROY_TEST event')

    syslog.syslog('Test %s (%s) completed: %s%s' % (
        self.test.path, self.uuid, status,
        (' (%s)' % error_msg if error_msg else '')))

    end_time = time.time()
    finish_data = {
        'status': status,
        'endTime': end_time
    }
    if error_msg:
      finish_data['error_msg'] = error_msg
    if status != TestState.PASSED:
      finish_data['log_tail'] = _SafelyCreateLogTail()

    # Log the end test event.
    try:
      testlog_helper.LogFinishEvent(finish_data)
      del self._env_additions[testlog.TESTLOG_ENV_VARIABLE_NAME]
    except Exception:
      status, error_msg = _HandleLogEndTestEventFail(status, 'testlog')
    finally:
      try:
        event_log_helper.LogEndEvent(finish_data)
      except Exception:
        status, error_msg = _HandleLogEndTestEventFail(status, 'event_log')

    return status, error_msg

  def _InvokeOnCompleteCallBack(self, status, error_msg):
    decrement_iterations_left = 0
    decrement_retries_left = 0

    if status == TestState.FAILED:
      if self.test.waived:
        status = TestState.FAILED_AND_WAIVED
      decrement_retries_left = 1
    elif status == TestState.PASSED:
      decrement_iterations_left = 1

    with self._lock:
      self.update_state_on_completion = dict(
          status=status,
          error_msg=error_msg,
          decrement_iterations_left=decrement_iterations_left,
          decrement_retries_left=decrement_retries_left)
      self._completed = True

    self.goofy.RunEnqueue(self.goofy.ReapCompletedTests)
    if status == TestState.FAILED:
      self.goofy.RunEnqueue(self._on_test_failure)
    if self._on_completion:
      self.goofy.RunEnqueue(self._on_completion)

    if sys_utils.InCrOSDevice():
      process_utils.Spawn(['ghost', '--send-data'])


class _TestInvocationTestLogHelper:
  """A helper class to log the testlog event.

  Properties:
    session_json_path: Testlog's sub-session path.
  """

  _STATUS_CONVERSION = {
      # TODO(itspeter): No mapping for STARTING ?
      TestState.ACTIVE: testlog.StationTestRun.STATUS.RUNNING,
      TestState.PASSED: testlog.StationTestRun.STATUS.PASS,
      TestState.FAILED: testlog.StationTestRun.STATUS.FAIL,
      TestState.UNTESTED: testlog.StationTestRun.STATUS.UNKNOWN,
      # TODO(itspeter): Consider adding another status.
      TestState.FAILED_AND_WAIVED: testlog.StationTestRun.STATUS.PASS,
      TestState.SKIPPED: testlog.StationTestRun.STATUS.PASS}

  def __init__(self):
    self.session_json_path = None

  def InitSubSession(self, dut, init_data):
    def _GetDUTDeviceID(dut):
      if not dut.link.IsReady():
        return 'device-offline'
      device_id = dut.info.device_id
      # TODO(chuntsen): If the dutDeviceId won't be None anymore, remove this.
      if not isinstance(device_id, str):
        logging.error('DUT device ID is an unexpected type (%s)',
                      type(device_id))
        device_id = str(device_id)
      return device_id

    testlog_event = testlog.StationTestRun()

    kwargs = {
        'dutDeviceId': _GetDUTDeviceID(dut),
        'stationDeviceId': session.GetDeviceID(),
        'stationInstallationId': session.GetInstallationID(),
        'testRunId': init_data['testRunId'],
        'testName': init_data['testName'],
        'testType': init_data['testType'],
        'status': testlog.StationTestRun.STATUS.RUNNING,
        'startTime': init_data['startTime']
    }
    testlog_event.Populate(kwargs)

    dargs = init_data['dargs']
    if dargs:
      # Only allow types that can be natively expressed in JSON.
      flattened_dargs = testlog_utils.FlattenAttrs(
          dargs, allow_types=(int, float, str, type(None)))
      for k, v in flattened_dargs:
        testlog_event.AddArgument(k, v)
    for k, v in init_data['serialNumbers'].items():
      testlog_event.AddSerialNumber(k, v)

    tag = init_data['tag']
    if tag:
      testlog_event.LogParam(name='tag', value=tag)
      testlog_event.UpdateParam(name='tag',
                                description='Indicate type of shutdown')

    self.session_json_path = testlog.InitSubSession(
        log_root=paths.DATA_LOG_DIR, station_test_run=testlog_event,
        uuid=init_data['testRunId'])

  def LogStartEvent(self):
    testlog_event = testlog.StationTestRun()
    testlog_event.Populate({'status': testlog.StationTestRun.STATUS.STARTING})
    testlog.LogTestRun(self.session_json_path, station_test_run=testlog_event)

  def LogFinishEvent(self, finish_data):
    status = self._STATUS_CONVERSION.get(finish_data['status'],
                                         finish_data['status'])

    testlog_event = testlog.StationTestRun()

    kwargs = {
        'endTime': finish_data['endTime'],
        'status': status
    }
    testlog_event.Populate(kwargs)

    if status == testlog.StationTestRun.STATUS.FAIL:
      for err_field, failure_code in [('error_msg', 'GoofyErrorMsg'),
                                      ('log_tail', 'GoofyLogTail')]:
        if err_field in finish_data:
          testlog_event.AddFailure(failure_code, finish_data[err_field])

    testlog.LogFinalTestRun(self.session_json_path,
                            station_test_run=testlog_event)


class _TestInvocationEventLogHelper:
  """Helper class to log the event_log event."""
  def __init__(self, event_log):
    self._event_log = event_log
    self._event_log_args = {}

  def LogStartEvent(self, event_name, start_data):
    self._event_log_args = {
        'path': start_data['testName'],
        'dargs': start_data['dargs'],
        'serial_numbers': start_data['serialNumbers'],
        'invocation': start_data['testRunId'],
        'start_time': start_data['startTime']
    }
    self._UpdateArgsIfKeyExists(start_data, 'testType')
    self._UpdateArgsIfKeyExists(start_data, 'tag')

    self._event_log.Log(event_name, **self._event_log_args)

    self._event_log_args.pop('dargs', None)
    self._event_log_args.pop('serialNumbers', None)
    self._event_log_args.pop('tag', None)

  def LogEndEvent(self, end_data):
    duration = end_data['endTime'] - self._event_log_args['start_time']
    self._event_log_args.update({'status': end_data['status'],
                                 'duration': duration})
    self._UpdateArgsIfKeyExists(end_data, 'error_msg')
    self._event_log.Log('end_test', **self._event_log_args)

  def _UpdateArgsIfKeyExists(self, data, key):
    if key in data:
      self._event_log_args[key] = data[key]
