#!/usr/bin/env python3
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import calendar
import logging
import os
import tempfile
import time
import unittest

import mock

from cros.factory.tools import time_sanitizer
from cros.factory.utils import file_utils


BASE_TIME = float(
    calendar.timegm(time.strptime('Sat Jun  9 00:00:00 2012')))

SECONDS_PER_DAY = 86400


# pylint: disable=protected-access
class TimeSanitizerTestBase(unittest.TestCase):

  def setUp(self):
    self.fake_time = mock.Mock(time_sanitizer.Time)

    self.sanitizer = time_sanitizer.TimeSanitizer(
        self.state_file,
        monitor_interval_secs=30,
        time_bump_secs=60,
        max_leap_secs=SECONDS_PER_DAY)
    self.sanitizer._time = self.fake_time
    self.sanitizer._suppress_exceptions = False

  def run(self, result=None):
    with file_utils.TempDirectory(
        prefix='time_sanitizer_unittest.') as temp_dir:
      # pylint: disable=attribute-defined-outside-init
      self.state_file = os.path.join(temp_dir, 'state_file')
      super(TimeSanitizerTestBase, self).run(result)

  def _ReadStateFile(self):
    return float(open(self.state_file).read().strip())


class TimeSanitizerBaseTimeTest(TimeSanitizerTestBase):

  def runTest(self):
    # pylint: disable=protected-access
    # (access to protected members)
    with tempfile.NamedTemporaryFile() as f:
      self.assertEqual(
          os.stat(f.name).st_mtime,
          time_sanitizer.GetBaseTimeFromFile([f.name]))
    self.assertEqual(
        None, time_sanitizer.GetBaseTimeFromFile(['/some-nonexistent-file']))


class TimeSanitizerTest(TimeSanitizerTestBase):

  def runTest(self):
    self.fake_time.Time.return_value = BASE_TIME

    self.sanitizer.RunOnce()
    self.assertEqual(BASE_TIME, self._ReadStateFile())
    self.fake_time.Time.assert_called_once_with()
    self.fake_time.Time.reset_mock()

    # Now move forward 1 second, and then forward 0 seconds.  Should
    # be fine.
    for unused_iteration in range(2):
      self.fake_time.Time.return_value = BASE_TIME + 1

      self.sanitizer.RunOnce()
      self.assertEqual(BASE_TIME + 1, self._ReadStateFile())
      self.fake_time.Time.assert_called_once_with()
      self.fake_time.Time.reset_mock()

    # Now move forward 2 days.  This should be considered hosed, so
    # the time should be bumped up by time_bump_secs (120).
    self.fake_time.Time.return_value = BASE_TIME + 2 * SECONDS_PER_DAY

    self.sanitizer.RunOnce()
    self.assertEqual(BASE_TIME + 61, self._ReadStateFile())
    self.fake_time.Time.assert_called_once_with()
    self.fake_time.Time.reset_mock()
    self.fake_time.SetTime.assert_called_with(BASE_TIME + 61)

    # Move forward a bunch.  Fine.
    self.fake_time.Time.return_value = BASE_TIME + 201.5

    self.sanitizer.RunOnce()
    self.assertEqual(BASE_TIME + 201.5, self._ReadStateFile())
    self.fake_time.Time.assert_called_once_with()
    self.fake_time.Time.reset_mock()

    # Jump back 20 seconds.  Not fine!
    self.fake_time.Time.return_value = BASE_TIME + 181.5

    self.sanitizer.RunOnce()
    self.assertEqual(BASE_TIME + 261.5, self._ReadStateFile())
    self.fake_time.Time.assert_called_once_with()
    self.fake_time.SetTime.assert_called_with(BASE_TIME + 261.5)


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  unittest.main()
