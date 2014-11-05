#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Time-related utilities."""


from __future__ import print_function
import unittest
import datetime

import factory_common  # pylint: disable=W0611
from cros.factory.utils.time_utils import FormatElapsedTime, TimeString


class TimeUtilsTest(unittest.TestCase):
  def testFormatElapsedTime(self):
    self.assertEquals('00:00:00', FormatElapsedTime(0))
    self.assertEquals('01:02:03', FormatElapsedTime(1*3600 + 2*60 + 3))
    self.assertEquals('101:02:03', FormatElapsedTime(101*3600 + 2*60 + 3))
    self.assertEquals('-00:00:01', FormatElapsedTime(-1))

  def testTimeString(self):
    dt = datetime.datetime(2014, 11, 5, 3, 47, 52, 443865)
    stamp = 1415159272.443865
    self.assertEquals('2014-11-05T03:47:52.443Z', TimeString(dt))
    self.assertEquals('2014-11-05T03:47:52.443Z', TimeString(stamp))
    self.assertEquals('2014-11-05T03-47-52.443Z', TimeString(stamp, '-'))
    self.assertEquals('2014-11-05T03|47|52Z', TimeString(dt, '|', False))


if __name__ == '__main__':
  unittest.main()
