# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Sync the clock of DUT with the clock of station.

Description
-----------
This test set DUT clock to station clock time, and then check if the difference
between DUT clock time and station clock time exceeds a given threshold. If
exceeds, this test will fail.

Test Procedure
--------------
This is an automatic test that doesn't need any user interaction.

1. Firstly, this test will create a DUT link.
2. If the link is not a local link, DUT clock will be set to station clock time.
3. This test will check the difference between DUT clock time and station clock
   time, and fail if it exceeds the given tolerance. Otherwise, the test will
   pass.

Dependency
----------
- DUT link must be ready before running this test.

Examples
--------
To sync the clock of DUT with the clock of station with default tolerance, add
this in test list::

  {
    "pytest_name": "sync_time"
  }

To sync with tolerance time set to 3 seconds::

  {
    "pytest_name": "sync_time",
    "args": {
      "tolerance": 3.0
    }
  }
"""

import datetime
import unittest

from cros.factory.device import device_utils
from cros.factory.test import session
from cros.factory.test.utils import time_utils as test_time_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import time_utils


class SyncTime(unittest.TestCase):

  ARGS = [
      Arg('tolerance', float,
          'Max absolute time difference between DUT and station after sync.',
          default=5.0)]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    session.console.info('DUT time was: %s',
                         self.dut.CallOutput(['date', '-u'], log=True))

    test_time_utils.SyncDate(self.dut)

    dut_now = float(self.dut.CallOutput(['date', '-u', '+%s'], log=True))
    goofy_now = (datetime.datetime.utcnow() -
                 time_utils.EPOCH_ZERO).total_seconds()

    self.assertAlmostEqual(goofy_now, dut_now, delta=self.args.tolerance)
