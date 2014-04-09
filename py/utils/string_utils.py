#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This module provides utility functions for string processing."""


import logging


def DecodeUTF8(data):
  """Decodes data as UTF-8, replacing any bad characters."""
  if isinstance(data, unicode):
    return data
  else:
    return unicode(data, encoding='utf-8', errors='replace')

def CleanUTF8(data):
  """Returns a UTF-8-clean string."""
  return DecodeUTF8(data).encode('utf-8')

def ParseDict(lines, delimeter=':'):
  """Parses list of lines into a dict. Each line is a string containing
  key, value pair, where key and value are separated by delimeter, and are
  stripped. If key, value pair can not be found in the line, that line will be
  skipped.

  Args:
    lines: A list of strings.
    delimeter: The delimeter string to separate key and value in each line.

  Returns:
    A dict, where both keys and values are string.
  """
  ret = dict()
  for line in lines:
    try:
      key, value = line.split(delimeter)
    except ValueError:
      logging.warning('Can not extract key, value pair in %s', line)
    else:
      ret[key.strip()] = value.strip()
  return ret

def ParseString(value):
  """Parses a string if it is actually a True/False/None/Int value.

  Args:
    value: A string.

  Returns:
    True if the string matches one of 'True' and 'true. False if the string
    matches one of 'False' and 'false'. None if the string matches 'None'.
    An int if the string can be casted to an integer. Returns a string if
    nothing matched.
  """
  if value in ['True', 'true']:
    value = True
  elif value in ['False', 'false']:
    value = False
  elif value == 'None':
    value = None
  else:
    try:
      value = int(value)
    except ValueError:
      pass  # No sweat
  return value
