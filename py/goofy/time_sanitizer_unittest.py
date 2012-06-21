#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import calendar
import mox
import os
import tempfile
import time
import unittest

from contextlib import contextmanager

import factory_common
from autotest_lib.client.cros.factory import time_sanitizer


BASE_TIME = float(
  calendar.timegm(time.strptime('Sat Jun  9 00:00:00 2012')))

SECONDS_PER_DAY = 86400

class TimeSanitizerTest(unittest.TestCase):
  def testBaseTimeFile(self):
    with tempfile.NamedTemporaryFile() as f:
      self.assertEquals(os.stat(f.name).st_mtime,
                        time_sanitizer._GetBaseTime(f.name))
    self.assertEquals(None,
                      time_sanitizer._GetBaseTime('/some-nonexistent-file'))

  def setUp(self):
    self.mox = mox.Mox()
    self.fake_time = self.mox.CreateMock(time_sanitizer.Time)

    self.state_file = tempfile.NamedTemporaryFile().name
    self.sanitizer = time_sanitizer.TimeSanitizer(
      self.state_file,
      monitor_interval_secs=30,
      time_bump_secs=60,
      max_leap_secs=SECONDS_PER_DAY)
    self.sanitizer._time = self.fake_time

  def _ReadStateFile(self):
    return float(open(self.state_file).read().strip())

  def testSanitizer(self):
    # Context manager that sets up a mock, then runs the sanitizer once.
    @contextmanager
    def mock():
      self.mox.ResetAll()
      yield
      self.mox.ReplayAll()
      self.sanitizer.RunOnce()
      self.mox.VerifyAll()

    with mock():
      self.fake_time.Time().AndReturn(BASE_TIME)
    self.assertEquals(BASE_TIME, self._ReadStateFile())

    # Now move forward 1 second, and then forward 0 seconds.  Should
    # be fine.
    for _ in xrange(2):
      with mock():
        self.fake_time.Time().AndReturn(BASE_TIME + 1)
      self.assertEquals(BASE_TIME + 1, self._ReadStateFile())

    # Now move forward 2 days.  This should be considered hosed, so
    # the time should be bumped up by time_bump_secs (120).
    with mock():
      self.fake_time.Time().AndReturn(BASE_TIME + 2 * SECONDS_PER_DAY)
      self.fake_time.SetTime(BASE_TIME + 61)
    self.assertEquals(BASE_TIME + 61, self._ReadStateFile())

    # Move forward a bunch.  Fine.
    with mock():
      self.fake_time.Time().AndReturn(BASE_TIME + 201.5)
    self.assertEquals(BASE_TIME + 201.5, self._ReadStateFile())

    # Jump back 20 seconds.  Not fine!
    with mock():
      self.fake_time.Time().AndReturn(BASE_TIME + 181.5)
      self.fake_time.SetTime(BASE_TIME + 261.5)
    self.assertEquals(BASE_TIME + 261.5, self._ReadStateFile())

if __name__ == "__main__":
    unittest.main()


