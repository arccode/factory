# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""JSON-related utilities."""

# TODO(kitching): Consider moving this to the cros.factory.utils directory.

import datetime
import inspect
import json
import logging
import traceback


# This is ISO 8601 format of date/time/datetime. If you want to change this,
# you have to also change the FastStringParseDate/Time/Datetime function
# and isoformat() below.
FORMAT_DATETIME = '%Y-%m-%dT%H:%M:%S.%fZ'
FORMAT_DATE = '%Y-%m-%d'
FORMAT_TIME = '%H:%M:%S.%f'


def FastStringParseDate(date_string):
  """Parses the date_string with FORMAT_DATE to datetime.date"""
  if len(date_string) != 10 or date_string[4] != '-' or date_string[7] != '-':
    raise ValueError('Wrong format string: %s' % date_string)
  return datetime.date(
      int(date_string[0:4]),
      int(date_string[5:7]),
      int(date_string[8:10]))


def FastStringParseTime(date_string):
  """Parses the date_string with FORMAT_TIME to datetime.time"""
  if (len(date_string) != 15 or date_string[2] != ':' or
      date_string[5] != ':' or date_string[8] != '.'):
    raise ValueError('Wrong format string: %s' % date_string)
  return datetime.time(
      int(date_string[0:2]),
      int(date_string[3:5]),
      int(date_string[6:8]),
      int(date_string[9:15]))


def FastStringParseDatetime(date_string):
  """Parses the date_string with FORMAT_DATETIME to datetime.datetime"""
  if len(date_string) != 27 or date_string[10] != 'T' or date_string[26] != 'Z':
    raise ValueError('Wrong format string: %s' % date_string)
  return datetime.datetime.combine(
      FastStringParseDate(date_string[0:10]),
      FastStringParseTime(date_string[11:26]))


class JSONEncoder(json.JSONEncoder):

  def default(self, obj):  # pylint: disable=method-hidden, arguments-differ
    """Handler for serializing objects during conversion to JSON.

    Outputs datetime, date, and time objects with enough metadata to restore
    as their former objects when deserialized.
    """
    if isinstance(obj, Serializable):
      dct = obj.ToDict()
      dct['__type__'] = obj.__class__.__name__
      return dct
    if isinstance(obj, datetime.datetime):
      assert obj.tzinfo is None
      # obj.isoformat() will ignore microsecond if obj.microsecond is 0.
      return {
          '__type__': 'datetime',
          'value': obj.isoformat() + (
              '.000000Z' if obj.microsecond == 0 else 'Z')}
    if isinstance(obj, datetime.date):
      return {
          '__type__': 'date',
          'value': obj.isoformat()}
    if isinstance(obj, datetime.time):
      assert obj.tzinfo is None
      # obj.isoformat() will ignore microsecond if obj.microsecond is 0.
      return {
          '__type__': 'time',
          'value': obj.isoformat() + (
              '.000000' if obj.microsecond == 0 else '')}
    if inspect.istraceback(obj):
      tb = ''.join(traceback.format_tb(obj))
      return tb.strip()
    if isinstance(obj, Exception):
      return 'Exception: %s' % str(obj)

    # Base class default method may raise TypeError.
    try:
      return json.JSONEncoder.default(self, obj)
    except TypeError:
      return str(obj)


class JSONDecoder(json.JSONDecoder):

  def __init__(self, *args, **kwargs):
    self._class_registry = kwargs.pop('class_registry', {})
    json.JSONDecoder.__init__(
        self, object_hook=self.object_hook, *args, **kwargs)

  def object_hook(self, dct):  # pylint: disable=method-hidden
    """Handler for deserializing objects after conversion to JSON.

    Restores datetime, date, and time objects using the metadata output from
    matching JSONDecoder class.
    """
    if dct.get('__type__') in self._class_registry:
      return self._class_registry[dct['__type__']].FromDict(dct)
    # TODO(kitching): Remove legacy __datetime__, __date__, and __time__ checks.
    if dct.get('__type__') == 'datetime' or '__datetime__' in dct:
      try:
        return FastStringParseDatetime(dct['value'])
      except ValueError:
        logging.warning('Fast strptime failed: %s', dct['value'])
        return datetime.datetime.strptime(dct['value'], FORMAT_DATETIME)
    if dct.get('__type__') == 'date' or '__date__' in dct:
      try:
        return FastStringParseDate(dct['value'])
      except ValueError:
        logging.warning('Fast strptime failed: %s', dct['value'])
        return datetime.datetime.strptime(dct['value'], FORMAT_DATE).date()
    if dct.get('__type__') == 'time' or '__time__' in dct:
      try:
        return FastStringParseTime(dct['value'])
      except ValueError:
        logging.warning('Fast strptime failed: %s', dct['value'])
        return datetime.datetime.strptime(dct['value'], FORMAT_TIME).time()
    return dct


# Class registry maps class name => class reference for Serializable subclasses.
_class_registry = {}
encoder = JSONEncoder()
decoder = JSONDecoder(class_registry=_class_registry)


class SerializableMeta(type):
  """Metaclass to collect Serializable classes into a class registry."""

  def __new__(cls, name, bases, class_dict):
    mcs = type.__new__(cls, name, bases, class_dict)
    if mcs.__name__ in _class_registry:
      raise RuntimeError('Multiple serializable classes with name "%s"'
                         % mcs.__name__)
    _class_registry[mcs.__name__] = mcs
    return mcs


class Serializable(metaclass=SerializableMeta):
  """Superclass to allow object serialization and deserialization.

  Usage (note order of the classes in the inheritance list):

    class MyClass(json_utils.Serializable, MyBaseClass):

      def __init__(self, my_data):
        self.my_data = my_data

      def ToDict(self):
        return {'my_data': self.my_data}

      @classmethod
      def FromDict(self, dct):
        return MyClass(dct['my_data'])
  """

  def Serialize(self):
    """Serializes this object to a JSON string."""
    return encoder.encode(self)

  @classmethod
  def Deserialize(cls, json_string):
    """Deserializes the JSON string into its corresponding Python object."""
    ret = decoder.decode(json_string)
    if not isinstance(ret, cls):
      raise ValueError('Given JSON string does not contain "%s" instance'
                       % cls.__name__)
    return ret

  def ToDict(self):
    """Returns the dictionary equivalent of the object."""
    raise NotImplementedError

  @classmethod
  def FromDict(cls, dct):
    """Returns the object from its dictionary equivalent."""
    raise NotImplementedError


def Deserialize(json_string):
  """Deserializes any JSON string using json_utils's class registry."""
  return decoder.decode(json_string)


def WalkJSONPath(json_path, data):
  """Retrieves part of a Python dictionary by walking a JSONPath-like pattern.

  Uses a simplified version of jq's JSON querying language to select
  to select information out of the dictionary.  The supported operators
  are "." and "[]".

  Example:
    {'hello': {'world': [100, 200]}}

    ".hello.world[0]"  ==> 100
    ".hello.world[-1]" ==> 200
    ".hello.world"     ==> [100, 200]
    "."                ==> {'hello': {'world': [100, 200]}}
  """
  def ChompNextPart(json_path):
    """Splits the JSON path into the next operator, and everything else."""
    dict_operator_pos = json_path.find('.', 1)
    list_operator_pos = json_path.find('[', 1)
    if dict_operator_pos == -1:
      dict_operator_pos = len(json_path)
    if list_operator_pos == -1:
      list_operator_pos = len(json_path)
    cut = min(dict_operator_pos, list_operator_pos)
    return json_path[:cut], json_path[cut:]

  if not json_path:
    return data
  current, left = ChompNextPart(json_path)
  try:
    if current == '.':
      return WalkJSONPath(left, data)
    if current.startswith('.'):
      return WalkJSONPath(left, data[current[1:]])
    if current.startswith('['):
      return WalkJSONPath(left, data[int(current[1:-1])])
  except (KeyError, TypeError):
    raise ValueError('Could not access %s' % json_path)
  else:
    raise ValueError('Invalid syntax found at %s' % json_path)
