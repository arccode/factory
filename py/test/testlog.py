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

[FACTORY_ROOT] ─── .device_id
                   (legacy file, replaced by [LOG_ROOT]/device_id)
[LOG_ROOT]─┬─ testlog.json
           ├─ device_id
           ├─ init_count
           ├─ reimage_id
           ├─ events/ ─┬─ .boot_sequence
           │   (Legacy │    (legacy file, replaced by [LOG_ROOT]/init_count)
           │           ├─ .reimage_id
           │           │    (legacy file, replaced by [LOG_ROOT]/reimage_id)
           │           └─ events
           │                (legacy file, replaced by [LOG_ROOT]/testlog.json)
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


from __future__ import print_function

import datetime
import json
import logging
import os
import shutil
import threading
from uuid import uuid4


# TODO(itspeter): Find a way to properly pack those as testlog should
# be able to deploy without factory framework.
import factory_common  # pylint: disable=W0611
from cros.factory.test import testlog_seq
from cros.factory.test import testlog_validator
from cros.factory.test import testlog_utils
from cros.factory.utils import file_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils


TESTLOG_API_VERSION = '0.1'
TESTLOG_ENV_VARIABLE_NAME = 'TESTLOG'

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
# The /var/run directory (or something writable by us if in the chroot).
# TODO(itspeter): Survey if we can find an equivalent folder in Windows.
#                 Otherwise, the SEQ_INCREMENT_ON_BOOT magic might not work.
_TMP_DIR = '/tmp' if sys_utils.InChroot() else '/var/run'

# File containing the next sequence number to write. This is in
# /var/run so it is cleared on each boot.
_SEQUENCE_PATH = os.path.join(_TMP_DIR, 'testlog_seq')

# Use the lock to avoid two threads creating multiple writers.
_log_related_lock = threading.RLock()

# A global testlog writer. Since we expect each test is invoked
# separately as a process, each test will have their own 'global'
# testlog writer with a unique ID.
_global_testlog = None

_pylogger = None
_pylogger_handler = None


class Testlog(object):
  """Primarily a wrapper for variables that should exist in a singleton.

  This class should be initialized only once per process.

  Properties:
    last_test_run: In memory object that keep the same content of session_json.
      They should be the same so when updating the test_run we don't need to
      read and parse from session_json repeatedly.
    log_root: The root folder for logging.
    primary_json: A JSON file that will ingested by Instalog.
    session_json: A temporary JSON file to keep the test_run information.
    flush_mode: Flag for default action on API calls. True to flush the
      test_run event into primary_json, False to session_json.
    attachments_folder: The folder for copying / moving binary files.
    uuid: A unique ID for related to the process that using the testlog.
    seq_generator: A sequence file that expected to increase monotonically.
      during test.
  """

  FIELDS = type_utils.Enum([
      'LAST_TEST_RUN', 'LOG_ROOT', 'PRIMARY_JSON', 'SESSION_JSON',
      'ATTACHMENTS_FOLDER', 'UUID', 'FLUSH_MODE', '_METADATA'])

  def __init__(self, log_root=None, uuid=None):
    """Initializes the Testlog singleton.

    Args:
      log_root: The path to root folder of testlog.
      uuid: A unique ID for this process.
    """
    global _global_testlog  # pylint: disable=W0603
    assert _global_testlog is None, (
        '_global_testlog should be initialized only once before Close().')
    with _log_related_lock:
      _global_testlog = self
    if log_root and uuid:
      # Indicate it initialized from a harness that no one will collect its
      # session JSON file (so set to None)
      session_data = {
          Testlog.FIELDS.LOG_ROOT: log_root,
          Testlog.FIELDS.PRIMARY_JSON:
              os.path.join(log_root, _DEFAULT_PRIMARY_JSON_FILE),
          Testlog.FIELDS.ATTACHMENTS_FOLDER:
              os.path.join(log_root, _DEFAULT_ATTACHMENTS_FOLDER),
          Testlog.FIELDS.UUID: uuid,
          Testlog.FIELDS.FLUSH_MODE: True}
    elif not log_root and not uuid:
      # Get the related information from the OS environment variable.
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
    self.flush_mode = session_data.pop(self.FIELDS.FLUSH_MODE)
    metadata = session_data.pop(self.FIELDS._METADATA, None)  # pylint: disable=W0212
    if metadata:
      # pylint: disable=W0212
      self.last_test_run[self.FIELDS._METADATA] = metadata
    assert len(session_data.items()) == 0, 'Not all variable initialized.'

    # Initialize the sequence generator
    self.seq_generator = testlog_seq.SeqGenerator(
        _SEQUENCE_PATH, self.primary_json)
    self._CreateFolders()
    # Reload the JSON paths into JSONLogFile for future writing.
    if self.session_json:
      self.session_json = JSONLogFile(
          uuid=self.uuid, seq_generator=self.seq_generator,
          path=self.session_json, mode='w')
    if self.primary_json:
      self.primary_json = JSONLogFile(
          uuid=self.uuid, seq_generator=self.seq_generator,
          path=self.primary_json, mode='a')
    # Initialize testlog._pylogger
    self.CaptureLogging()

  def CaptureLogging(self):
    """Captures calls to logging.* into primary_json."""
    level = logging.getLogger().getEffectiveLevel()
    CapturePythonLogging(
        callback=self.primary_json.Log, level=level)
    logging.info('Testlog(%s) is capturing logging at level %s',
                 self.uuid, logging.getLevelName(level))

  def Close(self):
    # pylint: disable=W0603
    global _global_testlog, _pylogger, _pylogger_handler
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
    metadata = last_test_run.pop(Testlog.FIELDS._METADATA)  # pylint: disable=W0212
    return {
        Testlog.FIELDS.LAST_TEST_RUN: Event.FromDict(last_test_run),
        Testlog.FIELDS.LOG_ROOT: metadata[Testlog.FIELDS.LOG_ROOT],
        Testlog.FIELDS.PRIMARY_JSON: metadata[Testlog.FIELDS.PRIMARY_JSON],
        Testlog.FIELDS.SESSION_JSON: session_json_path,
        Testlog.FIELDS.ATTACHMENTS_FOLDER:
            metadata[Testlog.FIELDS.ATTACHMENTS_FOLDER],
        Testlog.FIELDS.UUID: metadata[Testlog.FIELDS.UUID],
        Testlog.FIELDS.FLUSH_MODE: metadata[Testlog.FIELDS.FLUSH_MODE],
        Testlog.FIELDS._METADATA: metadata}  # pylint: disable=W0212

  def _CreateFolders(self):
    for x in [self.log_root, self.attachments_folder]:
      file_utils.TryMakeDirs(x)


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
  if not station_test_run:
    station_test_run = StationTestRun()
    station_test_run.FromDict({
        'status': StationTestRun.STATUS.STARTING,
        'testRunId': uuid,
        'startTime': datetime.datetime.utcnow()
        })
  # pylint: disable=W0212
  station_test_run[Testlog.FIELDS._METADATA] = {
      Testlog.FIELDS.LOG_ROOT: log_root,
      Testlog.FIELDS.PRIMARY_JSON:
          os.path.join(log_root, _DEFAULT_PRIMARY_JSON_FILE),
      Testlog.FIELDS.SESSION_JSON: session_log_path,
      Testlog.FIELDS.ATTACHMENTS_FOLDER:
          os.path.join(log_root, _DEFAULT_ATTACHMENTS_FOLDER),
      Testlog.FIELDS.FLUSH_MODE: False,
      Testlog.FIELDS.UUID: uuid
      }
  with file_utils.FileLockContextManager(session_log_path, 'w') as fd:
    fd.write(station_test_run.ToJSON())
  return session_log_path


def Collect(session_json_path, station_test_run=None):
  """Merges the session JSON into the primary JSON.

  Args:
    session_json_path: Path to the session JSON.
    station_test_run: Additional information might be appended.
  """
  # TODO(itspeter): Check the file is already closed properly. (i.e.
  #                 no lock exists or other process using it)
  # TODO(itspeter): Expose another function for collecting tests that
  #                 crashed during the test.
  with file_utils.FileLockContextManager(session_json_path, 'r') as fd:
    content = fd.read()
    try:
      session_json = json.loads(content)
      session_json.pop(Testlog.FIELDS._METADATA) # pylint: disable=W0212
      test_run = StationTestRun()
      test_run.Populate(session_json)
      # Merge the station_test_run information.
      if station_test_run:
        test_run.Populate(station_test_run.ToDict())
      Log(test_run)
    except Exception:  # pylint: disable=W0703
      # Not much we can do here.
      logging.exception('Not able to collect %s. Last read: %s',
                        session_json_path, content)

  shutil.rmtree(os.path.dirname(session_json_path))


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

  if testlog_singleton.flush_mode:
    testlog_singleton.primary_json.Log(event)
  else:
    testlog_singleton.session_json.Log(event, override=True)


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
    ret = getattr(GetGlobalTestlog().last_test_run, method_name)(*args, **kwargs)
    Log(GetGlobalTestlog().last_test_run)
    return ret
  else:
    raise testlog_utils.TestlogError(
        'In memory station.test_run does not set. '
        'Test harness need to set it manually.')


def LogParam(*args, **kwargs):
  kwargs['_method_name'] = 'LogParam'
  return _StationTestRunWrapperInSession(*args, **kwargs)


def AttachFile(*args, **kwargs):
  kwargs['_method_name'] = 'AttachFile'
  return _StationTestRunWrapperInSession(*args, **kwargs)


def CreateSeries(*args, **kwargs):
  kwargs['_method_name'] = 'CreateSeries'
  return _StationTestRunWrapperInSession(*args, **kwargs)


def AddArgument(*args, **kwargs):
  kwargs['_method_name'] = 'AddArgument'
  return _StationTestRunWrapperInSession(*args, **kwargs)


def AddFailure(*args, **kwargs):
  kwargs['_method_name'] = 'AddFailure'
  return _StationTestRunWrapperInSession(*args, **kwargs)


class JSONLogFile(file_utils.FileLockContextManager):
  """Represents a JSON log file on disk."""

  def __init__(self, uuid, seq_generator, path, mode='a'):
    super(JSONLogFile, self).__init__(path=path, mode=mode)
    self.test_run_id = uuid
    self.seq_generator = seq_generator

  def Log(self, event, override=False):
    """Converts event into JSON string and writes into disk.

    Args:
      event: The event to output.
      override: Ture to make sure the JSON log file contains only one event.
    """
    # Data that should be refresh at every write operation.
    event['id'] = str(uuid4())
    event['seq'] = self.seq_generator.Next()
    if 'apiVersion' not in event:
      event['apiVersion'] = TESTLOG_API_VERSION
    if 'time' not in event:
      event['time'] = datetime.datetime.utcnow()

    line = event.ToJSON() + '\n'
    with self:
      if override:
        self.file.seek(0)
      self.file.write(line)
      if override:
        self.file.truncate()
      self.file.flush()
      os.fsync(self.file.fileno())
    return line


def CapturePythonLogging(callback, level=logging.DEBUG):
  """Starts capturing Python logging.

  The output events will be sent to the specified callback function.
  This function can only be used once to set up logging -- any subsequent
  calls will return the existing Logger object.

  Args:
    callback: Function to be called when the Python logging library is called.
              It accepts one argument, which will be the StationMessage object
              as constructed by TestlogLogHandler.
    level: Sets minimum verbosity of log messages that will be sent to the
           callback.  Default: logging.DEBUG.
  """
  global _pylogger, _pylogger_handler  # pylint: disable=W0603
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
               and created a StationMessage object.  It accepts one argument,
               which will be the constructed StationMessage object.
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

    self._thread_data.in_emit = True
    event = self.format(record)
    result = self._callback(event)
    self._thread_data.in_emit = False
    return result


class LogFormatter(logging.Formatter):
  """Formats records into events."""

  def format(self, record):
    message = record.getMessage()
    if record.exc_info:
      message += '\n%s' % self.formatException(record.exc_info)
    time = datetime.datetime.utcfromtimestamp(record.created)

    data = {
        'filePath': getattr(record, 'pathname', None),
        'lineNumber': getattr(record, 'lineno', None),
        'functionName': getattr(record, 'funcName', None),
        'logLevel': getattr(record, 'levelname', None),
        'time': time,
        'message': message}

    return StationMessage(data)


class EventBase(object):
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
      # pylint: disable=W0212
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
      return self._data == other._data  # pylint: disable=W0212
    else:
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
      TestlogError if the key is not whitelisted in the FIELD.
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

  def CheckMissingFields(self):
    """Returns a list of missing field."""
    mro = self.__class__.__mro__
    missing_fileds = []
    # Find the corresponding requirement.
    for cls in mro:
      if cls is object:
        break
      for field_name, metadata in cls.FIELDS.iteritems():
        if metadata[0] and field_name not in self._data:
          missing_fileds.append(field_name)

    return missing_fileds

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
    for key in data.iterkeys():
      data_type = type(data[key])
      if data_type == list:
        for value in data[key]:
          self[key] = value
      elif data_type == dict:
        for sub_key, value in data[key].iteritems():
          self[key] = {'key' : sub_key, 'value': value}
      else:
        self[key] = data[key]
    return self

  def CastFields(self):
    """Casts fields to certain python types."""
    pass

  @classmethod
  def _AllSubclasses(cls):
    """Returns all subclasses of this class recursively."""
    subclasses = cls.__subclasses__()
    # pylint: disable=W0212
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
    except testlog_utils.TestlogError:
      raise testlog_utils.TestlogError(
          'Input event does not have a valid `type`.')

  @classmethod
  def FromJSON(cls, json_string):
    """Converts JSON data into an Event instance."""
    return cls.FromDict(json.loads(json_string))

  @classmethod
  def FromDict(cls, data):
    """Converts Python dict data into an Event instance."""
    event = cls.DetermineClass(data)()
    event.Populate(data)
    event.CastFields()
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
      - id (string, required): Unique UUID of the event.
      - apiVersion (string, required): Version of the testlog API being
        used.
      - seq (integer, optional): Sequence number of the event, to help in
        cases where the station date is unreliable.  Should be monotonically
        increasing.
      - time (datetime or string, required): Date and time of the event.
  """

  FIELDS = {
      'id': (True, testlog_validator.Validator.String),
      'apiVersion': (True, testlog_validator.Validator.String),
      'seq': (False, testlog_validator.Validator.Long),
      'time': (True, testlog_validator.Validator.Time),
  }

  @classmethod
  def GetEventType(cls):
    return None

  def CastFields(self):
    return super(Event, self).CastFields()

class _StationBase(Event):
  """Base class for all "station" subtypes.

  Cannot be initialized.

  Properties in FIELDS:
      - stationName (string, optional): Name of the station.
      - stationDeviceId (string, optional): ID of the device being used as
        the station.  This should be a value tied to the device (such as a
        MAC address) that will not change in the case that the device is
        reimaged.
      - stationReimageId (string, optional): ID of the reimage of the
        station.  Every time the station is reimaged, a new reimage ID
        should be generated (unique UUID).
  """

  FIELDS = {
      'stationName': (False, testlog_validator.Validator.String),
      'stationDeviceId': (False, testlog_validator.Validator.String),
      'stationReimageId': (False, testlog_validator.Validator.String)
  }

  @classmethod
  def GetEventType(cls):
    return None

  def CastFields(self):
    return super(_StationBase, self).CastFields()


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

  def CastFields(self):
    return super(StationInit, self).CastFields()

class StationMessage(_StationBase):
  """Represents a Python message on the Station.

  Properties in FIELDS:
      - filePath (string, optional): Name or path of the program that
        generated this message.
      - lineNumber (integer, optional): Line number within the program that
        generated this message.
      - functionName (string, optional): Function name within the program
        that generated this message.
      - logLevel (string, optional): Log level of this message. Possible
        values: DEBUG, INFO, WARNING, ERROR, CRITICAL
      - message (string, required): Message text.  Can include stacktrace or
        other debugging information if applicable.
      - testRunId (string, optional): If this message was associated with a
        particular test run, its ID should be specified here.
  """

  FIELDS = {
      'filePath': (False, testlog_validator.Validator.String),
      'lineNumber': (False, testlog_validator.Validator.Long),
      'functionName': (False, testlog_validator.Validator.String),
      'logLevel': (False, testlog_validator.Validator.String),
      'message': (False, testlog_validator.Validator.String),
      'testRunId': (False, testlog_validator.Validator.String)
  }

  @classmethod
  def GetEventType(cls):
    return 'station.message'

  def CastFields(self):
    return super(StationMessage, self).CastFields()

class StationTestRun(_StationBase):
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
    - status (string, required): The current status of the test run.
      Possible values: STARTING, RUNNING, FAILED, PASSED PASSED
    - startTime (datetime, required): Date and time when the test started.
    - endTime (datetime, optional): Date and time when the test ended.
    - duration (number, optional): How long the test took to complete.
      Should be the same as endTime - startTime.  Included for convenience.
      Measured in seconds.
  """

  # TODO(itspeter): Document 'argument', 'operatorId', 'failures',
  #                 'serialNumbers', 'parameters' and 'series'.

  def _ValidatorAttachmentWrapper(*args, **kwargs):  # pylint: disable=E0211
    # Because the FIELDS map must be assigned at the time of loading the
    # module. However, Testlog singleton is not ready yet, we pass the
    # function that get the singleton instead.
    kwargs['testlog_getter_fn'] = GetGlobalTestlog
    return testlog_validator.Validator.Attachment(*args, **kwargs)

  FIELDS = {
      'testRunId': (True, testlog_validator.Validator.String),
      'testName': (True, testlog_validator.Validator.String),
      'testType': (True, testlog_validator.Validator.String),
      'arguments': (False, testlog_validator.Validator.Dict),
      'status': (True, testlog_validator.Validator.Status),
      'startTime': (True, testlog_validator.Validator.Time),
      'endTime': (False, testlog_validator.Validator.Time),
      'duration': (False, testlog_validator.Validator.Float),
      'operatorId': (False, testlog_validator.Validator.String),
      'attachments': (False, _ValidatorAttachmentWrapper),
      'failures': (False, testlog_validator.Validator.List),
      'serialNumbers': (False, testlog_validator.Validator.Dict),
      'parameters': (False, testlog_validator.Validator.Dict),
      'series': (False, testlog_validator.Validator.Dict),
  }

  # Possible values for the `status` field.
  # TODO(itspeter): Check on log when will UNKNOWN emitted.
  STATUS = type_utils.Enum([
      'STARTING', 'RUNNING', 'FAILED', 'PASSED',
      'UNKNOWN'])  # States that doesn't apply for StationTestRun

  @classmethod
  def GetEventType(cls):
    return 'station.test_run'

  def CastFields(self):
    if 'series' in self:
      s = Series(__METADATA__=dict())
      s.update(self['series'])
      self['series'] = s

  def LogParam(self, name, value, description=None, value_unit=None):
    """Logs parameters as specified in Testlog API."""
    value_dict = dict()
    if isinstance(value, basestring):
      value_dict['textValue'] = value
    elif isinstance(value, (int, long, float)):
      value_dict['numericValue'] = value
    else:
      raise ValueError(
          'LogParam supports only numeric or text, not %r' % value)

    if description:
      value_dict.update({'description': description})
    if value_unit:
      value_dict.update({'valueUnit': value_unit})
    self['parameters'] = {'key': name, 'value': value_dict}
    return self

  def AttachFile(self, path, mime_type, name, delete=True, description=None):
    """Attaches a file as specified in Testlog API."""
    value_dict = {'mimeType': mime_type,
                  'path': path}
    if description:
      value_dict.update({'description': description})
    self['attachments'] = {'key': name, 'value': value_dict, 'delete': delete}
    return self

  def CreateSeries(self, name,
                   description=None, key_unit=None, value_unit=None):
    """Returns a Series object as specified in Testlog API."""
    value_dict = dict()
    if description:
      value_dict['description'] = description
    if key_unit:
      value_dict['keyUnit'] = key_unit
    if value_unit:
      value_dict['valueUnit'] = value_unit
    s = Series(__METADATA__=value_dict)
    self['series'] = {'key': name, 'value': s}
    return s


class Series(dict):
  def __init__(*args, **kwargs):  # pylint: disable=E0211
    # Allowed only a specific form of initialization.
    assert len(args) == 1  # Expecting only self
    assert isinstance(kwargs['__METADATA__'], dict)
    super(Series, args[0]).__init__(kwargs['__METADATA__'])

  @staticmethod
  def CheckIsNumeric(v):
    return isinstance(v, (int, long, float))

  @staticmethod
  def _CheckArguments(key, value, min_val, max_val):
    # Only accept numeric value.
    for v in [key, value]:
      if not Series.CheckIsNumeric(v):
        raise ValueError('%r is not a numeric' % v)

    # Only accept numeric value or None
    for v in [min_val, max_val]:
      if v is not None and not Series.CheckIsNumeric(v):
        raise ValueError('%r is not a numeric or None' % v)

  def _LogValue(self, key, value, status, min_val, max_val):
    value_dict = {'key': key, 'numericValue': value}
    if status:
      value_dict['status'] = status
    if min_val:
      value_dict['expectedMinimum'] = min_val
    if max_val:
      value_dict['expectedMaximum'] = max_val

    if 'data' not in self:
      self['data'] = list()
    self['data'].append(value_dict)
    # Update the session JSON
    if GetGlobalTestlog().last_test_run:
      Log(GetGlobalTestlog().last_test_run)

  def LogValue(self, key, value):
    Series._CheckArguments(key, value, None, None)
    self._LogValue(key, value, None, None, None)

  def CheckValue(self, key, value, min=None, max=None):  # pylint: disable=W0622
    Series._CheckArguments(key, value, min, max)
    result = testlog_utils.IsInRange(value, min_val=min, max_val=max)
    result = 'PASS' if result else 'FAIL'
    self._LogValue(key, value, result, min, max)
    return result
