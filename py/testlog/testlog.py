# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Python implementation of testlog JSON API.

Testlog (deprecates event_log) is designed to
- Define a stricter API that unifined logging action across different tests.
- More friendly for third-party to use.

File hierarchy and relation between event_log.py:
TODO(itspeter): Remove event_log related path once phased out.
TODO(itspeter): Move to Instalog folder and remove the dependency of
                factory framework

[DATA_DIR] ─── .device_id
[LOG_ROOT]─┬─ testlog.json
           ├─ init_count
           ├─ installation_id
           ├─ events/ ─┬─ .boot_sequence
           │   (Legacy │   (legacy file, replaced by [LOG_ROOT]/init_count)
           │           ├─ .reimage_id
           │           │   (legacy file, replaced by [LOG_ROOT]/installation_id)
           │           └─ events
           │               (legacy file, replaced by [LOG_ROOT]/testlog.json)
           │
           ├─ running/ ─┬─ [UUID]-session.json
           │            ├─ [UUID]-session.json
           │            └─ [UUID]-session.json
           └─ attachments/ ─┬─ [binary_file 1]
                            └─ [binary_file N]
[TEMPORARY_FOLDER]─┬─ event_log_seq
                   │    (legacy file, replaced by testlog_seq)
                   └─ testlog_seq
"""

import json
import logging
import os
import re
import tempfile
import threading
import time

from . import hooks
from . import testlog_seq
from . import testlog_utils
from . import testlog_validator
from .utils import file_utils
from .utils import schema
from .utils import sys_utils
from .utils import time_utils
from .utils import type_utils


TESTLOG_API_VERSION = '0.21'
TESTLOG_ENV_VARIABLE_NAME = 'TESTLOG'

# Possible values for the `Stationstatus.parameters.type` field.
PARAM_TYPE = type_utils.Enum(['argument', 'measurement'])

# TODO(itspeter): Use config_utils for those default constants.
# The primary JSON file. It will be ingested by Instalog.
_DEFAULT_PRIMARY_JSON_FILE = 'testlog.json'
# The default template path for session JSON from log_root.
# Expected life cycle of a single test run. Parent process must call
# InitForChildProcess before invoking the new process.
_DEFAULT_SESSION_FOLDER = 'running'
_DEFAULT_SESSION_JSON_FILE_TEMPLATE = '%s-session.json'
# The default path for binary attachments from log_root.
_DEFAULT_ATTACHMENTS_FOLDER = 'attachments'

# This directory need to be cleared on each boot.
# The /run directory (or something writable by us if in the chroot).
# TODO(itspeter): Survey if we can find an equivalent folder in Windows.
#                 Otherwise, the SEQ_INCREMENT_ON_BOOT magic might not work.
_TMP_DIR = (os.environ.get('CROS_FACTORY_RUN_PATH') or
            (tempfile.gettempdir() if sys_utils.InChroot() else '/run'))

# File containing the next sequence number to write. This is in
# /run so it is cleared on each boot.
_SEQUENCE_PATH = os.path.join(_TMP_DIR, 'testlog_seq')

# Use the lock to avoid two threads creating multiple writers.
_log_related_lock = threading.RLock()

# A global testlog writer. Since we expect each test is invoked
# separately as a process, each test will have their own 'global'
# testlog writer with a unique ID.
_global_testlog = None

_pylogger = None
_pylogger_handler = None

_update_session_json = threading.Event()


class FlushException(Exception):
  """Represents an exception when flushing to Instalog."""


class Testlog:
  """Primarily a wrapper for variables that should exist in a singleton.

  This class should be initialized only once per process.

  Properties:
    last_test_run: In memory object that keep the same content of session_json.
        They should be the same so when updating the test_run we don't need to
        read and parse from session_json repeatedly.
    log_root: The root folder for logging.
    primary_json: A JSON file that will ingested by Instalog.
    session_json: A temporary JSON file to keep the test_run information.
    attachments_folder: The folder for copying / moving binary files.
    uuid: A unique ID for related to the process that using the testlog.
    seq_generator: A sequence file that expected to increase monotonically
        during test.
  """

  FIELDS = type_utils.Enum([
      'LAST_TEST_RUN', 'LOG_ROOT', 'PRIMARY_JSON', 'SESSION_JSON',
      'ATTACHMENTS_FOLDER', 'UUID', '_METADATA'])

  def __init__(self, log_root=None, uuid=None,
               stationDeviceId=None, stationInstallationId=None):
    """Initializes the Testlog singleton.

    Args:
      log_root: The path to root folder of testlog.
      uuid: A unique ID for this process.
      stationDeviceId: To use in saving Python logging calls.
      stationInstallationId: To use in saving Python logging calls.
    """
    global _global_testlog  # pylint: disable=global-statement
    assert _global_testlog is None, (
        '_global_testlog should be initialized only once before Close().')
    with _log_related_lock:
      _global_testlog = self
    self.instalog_plugin = None
    self.in_subsession = False
    if log_root and uuid:
      # Indicate it initialized from a harness that no one will collect its
      # session JSON file (so set to None)
      session_data = {
          Testlog.FIELDS.LOG_ROOT: log_root,
          Testlog.FIELDS.PRIMARY_JSON:
              os.path.join(log_root, _DEFAULT_PRIMARY_JSON_FILE),
          Testlog.FIELDS.ATTACHMENTS_FOLDER:
              os.path.join(log_root, _DEFAULT_ATTACHMENTS_FOLDER),
          Testlog.FIELDS.UUID: uuid}
    elif not log_root and not uuid:
      # Get the related information from the OS environment variable.
      self.in_subsession = True
      session_data = Testlog._ReadSessionInfo()
    else:
      assert False, (
          'Wrong initialization of _global_testlog with log_root:'
          ' %r, uuid: %r' % (log_root, uuid))

    self.last_test_run = session_data.pop(self.FIELDS.LAST_TEST_RUN, None)
    self.log_root = session_data.pop(self.FIELDS.LOG_ROOT)
    self.primary_json = session_data.pop(self.FIELDS.PRIMARY_JSON)
    self.session_json = session_data.pop(self.FIELDS.SESSION_JSON, None)
    self.attachments_folder = session_data.pop(self.FIELDS.ATTACHMENTS_FOLDER)
    self.uuid = session_data.pop(self.FIELDS.UUID)
    metadata = session_data.pop(
        self.FIELDS._METADATA, None)  # pylint: disable=protected-access
    if metadata:
      # pylint: disable=protected-access
      self.last_test_run[self.FIELDS._METADATA] = metadata
    assert not session_data, 'Not all variable initialized.'

    # Initialize the sequence generator
    self.seq_generator = testlog_seq.SeqGenerator(
        _SEQUENCE_PATH, self.primary_json)
    self._CreateFolders()

    self.hooks = None

    # To avoid deadlock when logging enable debug level.
    thread_data = threading.local()
    # Reload the JSON paths into JSONLogFile for future writing.
    if self.session_json:
      self.session_json = JSONLogFile(
          uuid=self.uuid, seq_generator=self.seq_generator,
          path=self.session_json, thread_data=thread_data, mode='w')
    if self.primary_json:
      self.primary_json = JSONLogFile(
          uuid=self.uuid, seq_generator=self.seq_generator,
          path=self.primary_json, thread_data=thread_data, mode='a',
          check_event=True)
    # Initialize testlog._pylogger
    self.CaptureLogging(stationDeviceId, stationInstallationId)

    if self.in_subsession:
      self.stop_session_json_thread = threading.Event()
      self.session_json_thread = threading.Thread(
          target=self.UpdateSessionJSON)
      self.session_json_thread.start()

  def UpdateSessionJSON(self):
    while (not self.stop_session_json_thread.wait(0.2) or
           _update_session_json.is_set()):
      if _update_session_json.is_set():
        _update_session_json.clear()
        Log(self.last_test_run)

  def init_hooks(self, hooks_class):
    # Initialize the Testlog hooks class
    module, class_name = hooks_class.rsplit('.', 1)
    self.hooks = getattr(__import__(module, fromlist=[class_name]),
                         class_name)()
    assert isinstance(self.hooks, hooks.Hooks), (
        'Testlog hooks should be of type Hooks but is %r' % type(self.hooks))

  def CaptureLogging(self, stationDeviceId=None, stationInstallationId=None):
    """Captures calls to logging.* into primary_json."""
    level = logging.getLogger().getEffectiveLevel()
    def AnnotateAndLog(station_message):
      if stationDeviceId:
        station_message['stationDeviceId'] = stationDeviceId
      if stationInstallationId:
        station_message['stationInstallationId'] = stationInstallationId
      # If we are in a subsession, use the UUID as testRunId.
      if self.in_subsession:
        station_message['testRunId'] = self.uuid
      self.primary_json.Log(station_message)

    CapturePythonLogging(
        callback=AnnotateAndLog, level=level)
    logging.info('Testlog(%s) is capturing logging at level %s',
                 self.uuid, logging.getLevelName(level))

  def Close(self):
    # pylint: disable=global-statement
    global _global_testlog, _pylogger, _pylogger_handler
    if self.in_subsession:
      self.stop_session_json_thread.set()
      self.session_json_thread.join()
    if self.primary_json:
      self.primary_json.Close()
    if self.session_json:
      self.session_json.Close()
    if _global_testlog:
      _global_testlog = None
    if _pylogger and _pylogger_handler:
      _pylogger.removeHandler(_pylogger_handler)
      _pylogger = None
      _pylogger_handler = None

  @staticmethod
  def _ReadSessionInfo():
    session_json_path = os.environ.get(TESTLOG_ENV_VARIABLE_NAME, None)
    assert session_json_path, (
        'Not able to find environment variable %r' % TESTLOG_ENV_VARIABLE_NAME)
    # Read to load metadata.
    metadata = None
    with file_utils.FileLockContextManager(session_json_path, 'r') as fd:
      last_test_run = json.loads(fd.read())
    metadata = last_test_run.pop(
        Testlog.FIELDS._METADATA)  # pylint: disable=protected-access
    return {
        Testlog.FIELDS.LAST_TEST_RUN: Event.FromDict(last_test_run, False),
        Testlog.FIELDS.LOG_ROOT: metadata[Testlog.FIELDS.LOG_ROOT],
        Testlog.FIELDS.PRIMARY_JSON: metadata[Testlog.FIELDS.PRIMARY_JSON],
        Testlog.FIELDS.SESSION_JSON: session_json_path,
        Testlog.FIELDS.ATTACHMENTS_FOLDER:
            metadata[Testlog.FIELDS.ATTACHMENTS_FOLDER],
        Testlog.FIELDS.UUID: metadata[Testlog.FIELDS.UUID],
        Testlog.FIELDS._METADATA: metadata}  # pylint: disable=protected-access

  def _CreateFolders(self):
    for x in [self.log_root, self.attachments_folder]:
      file_utils.TryMakeDirs(x)

  def SetInstalogPlugin(self, instalog_plugin):
    """Sets a reference to the Goofy Instalog plugin."""
    self.instalog_plugin = instalog_plugin

  def Flush(self, uplink=True, local=True, timeout=None):
    """Flushes testlog logs through Instalog.

    Args:
      uplink: Flush the uplink (output_http) plugin.
      local: Flush the local (output_file) plugin.
      timeout: Time to wait before returning with failure.

    Returns:
      If successful, returns True and a string describing the flushing result.
      Otherwise, returns False and a string describing the progress of flushing.

    Raises:
      FlushException if no instalog plugin.
    """
    if self.instalog_plugin is None:
      raise FlushException('Flush: No Instalog plugin available')
    last_seq_output = self.seq_generator.Current()
    input_success, input_result = self.instalog_plugin.FlushInput(
        last_seq_output, timeout)
    if not input_success:
      return False, input_result
    output_success, output_result = self.instalog_plugin.FlushOutput(
        uplink, local, timeout)
    if not output_success:
      return False, output_result
    result = input_result
    result.update(output_result)
    return True, json.dumps(result)


def InitSubSession(log_root, uuid, station_test_run=None):
  """Initializes session JSON file for future test in a separate process.

  This is used for harness to generate the session JSON file for the
  upcoming test. The upcoming test is expected to run in a separate process
  and the path of session JSON file will be passed through environment
  variable TESTLOG_ENV_VARIABLE_NAME.

  Args:
    log_root: Root folder that contains testlog.json, session JSONs
        attachments.
    uuid: Unique ID for the upcoming test run.
    station_test_run: Any existed fields that need to propagate into the new
        test session's station.test_run. For example, can be serial numbers or
        harness-specific information (e.x.: stationDeviceId).

  Returns:
    Path to the session JSON file.
  """
  # TODO(itspeter): Enable more fine setting on the testlog.json location, etc.
  session_log_path = os.path.join(log_root, _DEFAULT_SESSION_FOLDER,
                                  _DEFAULT_SESSION_JSON_FILE_TEMPLATE % uuid)
  file_utils.TryMakeDirs(os.path.dirname(session_log_path))
  if not station_test_run:
    station_test_run = StationTestRun()
    station_test_run.FromDict({
        'status': StationTestRun.STATUS.STARTING,
        'testRunId': uuid,
        'startTime': time.time()
    })
  # pylint: disable=protected-access
  station_test_run[Testlog.FIELDS._METADATA] = {
      Testlog.FIELDS.LOG_ROOT: log_root,
      Testlog.FIELDS.PRIMARY_JSON:
          os.path.join(log_root, _DEFAULT_PRIMARY_JSON_FILE),
      Testlog.FIELDS.SESSION_JSON: session_log_path,
      Testlog.FIELDS.ATTACHMENTS_FOLDER:
          os.path.join(log_root, _DEFAULT_ATTACHMENTS_FOLDER),
      Testlog.FIELDS.UUID: uuid
  }
  with file_utils.FileLockContextManager(session_log_path, 'w') as fd:
    fd.write(station_test_run.ToJSON())
    fd.flush()
    os.fsync(fd.fileno())
  return session_log_path


def CollectExpiredSessions(log_root, station_test_run=None):
  session_dir = os.path.join(log_root, _DEFAULT_SESSION_FOLDER)
  for session_log_path in os.listdir(session_dir):
    session_log_path = os.path.join(session_dir, session_log_path)
    if os.path.isfile(session_log_path):
      LogFinalTestRun(session_log_path, station_test_run)


def LogTestRun(session_json_path, station_test_run=None):
  """Merges the session JSON into the primary JSON and logs it.

  Args:
    session_json_path: Path to the session JSON.
    station_test_run: Additional information might be appended.
  """
  # TODO(itspeter): Check the file is already closed properly. (i.e.
  #                 no lock exists or other process using it)
  with file_utils.FileLockContextManager(session_json_path, 'r+') as fd:
    content = fd.read()
    try:
      session_json = json.loads(content)
      test_run = StationTestRun()
      test_run.Populate(session_json)
      # Merge the station_test_run information.
      if station_test_run:
        test_run.Populate(station_test_run.ToDict())
      if 'startTime' in test_run and 'endTime' in test_run:
        test_run['duration'] = test_run['endTime'] - test_run['startTime']
      Log(test_run)
      # pylint: disable=protected-access
      test_run[Testlog.FIELDS._METADATA] = (
          session_json[Testlog.FIELDS._METADATA])
      fd.seek(0)
      fd.truncate()
      fd.write(test_run.ToJSON())
      fd.flush()
      os.fsync(fd.fileno())
    except Exception:
      # Not much we can do here.
      logging.exception('Not able to collect %s. Last read: %s',
                        session_json_path, content)
      # We should stop the pytest if it failed to log Testlog event.
      raise


def LogFinalTestRun(session_json_path, station_test_run=None):
  LogTestRun(session_json_path, station_test_run)
  os.unlink(session_json_path)


def GetGlobalTestlog():
  """Gets the singleton instance of the global testlog writer."""
  if _global_testlog is None:
    with _log_related_lock:
      if _global_testlog:
        return _global_testlog
      # Oops, the Testlog is not there yet.
      Testlog()
  return _global_testlog


def GetGlobalTestlogLock():
  """Gets locks that used in testlog.

  Functions that want to keep action synchronized with testlog should use
  this lock. For example:
  with GetGlobalTestlogLock():
    # Do log stuff that related to testlog.

  Returns:
    threading.RLock() used in testlog module.
  """
  return _log_related_lock


def Log(event):
  """Logs the event using the global testlog writer.

  This function is essentially a wrapper around JSONLogFile.Log(). It
  creates or reuses the global log writer and calls the JSONLogFile.Log()
  function. Note that this should only be called by other exposed API.

  Args:
    event: An instance of testlog.EventBase.
  """
  # TODO(itspeter): expose flag to override the default flush behavior.
  testlog_singleton = GetGlobalTestlog()
  assert event, 'No event to write'

  if testlog_singleton.hooks:
    if isinstance(event, StationInit):
      testlog_singleton.hooks.OnStationInit(event)
    elif isinstance(event, StationMessage):
      testlog_singleton.hooks.OnStationMessage(event)
    elif isinstance(event, StationTestRun):
      testlog_singleton.hooks.OnStationTestRun(event)

  if not testlog_singleton.in_subsession:
    testlog_singleton.primary_json.Log(event)
  else:
    testlog_singleton.session_json.Log(event, override=True)


def FlushEvent():
  """Flush the last_test_run event to primary JSON file.

  Be careful that this function is slow and the time consumption depends on the
  size of the event. Calling it too often will cause performance issue.
  """
  testlog_singleton = GetGlobalTestlog()
  if testlog_singleton.in_subsession:
    testlog_singleton.primary_json.Log(testlog_singleton.last_test_run)
  else:
    raise testlog_utils.TestlogError(
        'FlushEvent should be called in subsession.')


def _StationTestRunWrapperInSession(*args, **kwargs):
  """Wrapper for StationTestRun method function.

  We provide this wrapper as a handy interface that caller can use
  testlog.foo() instead of GetGlobalTestlog().last_test_run.foo().
  This function is expected to call only in test session but not test harness,
  because only test session expected to have GetGlobalTestlog().last_test_run.

  Please see the StationTestRun for more details.
  """
  method_name = kwargs.pop('_method_name')
  if GetGlobalTestlog().last_test_run:
    ret = getattr(
        GetGlobalTestlog().last_test_run, method_name)(*args, **kwargs)
    _update_session_json.set()
    return ret
  raise testlog_utils.TestlogError(
      'In memory station.test_run does not set. '
      'Test harness need to set it manually.')


def AddSerialNumber(*args, **kwargs):
  kwargs['_method_name'] = 'AddSerialNumber'
  return _StationTestRunWrapperInSession(*args, **kwargs)


def LogParam(*args, **kwargs):
  kwargs['_method_name'] = 'LogParam'
  return _StationTestRunWrapperInSession(*args, **kwargs)


def CheckNumericParam(*args, **kwargs):
  kwargs['_method_name'] = 'CheckNumericParam'
  return _StationTestRunWrapperInSession(*args, **kwargs)


def CheckTextParam(*args, **kwargs):
  kwargs['_method_name'] = 'CheckTextParam'
  return _StationTestRunWrapperInSession(*args, **kwargs)


def GroupParam(*args, **kwargs):
  kwargs['_method_name'] = 'GroupParam'
  return _StationTestRunWrapperInSession(*args, **kwargs)


def AttachFile(*args, **kwargs):
  kwargs['_method_name'] = 'AttachFile'
  return _StationTestRunWrapperInSession(*args, **kwargs)


def AttachContent(*args, **kwargs):
  kwargs['_method_name'] = 'AttachContent'
  return _StationTestRunWrapperInSession(*args, **kwargs)


def UpdateParam(*args, **kwargs):
  kwargs['_method_name'] = 'UpdateParam'
  return _StationTestRunWrapperInSession(*args, **kwargs)


def AddArgument(*args, **kwargs):
  kwargs['_method_name'] = 'AddArgument'
  return _StationTestRunWrapperInSession(*args, **kwargs)


def AddFailure(*args, **kwargs):
  kwargs['_method_name'] = 'AddFailure'
  return _StationTestRunWrapperInSession(*args, **kwargs)


class JSONLogFile(file_utils.FileLockContextManager):
  """Represents a JSON log file on disk."""

  def __init__(self, uuid, seq_generator, path, thread_data,
               mode='a', check_event=False):
    """Constructor.

    Args:
      uuid: A unique ID for the Testlog process.
      seq_generator: A sequence file that expected to increase monotonically
          during test.
      path: Path of the JSON log file.
      thread_data: A threading.local() object to prevent deadlock.
          See http://b/62893425.
      mode: A string indicating how the file is to be opened.
      check_event: Boolean to indicate if we should check the validation of
          each event.
    """
    super(JSONLogFile, self).__init__(path=path, mode=mode)
    self._thread_data = thread_data
    self.test_run_id = uuid
    self.seq_generator = seq_generator
    self.check_event = check_event

  def Log(self, event, override=False):
    """Converts event into JSON string and writes into disk.

    Warning: If this function or any code executed down the call stack makes
    use of Python logging functions, they will be dropped from this function.
    Otherwise, a deadlock will occur.

    Args:
      event: The event to output.
      override: Ture to make sure the JSON log file contains only one event.
    """
    if getattr(self._thread_data, 'in_log', False):
      # We are already in a log call.  Throw out any other subsequent logs
      # until this call finishes.
      return

    self._thread_data.in_log = True

    # Data that should be refreshed on every write operation.
    event['uuid'] = time_utils.TimedUUID()
    event['seq'] = self.seq_generator.Next()
    if 'apiVersion' not in event:
      event['apiVersion'] = TESTLOG_API_VERSION
    if 'time' not in event:
      event['time'] = time.time()

    if self.check_event:
      # Check the event, or it may be rejected by Instalog input plugin.
      try:
        event.CheckIsValid()
      except Exception:
        logging.exception('Not able to log the event: %s', event.ToJSON())
        raise

    line = event.ToJSON() + '\n'
    with self:
      if override:
        self.file.seek(0)
      self.file.write(line)
      if override:
        self.file.truncate()
      self.file.flush()
      os.fsync(self.file.fileno())

    self._thread_data.in_log = False


def CapturePythonLogging(callback, level=logging.DEBUG):
  """Starts capturing Python logging.

  The output events will be sent to the specified callback function.
  This function can only be used once to set up logging -- any subsequent
  calls will return the existing Logger object.

  Args:
    callback: Function to be called when the Python logging library is called.
        It accepts one argument, which will be the StationMessage object as
        constructed by TestlogLogHandler.
    level: Sets minimum verbosity of log messages that will be sent to the
        callback.  Default: logging.DEBUG.
  """
  global _pylogger, _pylogger_handler  # pylint: disable=global-statement
  if _pylogger:
    # We are already capturing Python logging.
    return _pylogger

  _pylogger_handler = TestlogLogHandler(callback)
  _pylogger_handler.setFormatter(LogFormatter())
  _pylogger = logging.getLogger()
  _pylogger.addHandler(_pylogger_handler)
  _pylogger.setLevel(level)
  return _pylogger


class TestlogLogHandler(logging.Handler):
  """Formats records into events and send them to callback function.

  Properties:
    _callback: Function to be called when we have processed the logging message
        and created a StationMessage object.  It accepts one argument, which
        will be the constructed StationMessage object.
    _thread_data: Storage for the local thread.  Used to track whether or not
        the thread is currently in an emit call.
  """

  def __init__(self, callback):
    self._callback = callback
    self._thread_data = threading.local()
    super(TestlogLogHandler, self).__init__()

  def emit(self, record):
    """Formats and emits event record.

    Warning: If this function or any code executed down the call stack makes
    use of Python logging functions, they will be dropped from this log handler.
    Otherwise, an infinite loop will result.
    """
    if getattr(self._thread_data, 'in_emit', False):
      # We are already in an emit call.  Throw out any other subsequent emits
      # until this call finishes.
      return

    if record.name == 'console':
      # logs sent to console (py/test/session.py@console) may be noisy and
      # should be displayed only and not logged.
      return

    self._thread_data.in_emit = True
    event = self.format(record)
    self._callback(event)
    self._thread_data.in_emit = False


class LogFormatter(logging.Formatter):
  """Formats records into events."""

  def format(self, record):
    message = record.getMessage()
    if record.exc_info:
      message += '\n%s' % self.formatException(record.exc_info)

    data = {
        'filePath': getattr(record, 'pathname', None),
        'lineNumber': getattr(record, 'lineno', None),
        'functionName': getattr(record, 'funcName', None),
        'logLevel': getattr(record, 'levelname', None),
        'time': getattr(record, 'created', None),
        'message': message}

    return StationMessage(data)


class EventBase:
  """Base plumbing for Event class.

  Includes functionality to map incoming data (JSON or Python dict) to its
  corresponding Event class, through the GetEventType() method.

  Properties:
    _data: Stores the internal Python dict of this event.  This should be
        equivalent to the dict that gets returned from the ToDict class.
    _type_class_map_cache: (class variable) This is a cached dict that maps
        from event type to Python class.  Used by FromJSON and FromDict to
        know which class to initialize.

  Properties in FIELDS:
      - type (string, required): Type of the event.  Its value determines
        which fields are applicable to this event.
      - _METADATA (object, optional): Special field reserved for testlog
        to exchange information between processes.
  """

  # TODO(itspeter): Consider to create a class that wraps properties in
  #                 dictionary FIELDS.

  # The FIELDS list data expected in for this class in a form where name is
  # the key and value is a tuple of (required, validation function).
  # Details of each fields can be found on either the docstring of this class
  # or the Testlog API Playbook.
  FIELDS = {
      'type': (True, testlog_validator.Validator.String),
      # pylint: disable=protected-access
      Testlog.FIELDS._METADATA: (False, testlog_validator.Validator.Object)
  }

  def __init__(self, data=None):
    """Only allow initialization for classes that declared GetEventType()."""
    try:
      event_type = self.GetEventType()
      if event_type:
        default_data = self._data = {'type': event_type}
        if isinstance(data, dict):
          # Override the type in the data.
          data.update(default_data)
          self.Populate(data)
        return
    except NotImplementedError:
      pass
    raise testlog_utils.TestlogError(
        'Must initialize directly from desired event class.')

  def __eq__(self, other):
    """Equals operator."""
    if isinstance(other, self.__class__):
      return self._data == other._data  # pylint: disable=protected-access
    return False

  def __ne__(self, other):
    """Not equals operator."""
    return not self.__eq__(other)

  def __getitem__(self, name):
    """Dictionary operator."""
    return self._data[name]

  def __setitem__(self, key, value):
    """Simulates a dictionary operator.

    Provides a dictionary-like operation to update the event. It will try to
    get the corressponding validate function from FIELDS in current and all
    superclass.

    Raises:
      ValueError if the value can not be converted.
      TestlogError if the key is not allowlisted in the FIELD.
    """
    # TODO(itspeter): Consider remove this handy function and make it
    # explicitly to call other function to assign values.
    mro = self.__class__.__mro__
    # Find the corresponding validate function.
    for cls in mro:
      if cls is object:
        break  # Reach the root.
      if not hasattr(cls, 'FIELDS'):
        continue  # Continue search in the parents'
      if key in cls.FIELDS:
        cls.FIELDS[key][1](self, key, value)
        return
    raise testlog_utils.TestlogError('Cannot find key %r for event %s' % (
        key, self.__class__.__name__))

  def __contains__(self, item):
    """Supports `in` operator."""
    return item in self._data

  def CheckIsValid(self):
    """Raises an exception if the event is invalid."""
    mro = self.__class__.__mro__
    missing_fields = []
    # Find the corresponding requirement.
    for cls in mro:
      if cls is object:
        break
      for field_name, metadata in cls.FIELDS.items():
        if metadata[0] and field_name not in self._data:
          missing_fields.append(field_name)

    # Test run event with attachments should have at least one serial number.
    if (self.GetEventType() == 'station.test_run' and
        'attachments' in self._data and 'serialNumbers' not in self._data):
      missing_fields.append('serialNumbers')

    if missing_fields != []:
      raise testlog_utils.TestlogError('Missing fields: %s' % missing_fields)

    if self._data['apiVersion'] != TESTLOG_API_VERSION:
      raise testlog_utils.TestlogError('Invalid Testlog API version: %s' %
                                       self._data['apiVersion'])

    # Check the length of the grouped parameters.
    if 'parameters' in self._data:
      group_length = {}
      for param in self._data['parameters'].values():
        if 'group' in param:
          group = param['group']
          if group not in group_length:
            group_length[group] = len(param['data'])
          elif group_length[group] != len(param['data']):
            raise testlog_utils.TestlogError(
                'The parameters length in the group(%s) are not the same' %
                group)

    for key in self._data:
      # Ignore keys that start with an underscore.
      if key.startswith('_'):
        continue
      data_type = type(self._data[key])
      if data_type == list:
        if not self._data[key]:
          raise testlog_utils.TestlogError('Empty list is invalid: %r' % key)
      elif data_type == dict:
        if not self._data[key]:
          raise testlog_utils.TestlogError('Empty dict is invalid: %r' % key)

  @classmethod
  def GetEventType(cls):
    """Returns the event type of this particular object."""
    raise NotImplementedError

  def Populate(self, data):
    """Populates values one by one in dictionary data.

    We iterate the data instead of directly asssigning it to self._data in
    order to make sure that validate function is called.

    Returns:
      The event being modified (self).
    """
    for key in data:
      # Ignore keys that start with an underscore.
      if key.startswith('_'):
        continue
      data_type = type(data[key])
      if data_type == list:
        if not data[key]:
          raise testlog_utils.TestlogError('Empty list is invalid: %r' % key)
        for value in data[key]:
          self[key] = value
      elif data_type == dict:
        if not data[key]:
          raise testlog_utils.TestlogError('Empty dict is invalid: %r' % key)
        for sub_key, value in data[key].items():
          self[key] = {'key': sub_key, 'value': value}
      else:
        self[key] = data[key]
    return self

  def CastFields(self):
    """Casts fields to certain python types."""

  @classmethod
  def _AllSubclasses(cls):
    """Returns all subclasses of this class recursively."""
    subclasses = cls.__subclasses__()
    # pylint: disable=protected-access
    return subclasses + [subsub for sub in subclasses
                         for subsub in sub._AllSubclasses()]

  @classmethod
  def _TypeClassMap(cls):
    """Returns a map of EVENT_TYPE to EVENT_CLASS."""
    if not hasattr(cls, '_type_class_map_cache'):
      cls._type_class_map_cache = {event_cls.GetEventType(): event_cls
                                   for event_cls in cls._AllSubclasses()
                                   if event_cls.GetEventType()}
    return cls._type_class_map_cache

  @classmethod
  def DetermineClass(cls, data):
    """Determines the appropriate Event subclass for a particular dataset."""
    try:
      return cls._TypeClassMap()[data['type']]
    except (testlog_utils.TestlogError, KeyError):
      raise testlog_utils.TestlogError(
          'Input event does not have a valid `type`.')

  @classmethod
  def FromJSON(cls, json_string, check_valid=True):
    """Converts JSON data into an Event instance."""
    return cls.FromDict(json.loads(json_string), check_valid)

  @classmethod
  def FromDict(cls, data, check_valid=True):
    """Converts Python dict data into an Event instance."""
    event = cls.DetermineClass(data)()
    event.Populate(data)
    event.CastFields()
    if check_valid:
      event.CheckIsValid()
    return event

  def ToJSON(self):
    """Returns a JSON string representing this event."""
    return json.dumps(self.ToDict(), default=testlog_utils.JSONHandler)

  def ToDict(self):
    """Returns a Python dict representing this event."""
    return self._data

  def __repr__(self):
    """Repr operator for string printing."""
    return '<{} data={}>'.format(self.__class__.__name__, repr(self._data))


class Event(EventBase):
  """Main event class.

  Defines common fields of all events.

  Properties in FIELDS:
      - uuid (string, required): Unique UUID of the event.
      - apiVersion (string, required): Version of the testlog API being
        used.
      - time (number, required): Time in seconds since the epoch of
        the event.
      - seq (integer, optional): Sequence number of the event, to help in
        cases where the station date is unreliable.  Should be monotonically
        increasing.
  """

  FIELDS = {
      'uuid': (True, testlog_validator.Validator.String),
      'apiVersion': (True, testlog_validator.Validator.String),
      'time': (True, testlog_validator.Validator.Number),
      'seq': (False, testlog_validator.Validator.Long),
  }

  @classmethod
  def GetEventType(cls):
    return None

class _StationBase(Event):
  """Base class for all "station" subtypes.

  Cannot be initialized.

  Properties in FIELDS:
      - dutDeviceId (string, optional): ID of the device under test.  This
        should be a value tied to the device that will not change in the case
        that the device is reimaged.
      - stationDeviceId (string, optional): ID of the device being used as
        the station.  This should be a value tied to the device that will not
        change in the case that the device is reimaged.
      - stationInstallationId (string, optional): ID of the installation of the
        station.  Every time the station is reimaged, a new installation ID
        should be generated (unique UUID).
  """

  FIELDS = {
      'dutDeviceId': (False, testlog_validator.Validator.String),
      'stationDeviceId': (False, testlog_validator.Validator.String),
      'stationInstallationId': (False, testlog_validator.Validator.String)
  }

  @classmethod
  def GetEventType(cls):
    return None


class _GroupChecker:
  """Context manager for checking grouped parameters."""

  def __init__(self, event, name, param_list):
    self.event = event
    self.name = name
    self.param_list = param_list

  def __enter__(self):
    if self.event.in_group:
      raise ValueError('Can\'t enter the same GroupChecker twice')
    self.event.in_group = self.name

  def __exit__(self, exc_type, exc_value, traceback):
    # If an exception occurs, we don't want to suppress it.
    if traceback:
      return

    if self.event.in_group != self.name:
      raise ValueError('This should not happen! Exit the wrong group!')
    self.event.in_group = None
    length = len(self.event['parameters'][self.param_list[0]]['data'])
    for param_name in self.param_list:
      if length != len(self.event['parameters'][param_name]['data']):
        raise ValueError('The parameters length in the group(%s) are not '
                         'the same' % self.name)


class StationStatus(_StationBase):
  """Represents the Station's status when Station is running.

  Properties in FIELDS:
      - filePath (string, optional): Name or path of the program that generated
        this message.
      - serialNumbers (dictionary, optional): A dictionary of serial numbers
        associated with this device.  May not be exhaustive (since some
        components may not have been attached yet).
      - parameters (dictionary, optional): The value can be any type. If
        numeric, minimum and maximum limits (inclusive) may also be specified.
        If text, a regex may be specified.  If other types, the value will be
        serialized.  If limits/regex are specified, the status field should be
        defined to show success (value match the expectation) or failure.
  """

  @classmethod
  def _NumericSchema(cls, label):
    return schema.AnyOf([
        schema.Scalar(label, int),
        schema.Scalar(label, float)])

  def _ValidatorSerialNumberWrapper(*args, **kwargs):
    # pylint: disable=no-method-argument
    SCHEMA = schema.Optional(schema.Scalar('serialNumbers.value', str))
    kwargs['schema'] = SCHEMA
    return testlog_validator.Validator.Dict(*args, **kwargs)

  def _ValidatorParameterWrapper(*args, **kwargs):
    # pylint: disable=no-method-argument
    DATA_SCHEMA = schema.List('data', schema.FixedDict(
        'data',
        items={},
        optional_items={
            'status': schema.Scalar('status', str, ['PASS', 'FAIL']),
            'numericValue': StationStatus._NumericSchema('numericValue'),
            'expectedMinimum': StationStatus._NumericSchema('expectedMinimum'),
            'expectedMaximum': StationStatus._NumericSchema('expectedMaximum'),
            'textValue': schema.Scalar('textValue', str),
            'expectedRegex': schema.Scalar('expectedRegex', str),
            'serializedValue': schema.Scalar('serializedValue', str)
        }))
    SCHEMA = schema.FixedDict(
        'parameters.value',
        items={},
        optional_items={
            'description': schema.Scalar('description', str),
            'group': schema.Scalar('group', str),
            'valueUnit': schema.Scalar('valueUnit', str),
            'type': schema.Scalar('type', str, list(PARAM_TYPE)),
            'data': DATA_SCHEMA})
    kwargs['schema'] = SCHEMA
    return testlog_validator.Validator.Dict(*args, **kwargs)

  FIELDS = {
      'filePath': (False, testlog_validator.Validator.String),
      'serialNumbers': (False, _ValidatorSerialNumberWrapper),
      'parameters': (False, _ValidatorParameterWrapper),
  }

  @classmethod
  def GetEventType(cls):
    return 'station.status'

  @staticmethod
  def _CreateParamValueDict(value, min_val=None, max_val=None, regex=None):
    """Checks types and returns a dict that aligns with Testlog Playbook."""
    value_dict = {}
    if isinstance(value, str):
      value_dict['textValue'] = value
      if min_val is not None or max_val is not None:
        raise ValueError('This should not happen!')
      if regex:
        value_dict['expectedRegex'] = regex
    elif isinstance(value, (int, float)):
      value_dict['numericValue'] = value
      if regex:
        raise ValueError('This should not happen!')
      if min_val is not None:
        value_dict['expectedMinimum'] = min_val
      if max_val is not None:
        value_dict['expectedMaximum'] = max_val
    else:
      value_dict['serializedValue'] = json.dumps(value)
    return value_dict

  def _CheckAndCreateParam(self, name):
    if 'parameters' not in self._data or name not in self['parameters']:
      self['parameters'] = {
          'key': name,
          'value': {'type': PARAM_TYPE.measurement, 'data': []}
      }

  def _LogParamValue(self, name, value_dict):
    self._CheckAndCreateParam(name)

    group = self['parameters'][name].get('group', None)
    if group and group != self.in_group:
      raise ValueError('The grouped parameter should be used in the '
                       'GroupChecker')

    self['parameters'][name]['data'].append(value_dict)

  def AddSerialNumber(self, name, value):
    """Adds serial numbers."""
    self['serialNumbers'] = {'key': name, 'value': value}

  def LogParam(self, name, value):
    """Logs parameter as specified in Testlog API."""
    value_dict = StationStatus._CreateParamValueDict(value)

    self._LogParamValue(name, value_dict)
    return self

  # pylint: disable=redefined-builtin
  def CheckNumericParam(self, name, value, min=None, max=None):
    """Checks and logs numeric parameter as specified in Testlog API.

    We use testlog_utils.IsInRange to perform the check.
    """
    if not isinstance(value, (int, float)):
      raise ValueError('%r is not a numeric' % value)

    value_dict = StationStatus._CreateParamValueDict(value, min, max)

    # Check the result
    result = testlog_utils.IsInRange(value, min, max)
    value_dict['status'] = 'PASS' if result else 'FAIL'

    self._LogParamValue(name, value_dict)
    return result

  def CheckTextParam(self, name, value, regex=None):
    """Checks and logs text parameter as specified in Testlog API.

    We use re.search to perform the check.
    """
    if not isinstance(value, str):
      raise ValueError('%r is not a text' % value)
    value_dict = StationStatus._CreateParamValueDict(value, regex=regex)

    # Check the result
    result = True
    if not re.search(regex, value):
      result = False
    value_dict['status'] = 'PASS' if result else 'FAIL'

    self._LogParamValue(name, value_dict)
    return result

  def UpdateParam(self, name, description=None, value_unit=None,
                  param_type=None):
    """Updates parameter's metedata."""
    self._CheckAndCreateParam(name)

    if description:
      self['parameters'][name]['description'] = description
    if value_unit:
      self['parameters'][name]['valueUnit'] = value_unit
    if param_type:
      self['parameters'][name]['type'] = param_type

  in_group = None

  def GroupParam(self, name, param_list):
    """Groups a list of parameters."""
    if not isinstance(name, str) or not name:
      raise ValueError('name(%r) should be a string and not empty' % name)
    if not isinstance(param_list, list) or not param_list:
      raise ValueError('param_list(%r) should be a list and not empty' %
                       param_list)
    for param in param_list:
      self._CheckAndCreateParam(param)

      if self['parameters'][param]['data']:
        raise ValueError(
            'parameter(%s) should not have data before grouping' % param)
      if self['parameters'][param].get('group', None):
        raise ValueError(
            'parameter(%s) should not be grouped twice' % param)

      self['parameters'][param]['group'] = name

    return _GroupChecker(self, name, param_list)


class StationInit(_StationBase):
  """Represents the Station being brought up or initialized.

  Properties in FIELDS:
      - count (integer, required): Number of times that this station has
        been initialized so far.
      - success (boolean, required): Whether or not this station was
        successfully initialized.
      - failureMessage (string, optional): A failure string explaining why
        the station could not initialize.
  """

  FIELDS = {
      'count': (True, testlog_validator.Validator.Long),
      'success': (True, testlog_validator.Validator.Boolean),
      'failureMessage': (False, testlog_validator.Validator.String)
  }

  @classmethod
  def GetEventType(cls):
    return 'station.init'


class StationMessage(_StationBase):
  """Represents a Python message on the Station.

  Properties in FIELDS:
      - message (string, required): Message text.  Can include stacktrace or
        other debugging information if applicable.
      - filePath (string, optional): Name or path of the program that
        generated this message.
      - lineNumber (integer, optional): Line number within the program that
        generated this message.
      - functionName (string, optional): Function name within the program
        that generated this message.
      - logLevel (string, optional): Log level of this message. Possible
        values: DEBUG, INFO, WARNING, ERROR, CRITICAL
      - testRunId (string, optional): If this message was associated with a
        particular test run, its ID should be specified here.
  """

  FIELDS = {
      'message': (True, testlog_validator.Validator.String),
      'filePath': (False, testlog_validator.Validator.String),
      'lineNumber': (False, testlog_validator.Validator.Long),
      'functionName': (False, testlog_validator.Validator.String),
      'logLevel': (False, testlog_validator.Validator.String),
      'testRunId': (False, testlog_validator.Validator.String)
  }

  @classmethod
  def GetEventType(cls):
    return 'station.message'


class StationTestRun(StationStatus):
  """Represents a test run on the Station.

  Properties in FIELDS:
    - testRunId (string, required): Unique UUID of the test run.  Since one
      test run may output multiple test_run events (showing the progress of
      the test run), we use testRunId to identify them as the same test.
    - testName (string, required): A name identifying this test with its
      particular configuration.  Sometimes, a test might run multiple times
      with different configurations in the same project.  This field is used
      to separate these configurations.
    - testType (string, required): A name identifying this type of test.
      If it runs multiple times with different configurations, use testName
      to differentiate.
    - arguments (dictionary, optional): A dictionary representing the arguments
      of the test configuration.
    - status (string, required): The current status of the test run.
      Possible values: STARTING, RUNNING, FAIL, PASS, UNKNOWN
    - startTime (number, required): Time in seconds since the epoch when the
      test started.
    - endTime (number, optional): Time in seconds since the epoch when the test
      ended.
    - duration (number, optional): How long the test took to complete.
      Should be the same as endTime - startTime.  Included for convenience.
      Measured in seconds.
    - operatorId (string, optional): A unique identifier for the operator
      running this test.
    - attachments (dictionary, optional): List of attachment files associated
      with this test run.  If the JSON's location does not imply the path to
      attachment file, the full path can be specified.
      May also be a gs:// path.
    - failures (array, optional): List of failures associated with this test
      run.  It is recommended for each parameter or series failure to have an
      entry in this list, but functional or environmental failures may also be
      included (e.g. device not connected).  The same failure code may be listed
      multiple times with different details strings.
  """

  def _ValidatorArgumentWrapper(*args, **kwargs):
    # pylint: disable=no-method-argument
    SCHEMA = schema.FixedDict(
        'arguments.value',
        items={'value': schema.Scalar('value', str)},
        optional_items={
            'description': schema.Scalar('description', str)})
    kwargs['schema'] = SCHEMA
    return testlog_validator.Validator.Dict(*args, **kwargs)

  def _ValidatorFailureWrapper(*args, **kwargs):
    # pylint: disable=no-method-argument
    SCHEMA = schema.FixedDict(
        'failures.value',
        items={'code': schema.Scalar('code', str),
               'details': schema.Scalar('details', str)})
    kwargs['schema'] = SCHEMA
    return testlog_validator.Validator.List(*args, **kwargs)

  def _ValidatorAttachmentWrapper(*args, **kwargs):
    # pylint: disable=no-method-argument
    SCHEMA = schema.FixedDict(
        'attachments.value',
        items={'path': schema.Scalar('path', str),
               'mimeType': schema.Scalar('mimeType', str)},
        optional_items={
            'description': schema.Scalar('description', str)})
    kwargs['schema'] = SCHEMA
    return testlog_validator.Validator.Dict(*args, **kwargs)

  FIELDS = {
      'testRunId': (True, testlog_validator.Validator.String),
      'testName': (True, testlog_validator.Validator.String),
      'testType': (True, testlog_validator.Validator.String),
      'arguments': (False, _ValidatorArgumentWrapper),
      'status': (True, testlog_validator.Validator.Status),
      'startTime': (True, testlog_validator.Validator.Number),
      'endTime': (False, testlog_validator.Validator.Number),
      'duration': (False, testlog_validator.Validator.Number),
      'operatorId': (False, testlog_validator.Validator.String),
      'attachments': (False, _ValidatorAttachmentWrapper),
      'failures': (False, _ValidatorFailureWrapper),
  }

  # Possible values for the `status` field.
  # TODO(itspeter): Check on log when will UNKNOWN emitted.
  STATUS = type_utils.Enum([
      'STARTING', 'RUNNING', 'FAIL', 'PASS',
      'UNKNOWN'])  # States that doesn't apply for StationTestRun

  @classmethod
  def GetEventType(cls):
    return 'station.test_run'

  def AttachFile(self, path, mime_type, name, delete=True, description=None):
    """Attaches a file as specified in Testlog API."""
    value = {'mimeType': mime_type,
             'path': path}
    if description:
      value.update({'description': description})
    testlog_validator.Validator.Attachment(
        self, name, value, delete, GetGlobalTestlog)
    self['attachments'] = {'key': name, 'value': value}
    return self

  def AttachContent(self, content, name, description=None):
    """Attaches a file with content."""
    with file_utils.UnopenedTemporaryFile() as path:
      with open(path, 'w') as f:
        f.write(content)
      return self.AttachFile(
          path, 'text/plain', name, delete=False, description=description)

  def AddArgument(self, key, value, description=None):
    """Adds arguments."""
    value_dict = {'value': json.dumps(value)}
    if description:
      value_dict['description'] = description
    self['arguments'] = {'key': key, 'value': value_dict}
    return self

  def AddFailure(self, code, details):
    """Adds failures."""
    # TODO(itspeter): Unittest.
    # Get the numeric code unified into hex format.
    if isinstance(code, int):
      code = '0x%x' % code
    if not isinstance(code, str):
      raise ValueError('code(%r) should be a string or an integer' % code)
    if not isinstance(details, str):
      raise ValueError('details(%r) should be a string' % details)
    self['failures'] = {'code': code, 'details': details}
    return self
