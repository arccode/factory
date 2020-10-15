#!/usr/bin/env python3
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Time-related utilities."""

import datetime
import unittest

from dateutil import tz

from cros.factory.utils import time_utils


class TimeUtilsTest(unittest.TestCase):

  def testFormatElapsedTime(self):
    self.assertEqual('00:00:00', time_utils.FormatElapsedTime(0))
    self.assertEqual('-00:00:01', time_utils.FormatElapsedTime(-1))
    self.assertEqual(
        '01:02:03', time_utils.FormatElapsedTime(1 * 3600 + 2 * 60 + 3))
    self.assertEqual(
        '101:02:03', time_utils.FormatElapsedTime(101 * 3600 + 2 * 60 + 3))

  def testTimeString(self):
    dt = datetime.datetime(2014, 11, 5, 3, 47, 52, 443865)
    stamp = 1415159272.443865
    self.assertEqual('2014-11-05T03:47:52.443Z', time_utils.TimeString(dt))
    self.assertEqual('2014-11-05T03:47:52.443Z', time_utils.TimeString(stamp))
    self.assertEqual(
        '2014-11-05T03-47-52.443Z', time_utils.TimeString(stamp, '-'))
    self.assertEqual(
        '2014-11-05T03|47|52Z', time_utils.TimeString(dt, '|', False))

  def testDatetimeToUnixtime(self):
    STD_TIME = 1514862245.678901
    STD_DT = datetime.datetime.utcfromtimestamp(STD_TIME)
    DST_TIME = 1533179045.678901
    DST_DT = datetime.datetime.utcfromtimestamp(DST_TIME)

    self.assertAlmostEqual(STD_TIME, time_utils.DatetimeToUnixtime(STD_DT))
    dt_utc = STD_DT.replace(tzinfo=tz.gettz('UTC'))
    self.assertAlmostEqual(STD_TIME, time_utils.DatetimeToUnixtime(dt_utc))
    # UTC -5
    dt_ny_std = STD_DT.replace(tzinfo=tz.gettz('America/New_York'))
    self.assertAlmostEqual(STD_TIME + 5 * 60 * 60,
                           time_utils.DatetimeToUnixtime(dt_ny_std))
    # UTC -4 (DST)
    dt_ny_dst = DST_DT.replace(tzinfo=tz.gettz('America/New_York'))
    self.assertAlmostEqual(DST_TIME + 4 * 60 * 60,
                           time_utils.DatetimeToUnixtime(dt_ny_dst))
    # UTC +8
    dt_tpe = STD_DT.replace(tzinfo=tz.gettz('Asia/Taipei'))
    self.assertAlmostEqual(STD_TIME - 8 * 60 * 60,
                           time_utils.DatetimeToUnixtime(dt_tpe))


if __name__ == '__main__':
  unittest.main()
