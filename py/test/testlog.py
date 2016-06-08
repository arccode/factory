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
import inspect
import json
import logging
import threading
import traceback
import os
import shutil
from uuid import uuid4


# TODO(itspeter): Find a way to properly pack those as testlog should
# be able to deploy without factory framework.
import factory_common  # pylint: disable=W0611
from cros.factory.test import testlog_seq
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
      self.last_test_run._data[self.FIELDS._METADATA] = metadata
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
        'startTime': _ToJSONDateTime(datetime.datetime.utcnow())
        })
  # pylint: disable=W0212
  station_test_run._data[Testlog.FIELDS._METADATA] = {
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
      # TODO(itspeter): Fix the populate method
      test_run = StationTestRun()
      test_run.Populate(session_json)
      # Merge the station_test_run information.
      if station_test_run:
        data = {
            'status': station_test_run['status'],
            'endTime': station_test_run['endTime'],
            'duration': station_test_run['duration']}
        if 'failures' in station_test_run:
          data['failures'] = station_test_run['failures']
        test_run.Populate(data)
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
    testlog_singleton.session_json.Log(event)


def LogParam(*args, **kwargs):
  """Wrapper for StationTestRun.LogParam().

  We provide this wrapper as a handy interface that caller can use
  testlog.LogParam() instead of GetGlobalTestlog().last_test_run.LogParam().
  This function is expected to call only in test session but not test harness,
  because only test session expected to have GetGlobalTestlog().last_test_run.

  Please see the StationTestRun.LogParam() for more details.
  """
  if GetGlobalTestlog().last_test_run:
    GetGlobalTestlog().last_test_run.LogParam(*args, **kwargs)
  else:
    raise TestlogError('In memory station.test_run does not set. '
                       'Test harness need to set it manually.')


class JSONLogFile(file_utils.FileLockContextManager):
  """Represents a JSON log file on disk."""

  def __init__(self, uuid, seq_generator, path, mode='a'):
    super(JSONLogFile, self).__init__(path=path, mode=mode)
    self.test_run_id = uuid
    self.seq_generator = seq_generator

  def Log(self, event):
    """Converts event into JSON string and writes into disk."""
    log_stamp = {  # Data that should be refresh at every write operation.
        'id': str(uuid4()),
        'seq': self.seq_generator.Next()}
    event.PopAndSet(log_stamp, 'id', None)
    event.PopAndSet(log_stamp, 'seq', None)
    line = event.ToJSON() + '\n'
    with self:
      self.file.write(line)
      self.file.flush()
      os.fsync(self.file.fileno())
    return line


class TestlogError(Exception):
  """Catch-all exception for testlog Python API."""
  pass


def _ToJSONDateTime(time_value):
  """Returns a time as a string.

  Keep as a separate function in case client code would like to use it
  in the future.

  The format is like ISO8601 but with milliseconds:
    2012-05-22T14:15:08.123Z

  Note that isoformat() strips off milliseconds completely (including decimal)
  when the value returned is at an even second.
  """
  time_str = time_value.isoformat()
  if '.' in time_str:
    return time_str[:-3] + 'Z'
  else:
    return time_str + '.000Z'


def _FromJSONDateTime(string_value):
  """Returns a datetime object parsed from a string.

  Keep as a separate function in case client code would like to use it
  in the future.

  Reverses _ToJSONDateTime.
  """
  return datetime.datetime.strptime(string_value, '%Y-%m-%dT%H:%M:%S.%fZ')


def _JSONHandler(obj):
  """Handler for serializing objects during conversion to JSON."""
  if isinstance(obj, datetime.datetime):
    return _ToJSONDateTime(obj)
  elif isinstance(obj, datetime.date):
    return obj.isoformat()
  elif isinstance(obj, datetime.time):
    return obj.strftime('%H:%M')
  elif inspect.istraceback(obj):
    tb = ''.join(traceback.format_tb(obj))
    return tb.strip()
  elif isinstance(obj, Exception):
    return 'Exception: %s' % str(obj)
  return str(obj)


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
  """

  def __init__(self, data=None):
    """Only allow initialization for classes that declared GetEventType()."""
    try:
      if self.GetEventType():
        self._data = {}
        self.Populate(data or {})
        return
    except NotImplementedError:
      pass
    raise TestlogError('Must initialize directly from desired event class.')

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

  def __contains__(self, item):
    """Supports `in` operator."""
    return item in self._data

  @classmethod
  def GetEventType(cls):
    """Returns the event type of this particular object."""
    raise NotImplementedError

  def Populate(self, data):
    """Populates this object using the provided data dict."""
    raise NotImplementedError

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
    except TestlogError:
      raise TestlogError('Input event does not have a valid `type`.')

  @classmethod
  def FromJSON(cls, json_string):
    """Converts JSON data into an Event instance."""
    return cls.FromDict(json.loads(json_string))

  @classmethod
  def FromDict(cls, data):
    """Converts Python dict data into an Event instance."""
    event = cls.DetermineClass(data)()
    event.Populate(data)
    return event

  def ToJSON(self):
    """Returns a JSON string representing this event."""
    return json.dumps(self.ToDict(), default=_JSONHandler)

  def ToDict(self):
    """Returns a Python dict representing this event."""
    return self._data

  def PopAndSet(self, data, key, default):
    """Pops a value out of the given dictionary, and set it on the event.

    - If key exists in provided dictionary, pop the value from provided
      dictionary, and set the value on internal dictionary.
    - If key does not exist in provided dictionary and does not exist in
      internal dictionary, set the default value on internal dictionary.
    - If the key does not exist in provided dictionary and does exist in
      internal dictionary, leave it alone.
    """
    if key in data:
      self._data[key] = data.pop(key)
    elif key not in self._data:
      self._data[key] = default

  def __repr__(self):
    """Repr operator for string printing."""
    return '<{} data={}>'.format(self.__class__.__name__, repr(self._data))


class Event(EventBase):
  """Main event class.

  Defines common fields of all events in Populate function.
  """

  @classmethod
  def GetEventType(cls):
    return None

  def Populate(self, data):
    """Populates fields for event base class.

    Args:
      data: Dictionary that can contain:
          - id (string, required): Unique UUID of the event.
          - type (string, required): Type of the event.  Its value determines
            which fields are applicable to this event.
          - apiVersion (string, required): Version of the testlog API being
            used.
          - seq (integer, optional): Sequence number of the event, to help in
            cases where the station date is unreliable.  Should be monotonically
            increasing.
          - time (string, required): Date and time of the event.

    Returns:
      The event being modified (self).
    """
    if not self.GetEventType():
      raise TestlogError('Must initialize directly from desired event class')

    # Type field should already be consistent with the class type.
    data.pop('type', '')  # Pop the type if it exists.
    self.PopAndSet(data, 'type', self.GetEventType())

    self.PopAndSet(data, 'apiVersion', TESTLOG_API_VERSION)

    # Time field needs extra processing.
    d = None
    if 'time' in data:
      if isinstance(data['time'], basestring):
        d = _FromJSONDateTime(data.pop('time'))
      elif isinstance(data['time'], datetime.datetime):
        d = data.pop('time')
      else:
        raise TestlogError('Invalid `time` field')
    else:
      d = datetime.datetime.utcnow()
    # Round precision of microseconds to ensure equivalence after converting
    # to JSON and back again.
    d = d.replace(microsecond=(d.microsecond / 1000 * 1000))
    self._data['time'] = d

    # Return self for convenience.
    return self


class _StationBase(Event):
  """Fake event class for all "station" subtypes.

  Cannot be initialized.
  """

  @classmethod
  def GetEventType(cls):
    return None

  def Populate(self, data):
    """Populates fields for station base class.

    Args:
      data: Dictionary that can contain:
          - stationName (string, optional): Name of the station.
          - stationDeviceId (string, optional): ID of the device being used as
            the station.  This should be a value tied to the device (such as a
            MAC address) that will not change in the case that the device is
            reimaged.
          - stationReimageId (string, optional): ID of the reimage of the
            station.  Every time the station is reimaged, a new reimage ID
            should be generated (unique UUID).

    Returns:
      The event being modified (self).
    """
    self.PopAndSet(data, 'stationName', None)
    self.PopAndSet(data, 'stationDeviceId', None)
    self.PopAndSet(data, 'stationReimageId', None)
    return super(_StationBase, self).Populate(data)

class StationInit(_StationBase):
  """Represents the Station being brought up or initialized."""

  @classmethod
  def GetEventType(cls):
    return 'station.init'

  def Populate(self, data):
    """Populates fields for station init class.

    Args:
      data: Dictionary that can contain:
          - count (integer, required): Number of times that this station has
            been initialized so far.
          - success (boolean, required): Whether or not this station was
            successfully initialized.
          - failureMessage (string, optional): A failure string explaining why
            the station could not initialize.

    Returns:
      The event being modified (self).
    """
    self.PopAndSet(data, 'count', None)
    self.PopAndSet(data, 'success', None)
    self.PopAndSet(data, 'failureMessage', None)
    return super(StationInit, self).Populate(data)


class StationMessage(_StationBase):
  """Represents a Python message on the Station."""

  @classmethod
  def GetEventType(cls):
    return 'station.message'

  def Populate(self, data):
    """Populates fields for station message class.

    Args:
      data: Dictionary that can contain:
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

    Returns:
      The event being modified (self).
    """
    self.PopAndSet(data, 'filePath', None)
    self.PopAndSet(data, 'lineNumber', None)
    self.PopAndSet(data, 'functionName', None)
    self.PopAndSet(data, 'logLevel', None)
    self.PopAndSet(data, 'message', None)
    self.PopAndSet(data, 'testRunId', None)
    return super(StationMessage, self).Populate(data)


class StationTestRun(_StationBase):
  """Represents a test run on the Station."""

  # Possible values for the `status` field.
  # TODO(itspeter): Check on log when will UNKNOWN emitted.
  STATUS = type_utils.Enum([
      'STARTING', 'RUNNING', 'FAILED', 'PASSED',
      'UNKNOWN'])  # States that doesn't apply for StationTestRun


  @classmethod
  def GetEventType(cls):
    return 'station.test_run'

  @classmethod
  def FromTestRunState(cls, testlog_data):
    return Event.FromJSON(testlog_data)

  def LogParam(self, name, value, description=None, valueUnit=None):
    """Logs parameters as specified in Testlog API."""
    parameters = self['parameters'] if 'parameters' in self else dict()
    assert name not in parameters, 'Duplicated parameters %r' % name
    new_parameter = {'value': value}
    if description:
      new_parameter.update({'description': description})
    if valueUnit:
      new_parameter.update({'valueUnit': valueUnit})

    parameters[name] = new_parameter
    self.Populate(new_parameter)

  def Populate(self, data):
    """Populates fields for station test_run class.

    Args:
      data: Dictionary that can contain:
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
        - startTime (string, required): Date and time when the test started.
        - endTime (string, optional): Date and time when the test ended.
        - duration (number, optional): How long the test took to complete.
          Should be the same as endTime - startTime.  Included for convenience.
          Measured in seconds.

    Returns:
      The event being modified (self).
    """
    if data.get('status') not in [
        self.STATUS.STARTING, self.STATUS.RUNNING,
        self.STATUS.FAILED, self.STATUS.PASSED, None]:
      raise TestlogError('Invalid `status` field: %s' % data['status'])

    self.PopAndSet(data, 'testRunId', None)
    self.PopAndSet(data, 'testName', None)
    self.PopAndSet(data, 'testType', None)
    self.PopAndSet(data, 'status', None)
    self.PopAndSet(data, 'startTime', None)
    self.PopAndSet(data, 'endTime', None)
    self.PopAndSet(data, 'duration', None)
    self.PopAndSet(data, 'parameters', dict())

    return super(StationTestRun, self).Populate(data)
