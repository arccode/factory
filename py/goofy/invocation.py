# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Classes and Methods related to invoking a test."""

from __future__ import print_function

import copy
import cPickle as pickle
import logging
import os
import pprint
import signal
import sys
import tempfile
import threading
import time

import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test.env import paths
from cros.factory.test.event import Event
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test.state import TestState
from cros.factory.test.test_lists import manager
from cros.factory.test.test_lists import test_object
from cros.factory.testlog import testlog
from cros.factory.testlog import testlog_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils.service_utils import ServiceManager
from cros.factory.utils.string_utils import DecodeUTF8
from cros.factory.utils import time_utils

from cros.factory.external import syslog

# Number of bytes to include from the log of a failed test.
ERROR_LOG_TAIL_LENGTH = 8 * 1024


class InvocationError(Exception):
  """Invocation error."""
  pass


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


class PytestInfo(object):
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
    self.start_time = None
    self.end_time = None
    self.on_completion = on_completion
    self.on_test_failure = on_test_failure
    self.resume_test = False
    self.session_json_path = None
    key_post_shutdown = state.KEY_POST_SHUTDOWN % self.test.path
    if state.get_shared_data(key_post_shutdown):
      # If this is going to be a post-shutdown run of an active shutdown test,
      # reuse the existing invocation as uuid so that we can accumulate all the
      # logs in the same log file.
      self.uuid = state.get_shared_data(key_post_shutdown)['invocation']
    else:
      self.uuid = time_utils.TimedUUID()
    self.output_dir = os.path.join(paths.DATA_TESTS_DIR,
                                   '%s-%s' % (self.test.path,
                                              self.uuid))
    file_utils.TryMakeDirs(self.output_dir)

    # Create a symlink for the latest test run, so if we're looking at the
    # logs we don't need to enter the whole UUID.
    latest_symlink = os.path.join(paths.DATA_TESTS_DIR,
                                  self.test.path)
    file_utils.TryUnlink(latest_symlink)
    try:
      os.symlink(os.path.basename(self.output_dir), latest_symlink)
    except OSError:
      logging.exception('Unable to create symlink %s', latest_symlink)

    self.metadata_file = os.path.join(self.output_dir, 'metadata')
    self.env_additions = {
        session.ENV_TEST_INVOCATION: self.uuid,
        session.ENV_TEST_PATH: self.test.path}

    # Resuming from an active shutdown test, try to restore its metadata file.
    if state.get_shared_data(key_post_shutdown):
      try:
        self._LoadMetadata()
      except Exception:
        logging.exception('Failed to load metadata from active shutdown test; '
                          'will continue, but logs will be inaccurate')

    if not self.resume_test:
      self.metadata = {}
      self._UpdateMetadata(
          path=test.path,
          init_time=time.time(),
          invocation=self.uuid,
          label=test.label)

    self.count = None
    self.log_path = os.path.join(self.output_dir, 'log')
    self.update_state_on_completion = {}
    self.dut_options = self._ResolveDUTOptions()
    self.dut = device_utils.CreateDUTInterface(**self.dut_options)
    self.resolved_dargs = None

    self._lock = threading.Lock()
    # The following properties are guarded by the lock.
    self._aborted = False
    self._aborted_reason = None
    self._completed = False
    self._process = None

  def __repr__(self):
    return 'TestInvocation(_aborted=%s, _completed=%s)' % (
        self._aborted, self._completed)

  def _LoadMetadata(self):
    def _ValidateMetadata(metadata):
      REQUIRED_FIELDS = ['path', 'dargs', 'invocation',
                         'label', 'init_time', 'start_time']
      for field in REQUIRED_FIELDS:
        if field not in metadata:
          raise Exception('metadata missing field %s' % field)
      if self.test.pytest_name and 'pytest_name' not in metadata:
        raise Exception('metadata missing field pytest_name')

    with open(self.metadata_file, 'r') as f:
      metadata = yaml.load(f)
    _ValidateMetadata(metadata)
    self.metadata = metadata
    self.resume_test = True

  def _UpdateMetadata(self, **kwargs):
    self.metadata.update(kwargs)
    tmp = self.metadata_file + '.tmp'
    with open(tmp, 'w') as f:
      yaml.dump(self.metadata, f, default_flow_style=False)
    os.rename(tmp, self.metadata_file)

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
      with open(self.log_path, 'ab', 0) as log:
        print('Running test: %s' % self.test.path, file=log)
        self.env_additions['CROS_PROC_TITLE'] = (
            '%s.py (factory pytest %s)' % (pytest_name, self.output_dir))

        env = dict(os.environ)
        env.update(self.env_additions)
        with self._lock:
          if self._aborted:
            return TestState.FAILED, (
                'Before starting: %s' % self._AbortedMessage())

          self._process = self.goofy.pytest_prespawner.spawn(
              PytestInfo(test_list=self.goofy.options.test_list,
                         path=self.test.path,
                         pytest_name=pytest_name,
                         args=self.resolved_dargs,
                         results_path=results_path,
                         dut_options=self.dut_options),
              self.env_additions)

        def _LineCallback(line):
          log.write(line + '\n')
          sys.stderr.write('%s> %s\n' % (self.test.path.encode('utf-8'), line))

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
          return TestState.FAILED, (
              'Test returned code %d' % self._process.returncode)

      if not os.path.exists(results_path):
        return TestState.FAILED, 'pytest did not complete'

      with open(results_path) as f:
        return pickle.load(f)
    except Exception:
      logging.exception('Unable to retrieve pytest results')
      return TestState.FAILED, 'Unable to retrieve pytest results'
    finally:
      for f in files_to_delete:
        try:
          if os.path.exists(f):
            os.unlink(f)
        except Exception:
          logging.exception('Unable to delete temporary file %s', f)

  def _ConvertLogArgs(self, log_args, status):
    """Converts log_args dictionary into a station.test_run event object.

    Args:
      log_args: Legacy dictionary passed into event_log.Log.
      status: The status defined in either cros.factory.test.factory.TestState
              or testlog.StationTestRun.STATUS.

    Returns:
      A testlog.StationTestRun.
    """
    # Convert status
    _status_conversion = {
        # TODO(itspeter): No mapping for STARTING ?
        TestState.ACTIVE: testlog.StationTestRun.STATUS.RUNNING,
        TestState.PASSED: testlog.StationTestRun.STATUS.PASS,
        TestState.FAILED: testlog.StationTestRun.STATUS.FAIL,
        TestState.UNTESTED: testlog.StationTestRun.STATUS.UNKNOWN,
        # TODO(itspeter): Consider adding another status.
        TestState.FAILED_AND_WAIVED: testlog.StationTestRun.STATUS.PASS,
        TestState.SKIPPED: testlog.StationTestRun.STATUS.PASS}

    log_args = copy.deepcopy(log_args)  # Make sure it is intact
    log_args.pop('status', None)  # Discard the status
    log_args.pop('invocation')  # Discard the invocation
    test_name = log_args.pop('path')
    test_type = log_args.pop('pytest_name')

    # If the status is not in _status_conversion, assume it is already a Testlog
    # StationTestRun status.
    status = _status_conversion.get(status, status)

    def GetDUTDeviceID(dut):
      if not dut.link.IsReady():
        return 'device-offline'
      device_id = dut.info.device_id
      # TODO(chuntsen): If the dutDeviceId won't be None anymore, remove this.
      if not isinstance(device_id, basestring):
        logging.error('DUT device ID is an unexpected type (%s)',
                      type(device_id))
        device_id = str(device_id)
      return device_id

    kwargs = {
        'dutDeviceId': GetDUTDeviceID(self.dut),
        'stationDeviceId': session.GetDeviceID(),
        'stationInstallationId': session.GetInstallationID(),
        'testRunId': self.uuid,
        'testName': test_name,
        'testType': test_type,
        'status': status,
        'startTime': self.start_time
    }

    testlog_event = testlog.StationTestRun()
    if 'duration' in log_args:
      log_args.pop('duration')  # Discard the duration
      kwargs['endTime'] = self.end_time
      kwargs['duration'] = self.end_time - self.start_time
    testlog_event.Populate(kwargs)

    dargs = log_args.pop('dargs', None)
    if dargs:
      # Only allow types that can be natively expressed in JSON.
      flattened_dargs = testlog_utils.FlattenAttrs(
          dargs, allow_types=(int, long, float, basestring, type(None)))
      for k, v in flattened_dargs:
        testlog_event.AddArgument(k, v)

    serial_numbers = log_args.pop('serial_numbers', None)
    if serial_numbers:
      for k, v in serial_numbers.iteritems():
        testlog_event.AddSerialNumber(k, v)

    if status == testlog.StationTestRun.STATUS.FAIL:
      for err_field, failure_code in [('error_msg', 'GoofyErrorMsg'),
                                      ('log_tail', 'GoofyLogTail')]:
        if err_field in log_args:
          testlog_event.AddFailure(failure_code, log_args.pop(err_field))

    if 'tag' in log_args:
      testlog_event.LogParam(name='tag', value=log_args.pop('tag'))
      testlog_event.UpdateParam(name='tag',
                                description='Indicate type of shutdown')

    if log_args:
      logging.error('Unexpected fields in logs_args: %s',
                    pprint.pformat(log_args))
      for key, value in log_args.iteritems():
        testlog_event.LogParam(name=key, value=repr(value))
        testlog_event.UpdateParam(name=key, description='UnknownGoofyLogArgs')
    return testlog_event

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

    service_manager = ServiceManager()
    service_manager.SetupServices(enable_services=self.test.enable_services,
                                  disable_services=self.test.disable_services)

    status, error_msg = None, None

    # Resume the previously-running test.
    if self.resume_test:
      self.start_time = self.metadata['start_time']
      self.resolved_dargs = self.metadata['dargs']
      log_args = dict(
          path=self.metadata['path'],
          dargs=self.resolved_dargs,
          serial_numbers=self.metadata['serial_numbers'],
          invocation=self.uuid)
      if self.test.pytest_name:
        log_args['pytest_name'] = self.metadata['pytest_name']
      if isinstance(self.test, test_object.ShutdownStep):
        log_args['tag'] = 'post-shutdown'

      try:
        self.goofy.event_log.Log('resume_test', **log_args)
        self.session_json_path = testlog.InitSubSession(
            log_root=paths.DATA_LOG_DIR,
            station_test_run=self._ConvertLogArgs(
                log_args, TestState.ACTIVE),
            uuid=self.uuid)
        log_args.pop('dargs', None)  # We need to avoid duplication
        log_args.pop('serial_numbers', None)  # We need to avoid duplication
        log_args.pop('tag', None)  # We need to avoid duplication
        self.env_additions[
            testlog.TESTLOG_ENV_VARIABLE_NAME] = self.session_json_path

        # Log a STARTING event.
        testlog.LogTestRun(self.session_json_path, self._ConvertLogArgs(
            log_args, testlog.StationTestRun.STATUS.STARTING))
      except Exception:
        logging.exception('Unable to log resume_test event')

      syslog.syslog('Test %s (%s) resuming' % (
          self.test.path, self.uuid))

    # Not resuming the previously-running test.
    else:
      try:
        logging.debug('Resolving self.test.dargs from test list [%s]...',
                      self.goofy.options.test_list)
        self.resolved_dargs = ResolveTestArgs(
            self.goofy,
            self.test,
            test_list_id=self.goofy.options.test_list,
            dut_options=self.dut_options)
      except Exception as e:
        logging.exception('Unable to resolve test arguments')
        # Although the test is considered failed already,
        # let's still follow the normal path, so everything is logged properly.
        status = TestState.FAILED
        error_msg = 'Unable to resolve test arguments: %s' % e
        self.resolved_dargs = None

      log_args = dict(
          path=self.test.path,
          dargs=self.resolved_dargs,
          serial_numbers=device_data.GetAllSerialNumbers(),
          invocation=self.uuid)
      if self.test.pytest_name:
        log_args['pytest_name'] = self.test.pytest_name
      if isinstance(self.test, test_object.ShutdownStep):
        log_args['tag'] = 'pre-shutdown'

      self.start_time = time.time()
      self._UpdateMetadata(start_time=self.start_time, **log_args)

      try:
        self.goofy.event_log.Log('start_test', **log_args)
        # TODO(itspeter): Change the state to StationTestRun.STATUS.RUNNING
        #                 and flush for the first event to observe if any
        #                 test session is missing.
        self.session_json_path = testlog.InitSubSession(
            log_root=paths.DATA_LOG_DIR,
            station_test_run=self._ConvertLogArgs(
                log_args, TestState.ACTIVE),
            uuid=self.uuid)
        log_args.pop('dargs', None)  # We need to avoid duplication
        log_args.pop('serial_numbers', None)  # We need to avoid duplication
        log_args.pop('tag', None)  # We need to avoid duplication
        self.env_additions[
            testlog.TESTLOG_ENV_VARIABLE_NAME] = self.session_json_path

        # Log a STARTING event.
        testlog.LogTestRun(self.session_json_path, self._ConvertLogArgs(
            log_args, testlog.StationTestRun.STATUS.STARTING))
      except Exception:
        logging.exception('Unable to log start_test event')

      syslog.syslog('Test %s (%s) starting' % (
          self.test.path, self.uuid))

    try:
      if status is None:  # dargs are successfully resolved
        if self.test.pytest_name:
          status, error_msg = self._InvokePytest()
        else:
          status = TestState.FAILED
          error_msg = 'No pytest_name'
    finally:
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

      try:
        # Leave all items in log_args; this duplicates
        # things but will make it easier to grok the output.
        self.end_time = time.time()
        log_args.update(dict(status=status,
                             duration=(self.end_time - self.start_time)))
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
          except Exception:
            logging.exception('Unable to read log tail')

        self.goofy.event_log.Log('end_test', **log_args)
        self._UpdateMetadata(end_time=self.end_time, **log_args)

        testlog.LogFinalTestRun(self.session_json_path, self._ConvertLogArgs(
            log_args, status))
        del self.env_additions[testlog.TESTLOG_ENV_VARIABLE_NAME]

      except Exception:
        logging.exception('Unable to log end_test event')

    service_manager.RestoreServices()

    if isinstance(self.test, test_object.ShutdownStep):
      logging.info(u'Test %s%s (%s) %s', self.test.path, iteration_string,
                   ('post-shutdown' if self.resume_test else 'pre-shutdown'),
                   ': '.join([status, error_msg]))
    else:
      logging.info(u'Test %s%s %s', self.test.path, iteration_string,
                   ': '.join([status, error_msg]))

    decrement_iterations_left = 0
    decrement_retries_left = 0

    if status == TestState.FAILED:
      if self.test.waived:
        status = TestState.FAILED_AND_WAIVED
      reason = error_msg.split('\n')[0]
      session.console.error('Test %s%s %s: %s', self.test.path,
                            iteration_string, status, reason)
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
      self.goofy.RunEnqueue(self.on_test_failure)
    if self.on_completion:
      self.goofy.RunEnqueue(self.on_completion)
