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
    if isinstance(obj, datetime.datetime):
      return {
          '__datetime__': True,
          'value': obj.strftime(FORMAT_DATETIME)}
    elif isinstance(obj, datetime.date):
      return {
          '__date__': True,
          'value': obj.strftime(FORMAT_DATE)}
    elif isinstance(obj, datetime.time):
      return {
          '__time__': True,
          'value': obj.strftime(FORMAT_TIME)}
    elif inspect.istraceback(obj):
      tb = ''.join(traceback.format_tb(obj))
      return tb.strip()
    elif isinstance(obj, Exception):
      return 'Exception: %s' % str(obj)

    # Base class default method may raise TypeError.
    try:
      return json.JSONEncoder.default(self, obj)
    except TypeError:
      return str(obj)


class JSONDecoder(json.JSONDecoder):

  def __init__(self, *args, **kwargs):
    json.JSONDecoder.__init__(
        self, object_hook=self.object_hook, *args, **kwargs)

  def object_hook(self, dct):  # pylint: disable=E0202
    """Handler for deserializing objects after conversion to JSON.

    Restores datetime, date, and time objects using the metadata output from
    matching JSONDecoder class.
    """
    if '__datetime__' in dct:
      return datetime.datetime.strptime(dct['value'], FORMAT_DATETIME)
    if '__date__' in dct:
      return datetime.datetime.strptime(dct['value'], FORMAT_DATE).date()
    if '__time__' in dct:
      return datetime.datetime.strptime(dct['value'], FORMAT_TIME).time()
    return dct


def WalkJSONPath(json_path, data):
  """Retrieves part of a Python dictionary by walking a JSONPath-like pattern.

  Uses a simplified version of jq's JSON querying language to select
  to select information out of the dictionary.  The supported operators
  are "." and "[]".

  Example:
    {'hello': {'world': [100, 200]}}

    ".hello.world[0]" ==> 100
    ".hello.world"    ==> [100, 200]
    "."               ==> {'hello': {'world': [100, 200]}}
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
