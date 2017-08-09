#!/usr/bin/python -u
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Classes and Methods related to invoking a test."""

from __future__ import print_function

import copy
import cPickle as pickle
import datetime
import logging
import os
import pprint
import re
import signal
import sys
import tempfile
import threading
import time
import traceback
import unittest

import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.env import paths
from cros.factory.test.event import Event
from cros.factory.test import factory
from cros.factory.test.factory import TestState
from cros.factory.test.rules.privacy import FilterDict
from cros.factory.test import state
from cros.factory.test.test_lists import manager
from cros.factory.test import test_ui
from cros.factory.test import testlog_goofy
from cros.factory.test.utils.pytest_utils import LoadPytestModule
from cros.factory.testlog import testlog
from cros.factory.testlog import testlog_utils
from cros.factory.utils.arg_utils import Args
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils.service_utils import ServiceManager
from cros.factory.utils.string_utils import DecodeUTF8
from cros.factory.utils import time_utils

# pylint: disable=no-name-in-module
from cros.factory.external.setproctitle import setproctitle
from cros.factory.external import syslog

# Number of bytes to include from the log of a failed test.
ERROR_LOG_TAIL_LENGTH = 8 * 1024

# pylint: disable=bare-except

# A file that stores override test list dargs for factory test automation.
OVERRIDE_TEST_LIST_DARGS_FILE = os.path.join(
    paths.DATA_STATE_DIR, 'override_test_list_dargs.yaml')


# Dummy object to detect not set keyward argument.
_DEFAULT_NOT_SET = object()


class InvocationError(Exception):
  """Invocation error."""
  pass


class TestArgEnv(object):
  """Environment for resolving test arguments.

  Properties:
    state: Instance to obtain factory test.
    device_data: Cached device data from state_instance.
  """

  def __init__(self):
    self.state = state.get_instance()
    self.device_data_selector = device_data.GetDeviceDataSelector()

  def GetMACAddress(self, interface):
    return open('/sys/class/net/%s/address' % interface).read().strip()

  def GetDeviceData(self, key, default=_DEFAULT_NOT_SET):
    """Returns device data of given key."""
    if not key:
      raise KeyError('empty key')
    if default == _DEFAULT_NOT_SET:
      return self.device_data_selector.GetValue(key)
    else:
      return self.device_data_selector.GetValue(key, default)

  def GetAllDeviceData(self):
    return self.device_data_selector.Get({})

  def GetSerialNumber(self, name=device_data.NAME_SERIAL_NUMBER):
    """Returns serial number.

    Use `name` to specify which type of serial number you want, e.g.
    'mlb_serial_number'.  The default name will be 'serial_number'.

    Return: str or None (if not found)
    """
    if not name:
      raise KeyError('empty name')
    return device_data.GetSerialNumber(name)

  def GetAllSerialNumbers(self):
    return device_data.GetAllSerialNumbers()

  def InEngineeringMode(self):
    """Returns if goofy is in engineering mode."""
    return state.get_shared_data('engineering_mode')


def ResolveTestArgs(goofy, test, test_list_id, dut_options):
  """Resolves an argument dictionary.

  For LegacyTestList, value can be callable, which has function signature:

    lambda env: body

  Where env will be a TestArgEnv object.  These callable values will be
  executed, and replaced by evaluation result.

  For instance:

    dargs={
        'method': 'eval! constants.method_name',
        'args': lambda env: [
            env.GetSerialNumber('mlb_serial_number'),
            env.GetSerialNumber(),
            env.GetMACAddress('wlan0'),
        ]
    }

  This will be resolved to:

    dargs={
        'method': 'eval! constants.method_name',
        'args': ['MLB12345', 'X67890', '00:11:22:33:44:55']
    }

  Then the dargs will be passed to test_list.ResolveTestArgs(), which will
  evaluate values start with 'eval! ' and 'i18n! '.

  Args:
    dargs: An test argument dictionary from the test list.

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

  if isinstance(test_list, manager.LegacyTestList):
    # TODO(stimim): remove all lambda functions in generic test list.
    def ResolveArg(k, v):
      """Resolves a single argument if it is callable."""
      if not callable(v):
        return v

      v = v(TestArgEnv())
      logging.info('Resolved argument %s to %r', k, FilterDict(v))
      return v

    # resolve all lambda functions
    dargs = dict((k, ResolveArg(k, v)) for k, v in dargs.iteritems())

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
    automation_mode: The enabled automation mode.
    dut_options: The options to override default DUT target.
  """

  def __init__(self, test_list, path, pytest_name, args, results_path,
               automation_mode=None, dut_options=None):
    self.test_list = test_list
    self.path = path
    self.pytest_name = pytest_name
    self.args = args
    self.results_path = results_path
    self.automation_mode = automation_mode
    self.dut_options = dut_options or {}

  def ReadTestList(self):
    """Reads and returns the test list."""
    mgr = manager.Manager()

    test_list = mgr.GetTestListByID(self.test_list)

    if test_list is None:
      # the test list is not available, try to load legacy test lists
      # (test list v2).  We need to build *all* test lists because in legacy
      # test lists, a python file can define multiple test lists (with different
      # IDs, of course).
      legacy_test_lists, unused_errors = mgr.BuildAllLegacyTestLists()
      test_list = legacy_test_lists[self.test_list]
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
        target=self._run, name='TestInvocation-%s' % self.test.path)
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
                          'CROS_FACTORY_TEST_PARENT_INVOCATION': self.uuid,
                          'CROS_FACTORY_TEST_METADATA': self.metadata_file}

    # Resuming from an active shutdown test, try to restore its metadata file.
    if state.get_shared_data(key_post_shutdown):
      try:
        self.load_metadata()
      except Exception:
        logging.exception('Failed to load metadata from active shutdown test; '
                          'will continue, but logs will be inaccurate')

    if not self.resume_test:
      self.metadata = {}
      self.update_metadata(path=test.path,
                           init_time=time.time(),
                           invocation=str(self.uuid),
                           label=test.label)

    self.count = None
    self.log_path = os.path.join(self.output_dir, 'log')
    self.update_state_on_completion = {}
    self.dut_options = self._resolve_dut_options()

    self._lock = threading.Lock()
    # The following properties are guarded by the lock.
    self._aborted = False
    self._aborted_reason = None
    self._completed = False
    self._process = None

  def __repr__(self):
    return 'TestInvocation(_aborted=%s, _completed=%s)' % (
        self._aborted, self._completed)

  def load_metadata(self):
    def _ValidateMetadata(metadata):
      REQUIRED_FIELDS = ['path', 'dargs', 'invocation',
                         'label', 'init_time', 'start_time']
      for field in REQUIRED_FIELDS:
        if field not in metadata:
          raise Exception('metadata missing field %s' % field)
      if self.test.pytest_name and 'pytest_name' not in metadata:
        raise Exception('metadata missing field pytest_name')
      return True

    with open(self.metadata_file, 'r') as f:
      metadata = yaml.load(f)
    if _ValidateMetadata(metadata):
      self.metadata = metadata
      self.resume_test = True

  def update_metadata(self, **kwargs):
    self.metadata.update(kwargs)
    tmp = self.metadata_file + '.tmp'
    with open(tmp, 'w') as f:
      yaml.dump(self.metadata, f, default_flow_style=False)
    os.rename(tmp, self.metadata_file)

  def start(self):
    """Starts the test threads."""
    self.thread.start()

  def abort_and_join(self, reason=None):
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

  def is_completed(self):
    """Returns true if the test has finished."""
    return self._completed

  def _aborted_message(self):
    """Returns an error message describing why the test was aborted."""
    return 'Aborted' + (
        (': ' + self._aborted_reason) if self._aborted_reason else '')

  def _resolve_dut_options(self):
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
    self.dut_options = dut_options

  def _invoke_pytest(self, resolved_dargs):
    """Invokes a pyunittest-based test."""
    assert self.test.pytest_name

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
      if self.goofy.options.automation_mode != AutomationMode.NONE:
        # Load override test list dargs if OVERRIDE_TEST_LIST_DARGS_FILE exists.
        if os.path.exists(OVERRIDE_TEST_LIST_DARGS_FILE):
          with open(OVERRIDE_TEST_LIST_DARGS_FILE) as f:
            override_dargs_from_file = yaml.safe_load(f.read())
          resolved_dargs.update(
              override_dargs_from_file.get(self.test.path, {}))
        logging.warn(resolved_dargs)

        if self.test.has_automator:
          logging.info('Enable factory test automator for %r', pytest_name)
          if os.path.exists(os.path.join(
              paths.FACTORY_DIR, 'py', 'test', 'pytests',
              pytest_name, pytest_name + '_automator_private.py')):
            pytest_name += '_automator_private'
          elif os.path.exists(os.path.join(
              paths.FACTORY_DIR, 'py', 'test', 'pytests',
              pytest_name, pytest_name + '_automator.py')):
            pytest_name += '_automator'
          else:
            raise InvocationError('Cannot find automator for %r' % pytest_name)

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
                'Before starting: %s' % self._aborted_message())

          self._process = self.goofy.pytest_prespawner.spawn(
              PytestInfo(test_list=self.goofy.options.test_list,
                         path=self.test.path,
                         pytest_name=pytest_name,
                         args=resolved_dargs,
                         results_path=results_path,
                         automation_mode=self.goofy.options.automation_mode,
                         dut_options=self.dut_options),
              self.env_additions)

        # Tee process's stderr to both the log and our stderr; this
        # will end when the process dies.
        while True:
          line = self._process.stdout.readline()
          if not line:
            break
          log.write(line)
          sys.stderr.write('%s> %s' % (self.test.path.encode('utf-8'), line))

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
    except Exception:
      logging.exception('Unable to retrieve pytest results')
      return TestState.FAILED, 'Unable to retrieve pytest results'
    finally:
      for f in files_to_delete:
        try:
          if os.path.exists(f):
            os.unlink(f)
        except Exception:
          logging.exception('Unable to delete temporary file %s',
                            f)

  def _invoke_target(self):
    """Invokes a target directly within Goofy."""
    try:
      self.test.invocation_target(self)
      return TestState.PASSED, ''
    except Exception:
      logging.exception('Exception while invoking target')

      if sys.exc_info()[0] == factory.FactoryTestFailure:
        # Use the status from the exception.
        status = sys.exc_info()[1].status
      else:
        status = TestState.FAILED

      return status, traceback.format_exc()

  def _convert_log_args(self, log_args, status):
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
        TestState.PASSED: testlog.StationTestRun.STATUS.PASSED,
        TestState.FAILED: testlog.StationTestRun.STATUS.FAILED,
        TestState.UNTESTED: testlog.StationTestRun.STATUS.UNKNOWN,
        # TODO(itspeter): Consider adding another status.
        TestState.FAILED_AND_WAIVED: testlog.StationTestRun.STATUS.PASSED,
        TestState.SKIPPED: testlog.StationTestRun.STATUS.PASSED}

    log_args = copy.deepcopy(log_args)  # Make sure it is intact
    log_args.pop('status', None)  # Discard the status
    log_args.pop('invocation')  # Discard the invocation
    test_name = log_args.pop('path')
    test_type = log_args.pop('pytest_name')

    # If the status is not in _status_conversion, assume it is already a Testlog
    # StationTestRun status.
    status = _status_conversion.get(status, status)

    kwargs = {
        'stationDeviceId': testlog_goofy.GetDeviceID(),
        'stationInstallationId': testlog_goofy.GetInstallationID(),
        'testRunId': self.uuid,
        'testName': test_name,
        'testType': test_type,
        'status': status,
        'startTime': datetime.datetime.fromtimestamp(self.start_time)
    }

    dargs = log_args.pop('dargs', None)
    if dargs:
      # Only allow types that can be natively expressed in JSON.
      flattened_dargs = testlog_utils.FlattenAttrs(
          dargs, allow_types=(int, long, float, basestring, type(None)))
      dargs = {k: {'value': v} for k, v in flattened_dargs}
      kwargs['arguments'] = dargs
    if 'duration' in log_args:
      log_args.pop('duration')  # Discard the duration
      kwargs['endTime'] = datetime.datetime.fromtimestamp(self.end_time)
      kwargs['duration'] = self.end_time - self.start_time

    serial_numbers = log_args.pop('serial_numbers', None)
    if serial_numbers:
      kwargs['serialNumbers'] = serial_numbers

    testlog_event = testlog.StationTestRun()
    testlog_event.Populate(kwargs)
    if status == testlog.StationTestRun.STATUS.FAILED:
      for err_field, failure_code in [('error_msg', 'GoofyErrorMsg'),
                                      ('log_tail', 'GoofyLogTail')]:
        if err_field in log_args:
          testlog_event.AddFailure(failure_code, log_args.pop(err_field))

    if 'tag' in log_args:
      testlog_event.LogParam(
          name='tag', value=log_args.pop('tag'),
          description='Indicate type of shutdown')

    if len(log_args) > 0:
      logging.error('Unexpected fields in logs_args: %s',
                    pprint.pformat(log_args))
      for key, value in log_args.iteritems():
        testlog_event.LogParam(name=key, value=repr(value),
                               description='UnknownGoofyLogArgs')
    return testlog_event

  def _run(self):
    with self._lock:
      if self._aborted:
        return

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

    try:
      # *WARNING* test metadata is not initialized at this point, please don't
      # use it in prepare function.
      if self.test.prepare:
        self.test.prepare()
    except Exception:
      logging.exception('Exception while invoking prepare callback %s',
                        traceback.format_exc())

    # During the preparation, if a severe error occurs,
    # you can set status to TestState.FAILED, then the test won't be invoked.
    status, error_msg = None, None

    # Resume the previously-running test.
    if self.resume_test:
      self.start_time = self.metadata['start_time']
      resolved_dargs = self.metadata['dargs']
      log_args = dict(
          path=self.metadata['path'],
          dargs=resolved_dargs,
          serial_numbers=self.metadata['serial_numbers'],
          invocation=self.uuid)
      if self.test.pytest_name:
        log_args['pytest_name'] = self.metadata['pytest_name']
      if isinstance(self.test, factory.ShutdownStep):
        log_args['tag'] = 'post-shutdown'

      try:
        self.goofy.event_log.Log('resume_test', **log_args)
        self.session_json_path = testlog.InitSubSession(
            log_root=paths.DATA_LOG_DIR,
            station_test_run=self._convert_log_args(
                log_args, TestState.ACTIVE),
            uuid=self.uuid)
        log_args.pop('dargs', None)  # We need to avoid duplication
        log_args.pop('serial_numbers', None)  # We need to avoid duplication
        log_args.pop('tag', None)  # We need to avoid duplication
        self.env_additions[
            testlog.TESTLOG_ENV_VARIABLE_NAME] = self.session_json_path

        # Log a STARTING event.
        testlog.LogTestRun(self.session_json_path, self._convert_log_args(
            log_args, testlog.StationTestRun.STATUS.STARTING))
      except Exception:
        logging.exception('Unable to log resume_test event')

      syslog.syslog('Test %s (%s) resuming' % (
          self.test.path, self.uuid))

    # Not resuming the previously-running test.
    else:
      logging.debug('Resolving self.test.dargs...')
      try:
        logging.info('test list: %s', self.goofy.options.test_list)
        resolved_dargs = ResolveTestArgs(
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
        resolved_dargs = None

      log_args = dict(
          path=self.test.path,
          dargs=resolved_dargs,
          serial_numbers=device_data.GetAllSerialNumbers(),
          invocation=self.uuid)
      if self.test.pytest_name:
        log_args['pytest_name'] = self.test.pytest_name
      if isinstance(self.test, factory.ShutdownStep):
        log_args['tag'] = 'pre-shutdown'

      self.start_time = time.time()
      self.update_metadata(start_time=self.start_time, **log_args)

      try:
        self.goofy.event_log.Log('start_test', **log_args)
        # TODO(itspeter): Change the state to StationTestRun.STATUS.RUNNING
        #                 and flush for the first event to observe if any
        #                 test session is missing.
        self.session_json_path = testlog.InitSubSession(
            log_root=paths.DATA_LOG_DIR,
            station_test_run=self._convert_log_args(
                log_args, TestState.ACTIVE),
            uuid=self.uuid)
        log_args.pop('dargs', None)  # We need to avoid duplication
        log_args.pop('serial_numbers', None)  # We need to avoid duplication
        log_args.pop('tag', None)  # We need to avoid duplication
        self.env_additions[
            testlog.TESTLOG_ENV_VARIABLE_NAME] = self.session_json_path

        # Log a STARTING event.
        testlog.LogTestRun(self.session_json_path, self._convert_log_args(
            log_args, testlog.StationTestRun.STATUS.STARTING))
      except Exception:
        logging.exception('Unable to log start_test event')

      syslog.syslog('Test %s (%s) starting' % (
          self.test.path, self.uuid))

    try:
      if status is None:  # dargs are successfully resolved
        if self.test.pytest_name:
          status, error_msg = self._invoke_pytest(resolved_dargs)
        elif self.test.invocation_target:
          status, error_msg = self._invoke_target()
        else:
          status = TestState.FAILED
          error_msg = 'No pytest_name, or invocation_target'
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
        self.update_metadata(end_time=self.end_time, **log_args)

        testlog.LogFinalTestRun(self.session_json_path, self._convert_log_args(
            log_args, status))
        del self.env_additions[testlog.TESTLOG_ENV_VARIABLE_NAME]

      except Exception:
        logging.exception('Unable to log end_test event')

    service_manager.RestoreServices()

    if isinstance(self.test, factory.ShutdownStep):
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
      factory.console.error('Test %s%s %s: %s', self.test.path,
                            iteration_string, status, reason)
      decrement_retries_left = 1
    elif status == TestState.PASSED:
      decrement_iterations_left = 1

    try:
      if self.test.finish:
        self.test.finish(status)
    except Exception:
      logging.exception('Exception while invoking finish_callback %s',
                        traceback.format_exc())

    with self._lock:
      self.update_state_on_completion = dict(
          status=status, error_msg=error_msg,
          visible=False, decrement_iterations_left=decrement_iterations_left,
          decrement_retries_left=decrement_retries_left)
      self._completed = True

    self.goofy.run_queue.put(self.goofy.reap_completed_tests)
    if status == TestState.FAILED:
      self.goofy.run_queue.put(self.on_test_failure)
    if self.on_completion:
      self.goofy.run_queue.put(self.on_completion)


# The functions above is used when invocation is imported as module, and
# functions below is used when invocation is run as a standalone script (by
# prespawner).
# TODO(pihsun): Move codes below to another file.


def RunTestCase(test_case):
  """Runs the given test case.

  This is the actual test case runner.  It runs the test case and returns the
  test results.

  Args:
    test_case: The test case to run.

  Returns:
    The test result of the test case.
  """
  logging.debug('[%s] Really run test case: %s', os.getpid(),
                test_case.id())
  # We need a new invocation uuid here to have a new UI context for each
  # test case subprocess.
  # The parent uuid is stored in CROS_FACTORY_TEST_PARENT_INVOCATION env
  # variable, and we can properly clean up all associated invocations at
  # test frontend using the parent invocation uuid.
  os.environ['CROS_FACTORY_TEST_INVOCATION'] = time_utils.TimedUUID()
  result = unittest.TestResult()
  test_case.run(result)
  return result


def RunPytest(test_info):
  """Runs a pytest, saving a pickled (status, error_msg) tuple to the
  appropriate results file.

  Args:
    test_info: A PytestInfo object containing information about what to
      run.
  """
  try:
    # Register a handler for SIGTERM, so that Python interpreter has
    # a chance to do clean up procedures when SIGTERM is received.
    def _SIGTERMHandler(signum, frame):  # pylint: disable=unused-argument
      logging.error('SIGTERM received')
      raise factory.FactoryTestFailure('SIGTERM received')

    signal.signal(signal.SIGTERM, _SIGTERMHandler)

    module = LoadPytestModule(test_info.pytest_name)
    suite = unittest.TestLoader().loadTestsFromModule(module)

    # An example of the TestSuite returned by loadTestsFromModule:
    #   TestSuite
    #   - TestSuite (class XXXTest(unittest.TestCase))
    #     - TestCase (XXXTest.runTest)
    #   - TestSuite (class YYYTest(unittest.TestCase))
    #     - TestCase (YYYTest.testAAA)
    #     - TestCase (YYYTest.testBBB)
    # The countTestCases() would return 3 in this example.

    # To simplify things, we only allow one TestCase per pytest.
    if suite.countTestCases() != 1:
      raise factory.FactoryTestFailure(
          'Only one TestCase per pytest is supported. Use factory_task '
          'if multiple tasks need to be done in a single pytest.')

    # The first sub-TestCase in the first sub-TestSuite of suite is the target.
    test = next(iter(next(iter(suite))))

    logging.debug('[%s] Start test case: %s', os.getpid(), test.id())

    test.test_info = test_info
    if test_info.dut_options:
      os.environ.update({
          device_utils.ENV_DUT_OPTIONS: str(test_info.dut_options)})
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

    result = RunTestCase(test)

    def FormatErrorMessage(trace):
      """Formats a trace so that the actual error message is in the last line.
      """
      # The actual error is in the last line.
      trace, _, error_msg = trace.strip().rpartition('\n')
      error_msg = error_msg.replace('FactoryTestFailure: ', '')
      return error_msg + '\n' + trace

    all_failures = result.failures + result.errors + test_ui.exception_list
    if all_failures:
      status = TestState.FAILED
      error_msg = '\n'.join(FormatErrorMessage(trace)
                            for test_name, trace in all_failures)
      logging.info('pytest failure: %s', error_msg)
    else:
      status = TestState.PASSED
      error_msg = ''
  except Exception:
    logging.exception('Unable to run pytest')
    status = TestState.FAILED
    error_msg = traceback.format_exc()

  with open(test_info.results_path, 'w') as results:
    pickle.dump((status, error_msg), results)


def main():
  env, info = pickle.load(sys.stdin)
  if not env:
    sys.exit(0)
  os.environ.update(env)

  factory.init_logging(info.path)
  if testlog.TESTLOG_ENV_VARIABLE_NAME in os.environ:
    testlog.Testlog(
        stationDeviceId=testlog_goofy.GetDeviceID(),
        stationInstallationId=testlog_goofy.GetInstallationID())
  else:
    # If the testlog.TESTLOG_ENV_VARIABLE_NAME environment variable doesn't
    # exist, assume invocation is being called by run_test.py.  In this case,
    # this is expected behaviour, since run_test.py doesn't save logs.
    logging.info('Logging for Testlog is not able to start')

  proc_title = os.environ.get('CROS_PROC_TITLE')
  if proc_title:
    setproctitle(proc_title)
  RunPytest(info)

if __name__ == '__main__':
  main()
