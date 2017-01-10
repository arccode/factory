# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""JSON-related utilities."""

# TODO(kitching): Consider moving this to the cros.factory.utils directory.

from __future__ import print_function

import datetime
import inspect
import json
import traceback


FORMAT_DATETIME = '%Y-%m-%dT%H:%M:%S.%fZ'
FORMAT_DATE = '%Y-%m-%d'
FORMAT_TIME = '%H:%M:%S.%f'


class JSONEncoder(json.JSONEncoder):

  def default(self, obj):  # pylint: disable=E0202
    """Handler for serializing objects during conversion to JSON.

    Outputs datetime, date, and time objects with enough metadata to restore
    as their former objects when deserialized.
    """
    if isinstance(obj, Serializable):
      dct = obj.ToDict()
      dct['__type__'] = obj.__class__.__name__
      return dct
    if isinstance(obj, datetime.datetime):
      return {
          '__type__': 'datetime',
          'value': obj.strftime(FORMAT_DATETIME)}
    if isinstance(obj, datetime.date):
      return {
          '__type__': 'date',
          'value': obj.strftime(FORMAT_DATE)}
    if isinstance(obj, datetime.time):
      return {
          '__type__': 'time',
          'value': obj.strftime(FORMAT_TIME)}
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

  def object_hook(self, dct):  # pylint: disable=E0202
    """Handler for deserializing objects after conversion to JSON.

    Restores datetime, date, and time objects using the metadata output from
    matching JSONDecoder class.
    """
    if dct.get('__type__') in self._class_registry:
      return self._class_registry[dct['__type__']].FromDict(dct)
    # TODO(kitching): Remove legacy __datetime__, __date__, and __time__ checks.
    if dct.get('__type__') == 'datetime' or '__datetime__' in dct:
      return datetime.datetime.strptime(dct['value'], FORMAT_DATETIME)
    if dct.get('__type__') == 'date' or '__date__' in dct:
      return datetime.datetime.strptime(dct['value'], FORMAT_DATE).date()
    if dct.get('__type__') == 'time' or '__time__' in dct:
      return datetime.datetime.strptime(dct['value'], FORMAT_TIME).time()
    return dct


# Class registry maps class name => class reference for Serializable subclasses.
_class_registry = {}
_encoder = JSONEncoder()
_decoder = JSONDecoder(class_registry=_class_registry)


class SerializableMeta(type):
  """Metaclass to collect Serializable classes into a class registry."""

  def __new__(mcs, name, bases, class_dict):
    cls = type.__new__(mcs, name, bases, class_dict)
    if cls.__name__ in _class_registry:
      raise RuntimeError('Multiple serializable classes with name "%s"'
                         % cls.__name__)
    _class_registry[cls.__name__] = cls
    return cls


class Serializable(object):
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

  __metaclass__ = SerializableMeta

  def Serialize(self):
    """Serializes this object to a JSON string."""
    return _encoder.encode(self)

  @classmethod
  def Deserialize(cls, json_string):
    """Deserializes the JSON string into its corresponding Python object."""
    ret = _decoder.decode(json_string)
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
  return _decoder.decode(json_string)


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
