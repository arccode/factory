#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Time-related utilities."""


import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils.time_utils import FormatElapsedTime


class TimeUtilsTest(unittest.TestCase):
  def testFormatElapsedTime(self):
    self.assertEquals('00:00:00', FormatElapsedTime(0))
    self.assertEquals('01:02:03', FormatElapsedTime(1*3600 + 2*60 + 3))
    self.assertEquals('101:02:03', FormatElapsedTime(101*3600 + 2*60 + 3))
    self.assertEquals('-00:00:01', FormatElapsedTime(-1))


if __name__ == '__main__':
  unittest.main()
