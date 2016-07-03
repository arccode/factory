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
