#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import datetime
import unittest
import logging
import sys

import factory_common  # pylint: disable=W0611
from cros.factory.test import testlog_utils

SAMPLE_DATETIME = datetime.datetime(1989, 8, 8, 8, 8, 8, 888888)
SAMPLE_DATETIME_STRING = '1989-08-08T08:08:08.888Z'
SAMPLE_DATETIME_ROUNDED_MIL = datetime.datetime(1989, 8, 8, 8, 8, 8, 888000)
SAMPLE_DATETIME_ROUNDED_SEC = datetime.datetime(1989, 8, 8, 8, 8, 8, 000000)

class TestlogUtilsTest(unittest.TestCase):

  def testIsInRange(self):
    self.assertEquals(True,
                      testlog_utils.IsInRange(30, min_val=None, max_val=30))
    self.assertEquals(False,
                      testlog_utils.IsInRange(30, min_val=None, max_val=29.99))
    self.assertEquals(True,
                      testlog_utils.IsInRange(30, min_val=30, max_val=None))
    self.assertEquals(False,
                      testlog_utils.IsInRange(30, min_val=30.01, max_val=None))
    self.assertEquals(True,
                      testlog_utils.IsInRange(30, min_val=None, max_val=None))
    self.assertEquals(True,
                      testlog_utils.IsInRange(30, min_val=29, max_val=31))
    self.assertEquals(False,
                      testlog_utils.IsInRange(31.1, min_val=29, max_val=31))

  def testJSONTime(self):
    """Tests conversion to and from JSON date format.

    Microseconds should be stripped to precision of 3 decimal points."""
    # pylint: disable=W0212
    output = testlog_utils.FromJSONDateTime(
        testlog_utils.ToJSONDateTime(SAMPLE_DATETIME))
    self.assertEquals(output, SAMPLE_DATETIME_ROUNDED_MIL)

    # TODO(itspeteR): Consider remove the test below.
    output = testlog_utils.FromJSONDateTime(
        testlog_utils.ToJSONDateTime(SAMPLE_DATETIME_ROUNDED_SEC))

  def testJSONHandlerDateTime(self):
    obj = SAMPLE_DATETIME
    # pylint: disable=W0212
    output = testlog_utils.JSONHandler(obj)
    self.assertEquals(output, SAMPLE_DATETIME_STRING)
    self.assertEquals(output, testlog_utils.ToJSONDateTime(obj))

  def testJSONHandlerDate(self):
    obj = datetime.date(1989, 8, 8)
    # pylint: disable=W0212
    output = testlog_utils.JSONHandler(obj)
    self.assertEquals(output, '1989-08-08')

  def testJSONHandlerTime(self):
    obj = datetime.time(22, 10, 10)
    # pylint: disable=W0212
    output = testlog_utils.JSONHandler(obj)
    self.assertEquals(output, '22:10')

  def testJSONHandlerExceptionAndTraceback(self):
    try:
      1 / 0
    except Exception:
      _, ex, tb = sys.exc_info()
      # pylint: disable=W0212
      output = testlog_utils.JSONHandler(tb)
      self.assertTrue('1 / 0' in output)
      output = testlog_utils.JSONHandler(ex)
      self.assertTrue(output.startswith('Exception: '))


if __name__ == '__main__':
  logging.basicConfig(
      format=('[%(levelname)s] '
              ' %(threadName)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=logging.INFO,
      datefmt='%Y-%m-%d %H:%M:%S')
  unittest.main()
