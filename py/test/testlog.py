# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Python implementation of testlog JSON API."""


from __future__ import print_function

import datetime
import inspect
import json
import logging
import threading
import traceback
import uuid


TESTLOG_API_VERSION = '0.1'


_pylogger = None


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
  global _pylogger  # pylint: disable=W0603
  if _pylogger:
    # We are already capturing Python logging.
    return _pylogger

  log_handler = TestlogLogHandler(callback)
  log_handler.setFormatter(LogFormatter())
  _pylogger = logging.getLogger()
  _pylogger.addHandler(log_handler)
  _pylogger.setLevel(level)
  return _pylogger


class TestlogLogHandler(logging.Handler):
  """Format records into events and send them to callback function.

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
  """Format records into events."""

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

    self.PopAndSet(data, 'id', str(uuid.uuid4()))
    self.PopAndSet(data, 'apiVersion', TESTLOG_API_VERSION)
    self.PopAndSet(data, 'seq', -1)

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
  STARTING = 'STARTING'
  RUNNING = 'RUNNING'
  FAILED = 'FAILED'
  PASSED = 'PASSED'

  @classmethod
  def GetEventType(cls):
    return 'station.test_run'

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
        - testClass (string, required): A name identifying this type of test.
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
        None, self.STARTING, self.RUNNING, self.FAILED, self.PASSED]:
      raise TestlogError('Invalid `status` field: %s' % data['status'])

    self.PopAndSet(data, 'testRunId', None)
    self.PopAndSet(data, 'testName', None)
    self.PopAndSet(data, 'testClass', None)
    self.PopAndSet(data, 'status', None)
    self.PopAndSet(data, 'startTime', None)
    self.PopAndSet(data, 'endTime', None)
    self.PopAndSet(data, 'duration', None)
    return super(StationTestRun, self).Populate(data)
