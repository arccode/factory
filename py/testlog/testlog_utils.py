# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Util functions that served for testlog module."""

import datetime
import inspect
import traceback

from .utils import time_utils


class TestlogError(Exception):
  """Catch-all exception for testlog Python API."""


def JSONHandler(obj):
  """Handler for serializing objects during conversion to JSON."""
  if isinstance(obj, datetime.datetime):
    # Change datetime.datetime obj to Unix time.
    return '%.6f' % time_utils.DatetimeToUnixtime(obj)
  if isinstance(obj, datetime.date):
    # Currently we didn't expect obj in this type
    return obj.isoformat()
  if isinstance(obj, datetime.time):
    # Currently we didn't expect obj in this type
    return obj.strftime('%H:%M')
  if inspect.istraceback(obj):
    tb = ''.join(traceback.format_tb(obj))
    return tb.strip()
  if isinstance(obj, Exception):
    return 'Exception: %s' % str(obj)
  return str(obj)


def IsInRange(observed, min_val, max_val):
  """Returns True if min_val <= observed <= max_val.

  If any of min_val or max_val is missing, it means there is no lower or
  upper bounds respectively.
  """
  if min_val is not None and observed < min_val:
    return False
  if max_val is not None and observed > max_val:
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
  if not hasattr(node, '__iter__') or isinstance(node, str):
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
      for key, value in node.items():
        if key in ignore_keys:
          continue
        for ret in FlattenAttrs(
            value, path + str(key), allow_types, ignore_keys):
          yield ret

    # List-like node.
    else:
      for i, item in enumerate(node):
        for ret in FlattenAttrs(
            item, path + str(i), allow_types, ignore_keys):
          yield ret
