#!/usr/bin/env python3
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import datetime
import logging
import sys
import unittest

from cros.factory.testlog import testlog_utils

SAMPLE_UNIX_TIME = 618566888.888888
SAMPLE_DATETIME_STRING = '618566888.888888'
SAMPLE_DATETIME = datetime.datetime(1989, 8, 8, 8, 8, 8, 888888)

class TestlogUtilsTest(unittest.TestCase):

  def testIsInRange(self):
    self.assertEqual(False,
                     testlog_utils.IsInRange(30, min_val=None, max_val=0))
    self.assertEqual(True,
                     testlog_utils.IsInRange(30, min_val=0, max_val=None))
    self.assertEqual(True,
                     testlog_utils.IsInRange(30, min_val=None, max_val=30))
    self.assertEqual(False,
                     testlog_utils.IsInRange(30, min_val=None, max_val=29.99))
    self.assertEqual(True,
                     testlog_utils.IsInRange(30, min_val=30, max_val=None))
    self.assertEqual(False,
                     testlog_utils.IsInRange(30, min_val=30.01, max_val=None))
    self.assertEqual(True,
                     testlog_utils.IsInRange(30, min_val=None, max_val=None))
    self.assertEqual(True,
                     testlog_utils.IsInRange(30, min_val=29, max_val=31))
    self.assertEqual(False,
                     testlog_utils.IsInRange(31.1, min_val=29, max_val=31))

  def testJSONHandlerDateTime(self):
    obj = SAMPLE_DATETIME
    # pylint: disable=protected-access
    output = testlog_utils.JSONHandler(obj)
    self.assertEqual(output, SAMPLE_DATETIME_STRING)

  def testJSONHandlerDate(self):
    obj = datetime.date(1989, 8, 8)
    # pylint: disable=protected-access
    output = testlog_utils.JSONHandler(obj)
    self.assertEqual(output, '1989-08-08')

  def testJSONHandlerTime(self):
    obj = datetime.time(22, 10, 10)
    # pylint: disable=protected-access
    output = testlog_utils.JSONHandler(obj)
    self.assertEqual(output, '22:10')

  def testJSONHandlerExceptionAndTraceback(self):
    try:
      1 // 0
    except Exception:
      _, ex, tb = sys.exc_info()
      # pylint: disable=protected-access
      output = testlog_utils.JSONHandler(tb)
      self.assertTrue('1 // 0' in output)
      output = testlog_utils.JSONHandler(ex)
      self.assertTrue(output.startswith('Exception: '))

  def testFlattenAttrs(self):
    data = {'ignore': 1, 'level0': {'level1': ['item0', {'level2': ['item1']}]}}
    flattened = dict(testlog_utils.FlattenAttrs(data, ignore_keys=['ignore']))
    self.assertEqual(2, len(flattened))
    self.assertIn('level0.level1.0', flattened)
    self.assertEqual('item0', flattened['level0.level1.0'])
    self.assertNotIn('level0.level1', flattened)
    self.assertNotIn('level0.level1.1', flattened)
    self.assertIn('level0.level1.1.level2.0', flattened)
    self.assertEqual('item1', flattened['level0.level1.1.level2.0'])
    self.assertEqual({'': None}, dict(testlog_utils.FlattenAttrs(None)))

  def testFlattenAttrsWithAllowTypes(self):
    now = datetime.datetime.now()
    data = {'a': 1, 'b': now}
    flattened = dict(testlog_utils.FlattenAttrs(data))
    self.assertEqual(1, flattened['a'])
    self.assertEqual(now, flattened['b'])
    flattened = dict(testlog_utils.FlattenAttrs(data, allow_types=[int]))
    self.assertEqual(1, flattened['a'])
    self.assertEqual(repr(now), flattened['b'])
    self.assertIsInstance(flattened['b'], str)

if __name__ == '__main__':
  logging.basicConfig(
      format=('[%(levelname)s] '
              ' %(threadName)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=logging.INFO,
      datefmt='%Y-%m-%d %H:%M:%S')
  unittest.main()
