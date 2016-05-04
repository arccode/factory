#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import datetime
import logging
import sys
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import testlog


SAMPLE_DATETIME = datetime.datetime(1989, 8, 8, 8, 8, 8, 888888)
SAMPLE_DATETIME_ROUNDED = datetime.datetime(1989, 8, 8, 8, 8, 8, 888000)
SAMPLE_DATETIME_STRING = '1989-08-08T08:08:08.888Z'


class TestlogTest(unittest.TestCase):

  def testJSONTime(self):
    """Test conversion to and from JSON date format.

    Microseconds should be stripped to precision of 3 decimal points."""
    # pylint: disable=W0212
    output = testlog._FromJSONDateTime(
        testlog._ToJSONDateTime(SAMPLE_DATETIME))
    self.assertEquals(output, SAMPLE_DATETIME_ROUNDED)

  def testJSONHandlerDateTime(self):
    obj = SAMPLE_DATETIME
    # pylint: disable=W0212
    output = testlog._JSONHandler(obj)
    self.assertEquals(output, SAMPLE_DATETIME_STRING)
    self.assertEquals(output, testlog._ToJSONDateTime(obj))

  def testJSONHandlerDate(self):
    obj = datetime.date(1989, 8, 8)
    # pylint: disable=W0212
    output = testlog._JSONHandler(obj)
    self.assertEquals(output, '1989-08-08')

  def testJSONHandlerTime(self):
    obj = datetime.time(22, 10, 10)
    # pylint: disable=W0212
    output = testlog._JSONHandler(obj)
    self.assertEquals(output, '22:10')

  def testJSONHandlerExceptionAndTraceback(self):
    try:
      1 / 0
    except Exception:
      _, ex, tb = sys.exc_info()
      # pylint: disable=W0212
      output = testlog._JSONHandler(tb)
      self.assertTrue('1 / 0' in output)
      output = testlog._JSONHandler(ex)
      self.assertTrue(output.startswith('Exception: '))

  def testEventSerializeUnserialize(self):
    original = testlog.StationInit()
    output = testlog.Event.FromJSON(original.ToJSON())
    self.assertEquals(output, original)

  def testNewEventTime(self):
    event = testlog.StationInit({'time': SAMPLE_DATETIME})
    self.assertEquals(event['time'], SAMPLE_DATETIME_ROUNDED)
    event = testlog.StationInit({'time': SAMPLE_DATETIME_ROUNDED})
    self.assertEquals(event['time'], SAMPLE_DATETIME_ROUNDED)
    event = testlog.StationInit({'time': SAMPLE_DATETIME_STRING})
    self.assertEquals(event['time'], SAMPLE_DATETIME_ROUNDED)
    with self.assertRaises(testlog.TestlogError):
      event = testlog.StationInit({'time': None})

  def testPopulateReturnsSelf(self):
    event = testlog.StationInit()
    self.assertEquals(event.Populate({}), event)

  def testDisallowRecursiveLogging(self):
    """Check that calling 'logging' within log processing code is dropped."""
    logged_events = []
    def CheckMessage(event):
      logged_events.append(event)
      logging.info('testing 456')
    testlog.CapturePythonLogging(CheckMessage)
    logging.info('testing 123')
    self.assertEquals(len(logged_events), 1)
    self.assertEquals(logged_events[0]['message'], 'testing 123')

  def testInvalidStatusTestRun(self):
    with self.assertRaises(testlog.TestlogError):
      testlog.StationTestRun({'status': True})


if __name__ == '__main__':
  unittest.main()
