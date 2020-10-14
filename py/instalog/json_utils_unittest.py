#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for JSON-related utilities."""

import datetime
import logging
import unittest

from cros.factory.instalog import json_utils
from cros.factory.instalog import log_utils


_SAMPLE_DATETIME = datetime.datetime(1989, 12, 12, 12, 12, 12, 120)
_SAMPLE_DATE = _SAMPLE_DATETIME.date()
_SAMPLE_TIME = _SAMPLE_DATETIME.time()


class A(json_utils.Serializable):

  def __init__(self, data):
    self.data = data

  def ToDict(self):
    return {'data': self.data}

  @classmethod
  def FromDict(cls, dct):
    return A(dct['data'])


class B(json_utils.Serializable):

  def __init__(self, data):
    self.data = data

  def ToDict(self):
    return {'data': self.data}

  @classmethod
  def FromDict(cls, dct):
    return B(dct['data'])


class TestJSONUtils(unittest.TestCase):

  def testRoundTrip(self):
    """Tests that datetime, date, and time can all survive encode/decode."""
    enc = json_utils.JSONEncoder()
    dec = json_utils.JSONDecoder()
    orig = [_SAMPLE_DATETIME, _SAMPLE_DATE, _SAMPLE_TIME, 'test_string']
    self.assertEqual(dec.decode(enc.encode(orig)), orig)

  def testSerializable(self):
    orig = A('test')
    self.assertEqual(orig.data, A.Deserialize(orig.Serialize()).data)
    self.assertEqual(orig.data, json_utils.Deserialize(orig.Serialize()).data)

  def testRecursiveSerialize(self):
    orig = A(B('test'))
    self.assertTrue(isinstance(A.Deserialize(orig.Serialize()), A))
    self.assertTrue(isinstance(A.Deserialize(orig.Serialize()).data, B))
    self.assertTrue(isinstance(json_utils.Deserialize(orig.Serialize()), A))
    self.assertTrue(
        isinstance(json_utils.Deserialize(orig.Serialize()).data, B))
    with self.assertRaises(ValueError):
      B.Deserialize(orig.Serialize())

  def testDuplicateClassName(self):
    with self.assertRaises(RuntimeError):
      # pylint: disable=redefined-outer-name,abstract-method,unused-variable
      class A(json_utils.Serializable):

        pass


class TestWalkJSONPath(unittest.TestCase):

  def testEdgeCases(self):
    self.assertEqual({}, json_utils.WalkJSONPath('....', {}))
    self.assertEqual({}, json_utils.WalkJSONPath('', {}))
    self.assertEqual([], json_utils.WalkJSONPath('....', []))
    self.assertEqual(1, json_utils.WalkJSONPath('....[0]', [1]))

  def testExamples(self):
    data = {'hello': {'world': [100, 200]}}

    self.assertEqual(100,
                     json_utils.WalkJSONPath('.hello.world[0]', data))
    self.assertEqual(200,
                     json_utils.WalkJSONPath('.hello.world[-1]', data))
    with self.assertRaises(IndexError):
      json_utils.WalkJSONPath('.hello.world[-10]', data)
    self.assertEqual([100, 200],
                     json_utils.WalkJSONPath('.hello.world', data))
    self.assertEqual({'hello': {'world': [100, 200]}},
                     json_utils.WalkJSONPath('.', data))


class TestFastStringParseDatetime(unittest.TestCase):

  def testFastStringParseDate(self):
    time_now = _SAMPLE_DATE
    time_now_string = time_now.strftime(json_utils.FORMAT_DATE)
    self.assertEqual(time_now,
                     json_utils.FastStringParseDate(time_now_string))

    # Wrong length.
    with self.assertRaisesRegex(ValueError, r'Wrong format string'):
      json_utils.FastStringParseDate(time_now_string + ' ')
    # Wrong symbol.
    with self.assertRaisesRegex(ValueError, r'Wrong format string'):
      wrong_time_string = time_now_string[:4] + ':' + time_now_string[5:]
      json_utils.FastStringParseDate(wrong_time_string)
    # Year with non-integer.
    with self.assertRaisesRegex(ValueError, r'invalid literal for int'):
      wrong_time_string = time_now_string[:3] + '?' + time_now_string[4:]
      json_utils.FastStringParseDate(wrong_time_string)
    # The 13th month.
    with self.assertRaisesRegex(ValueError, r'month must be in 1..12'):
      wrong_time_string = time_now_string[:5] + '13' + time_now_string[7:]
      json_utils.FastStringParseDate(wrong_time_string)

  def testFastStringParseTime(self):
    time_now = _SAMPLE_TIME
    time_now_string = time_now.strftime(json_utils.FORMAT_TIME)
    self.assertEqual(time_now,
                     json_utils.FastStringParseTime(time_now_string))

    # Wrong length.
    with self.assertRaisesRegex(ValueError, r'Wrong format string'):
      json_utils.FastStringParseTime(time_now_string + ' ')
    # Wrong symbol.
    with self.assertRaisesRegex(ValueError, r'Wrong format string'):
      wrong_time_string = time_now_string[:2] + '-' + time_now_string[3:]
      json_utils.FastStringParseTime(wrong_time_string)
    # Microsecond with non-integer.
    with self.assertRaisesRegex(ValueError, r'invalid literal for int'):
      wrong_time_string = time_now_string[:-1] + '?'
      json_utils.FastStringParseTime(wrong_time_string)
    # The 60th second.
    with self.assertRaisesRegex(ValueError, r'second must be in 0..59'):
      wrong_time_string = time_now_string[:6] + '60' + time_now_string[8:]
      json_utils.FastStringParseTime(wrong_time_string)

  def testFastStringParseDatetime(self):
    time_now = _SAMPLE_DATETIME
    time_now_string = time_now.strftime(json_utils.FORMAT_DATETIME)
    self.assertEqual(time_now,
                     json_utils.FastStringParseDatetime(time_now_string))

    # Wrong length.
    with self.assertRaisesRegex(ValueError, r'Wrong format string'):
      json_utils.FastStringParseDatetime(time_now_string + ' ')
    # Wrong alphabet.
    with self.assertRaisesRegex(ValueError, r'Wrong format string'):
      wrong_time_string = time_now_string[:-1] + 'Y'
      json_utils.FastStringParseDatetime(wrong_time_string)
    # The 13th month.
    with self.assertRaisesRegex(ValueError, r'month must be in 1..12'):
      wrong_time_string = time_now_string[:5] + '13' + time_now_string[7:]
      json_utils.FastStringParseDatetime(wrong_time_string)

  def testSlowParse(self):
    dec = json_utils.JSONDecoder()
    time_dct = _SAMPLE_DATETIME
    wrong_time_string = (
        '{"__type__": "datetime", "value": "1989-12-12T12:12:12.00012Z"}')
    self.assertEqual(time_dct, dec.decode(wrong_time_string))


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
