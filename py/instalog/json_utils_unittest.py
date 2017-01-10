#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for JSON-related utilities."""

from __future__ import print_function

import datetime
import logging
import unittest

import instalog_common  # pylint: disable=W0611
from instalog import json_utils
from instalog import log_utils


_SAMPLE_DATETIME = datetime.datetime(1989, 12, 12, 12, 12, 12, 12)
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
    self.assertEquals(dec.decode(enc.encode(orig)), orig)

  def testSerializable(self):
    orig = A('test')
    self.assertEquals(orig.data, A.Deserialize(orig.Serialize()).data)
    self.assertEquals(orig.data, json_utils.Deserialize(orig.Serialize()).data)

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


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG, format=log_utils.LOG_FORMAT)
  unittest.main()
