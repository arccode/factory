# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Util functions that served for testlog module."""

import datetime
import inspect
import traceback


class TestlogError(Exception):
  """Catch-all exception for testlog Python API."""
  pass


def ToJSONDateTime(time_value):
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


def FromJSONDateTime(string_value):
  """Returns a datetime object parsed from a string.

  Reverses ToJSONDateTime.

  Keep as a separate function in case client code would like to use it
  in the future.
  """
  return datetime.datetime.strptime(string_value, '%Y-%m-%dT%H:%M:%S.%fZ')


def JSONHandler(obj):
  """Handler for serializing objects during conversion to JSON."""
  if isinstance(obj, datetime.datetime):
    return ToJSONDateTime(obj)
  elif isinstance(obj, datetime.date):
    # Currently we didn't expect obj in this type
    return obj.isoformat()
  elif isinstance(obj, datetime.time):
    # Currently we didn't expect obj in this type
    return obj.strftime('%H:%M')
  elif inspect.istraceback(obj):
    tb = ''.join(traceback.format_tb(obj))
    return tb.strip()
  elif isinstance(obj, Exception):
    return 'Exception: %s' % str(obj)
  return str(obj)


def IsInRange(observed, min_val, max_val):
  """Returns True if min_val <= observed <= max_val.

  If any of min_val or max_val is missing, it means there is no lower or
  upper bounds respectively.
  """
  if min_val and observed < min_val:
    return False
  if max_val and observed > max_val:
    return False
  return True


def FlattenAttrs(node, path=u'', allow_types=None, ignore_keys=None):
  """Flatten a nested dict/list data structure into (key-path, value) pairs.

  e.g. {'a': {'b': 'c'}} => [(u'a.b', 'c')]

  Keys of list elements are taken to be their enumerated IDs.

  e.g. {'a': [1, 2]} => [(u'a.0', 1), (u'a.1', 2)]

  Empty lists/dicts are mapped to None.

  e.g. {'a': []} => [(u'a', None)]

  Args:
    allow_types: A list or tuple of allowed value types.  Any other types will
        be converted to a string using __repr__.  If set to None, any value
        types are allowed.

  Returns:
    A generator list of (key-path, value) tuples.  Key-paths are Unicode
    strings, composed of all the keys required to walk to the particular node,
    separated by periods.
  """
  ignore_keys = [] if ignore_keys is None else ignore_keys
  if not hasattr(node, '__iter__'):
    if allow_types is not None and not isinstance(node, tuple(allow_types)):
      yield path, repr(node)
    else:
      yield path, node
  else:
    # Empty list/dict node.
    if not node:
      yield path, None

    if path:
      path += u'.'

    # Dict node.
    if isinstance(node, dict):
      for key, value in node.iteritems():
        if key in ignore_keys:
          continue
        for ret in FlattenAttrs(
            value, path + unicode(key), allow_types, ignore_keys):
          yield ret

    # List-like node.
    else:
      for i, item in enumerate(node):
        for ret in FlattenAttrs(
            item, path + unicode(i), allow_types, ignore_keys):
          yield ret
