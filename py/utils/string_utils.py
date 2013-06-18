#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging


def DecodeUTF8(data):
  '''Decodes data as UTF-8, replacing any bad characters.'''
  return unicode(data, encoding='utf-8', errors='replace')

def CleanUTF8(data):
  '''Returns a UTF-8-clean string.'''
  return DecodeUTF8(data).encode('utf-8')

def ParseDict(lines, delimeter=':'):
  '''Parses list of lines into a dict. Each line is a string containing
  key, value pair, where key and value are separated by delimeter, and are
  stripped. If key, value pair can not be found in the line, that line will be
  skipped.

  Args:
    lines: A list of strings.
    delimeter: The delimeter string to separate key and value in each line.

  Returns:
    A dict, where both keys and values are string.
  '''
  ret = dict()
  for line in lines:
    try:
      key, value = line.split(delimeter)
    except ValueError:
      logging.warning('Can not extract key, value pair in %s', line)
    else:
      ret[key.strip()] = value.strip()
  return ret
