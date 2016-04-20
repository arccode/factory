# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Python implementation of testlog JSON API."""


from __future__ import print_function

import datetime
import inspect
import json
import traceback
import uuid


TESTLOG_API_VERSION = '1.0'


def _ToJSONDateTime(time_value):
  """Returns a time as a string.

  Keep as a separate function in case client code would like to use it
  in the future.

  The format is like ISO8601 but with milliseconds:
    2012-05-22T14:15:08.123Z
  """
  return time_value.isoformat()[:-3] + 'Z'

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

class TestlogError(Exception):
  """Catch-all exception for testlog Python API."""
  pass

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
    else:
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

    Arguments:
      data: Dictionary that can contain:
          - type: Type of the event (corresponds to GetEventType()).
          - id: Unique UUID string of the event.
          - apiVersion: Testlog API version.
          - seq: Seq number (monotonically increasing ID) of the event.
          - time: Date and time the event was recorded.
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

class _StationBase(Event):
  """Fake event class for all "station" subtypes.

  Cannot be initialized.
  """

  @classmethod
  def GetEventType(cls):
    return None

  def Populate(self, data):
    """Populates fields for station base class.

    Arguments:
      data: Dictionary that can contain:
          - stationName: Unique string identifying the station.
          - stationDeviceId: Unique UUID identifying the station machine.
          - stationReimageId: Unique UUID identifying the current reimage on
                              the station.
    """
    self.PopAndSet(data, 'stationName', None)
    self.PopAndSet(data, 'stationDeviceId', None)
    self.PopAndSet(data, 'stationReimageId', None)
    super(_StationBase, self).Populate(data)

class StationInit(_StationBase):
  """Represents the Station being brought up or initialized."""

  @classmethod
  def GetEventType(cls):
    return 'station.init'

  def Populate(self, data):
    """Populates fields for station init class.

    Arguments:
      data: Dictionary that can contain:
          - count: Number of times this station has been initialized so far.
    """
    self.PopAndSet(data, 'count', None)
    super(StationInit, self).Populate(data)
