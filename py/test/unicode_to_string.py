#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrappers to convert Unicode strings to UTF-8 strings."""

import types


def UnicodeToString(obj):
  '''Converts any Unicode strings in obj to UTF-8 strings.

  Recurses into lists, dicts, and tuples in obj.
  '''
  if isinstance(obj, list):
    return [UnicodeToString(x) for x in obj]
  elif isinstance(obj, dict):
    return dict((UnicodeToString(k), UnicodeToString(v))
                for k, v in obj.iteritems())
  elif isinstance(obj, unicode):
    return obj.encode('utf-8')
  elif isinstance(obj, tuple):
    return tuple(UnicodeToString(x) for x in obj)
  elif isinstance(obj, set):
    return set(UnicodeToString(x) for x in obj)
  else:
    return obj


def UnicodeToStringArgs(function):
  '''A function decorator that converts function's arguments from
  Unicode to strings using UnicodeToString.
  '''
  return (lambda *args, **kwargs:
          function(*UnicodeToString(args),
                   **UnicodeToString(kwargs)))


def UnicodeToStringClass(cls):
  '''A class decorator that converts all arguments of all
  methods in class from Unicode to strings using UnicodeToStringArgs.'''
  for k, v in cls.__dict__.items():
    if type(v) == types.FunctionType:
      setattr(cls, k, UnicodeToStringArgs(v))
  return cls
