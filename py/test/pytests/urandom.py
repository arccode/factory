# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to stress CPU, by generating pseudo random numbers.

Description
-----------
It stresses CPU by generating random number using /dev/urandom for a specified
period of time (specified by ``duration_secs``).

Test Procedure
--------------
This is an automated test without user interaction.

Start the test and it will run for the time specified in argument
``duration_secs``, and pass if no errors found; otherwise fail with error
messages and logs.

Dependency
----------
No dependencies.  This test does not support remote DUT.

Examples
--------
To generate random number and stress CPU for 4 hours, add this in test list::

  {
    "pytest_name": "urandom",
    "args": {
      "duration_secs": 14400
    }
  }
"""

import logging
import time
import unittest

from cros.factory.utils import arg_utils


class UrandomTest(unittest.TestCase):
  ARGS = [
      arg_utils.Arg('duration_secs', int, help='How long this test will take?'),
  ]

  def runTest(self):
    duration_secs = self.args.duration_secs
    logging.info('Getting /dev/urandom for %d seconds', duration_secs)

    with open('/dev/urandom', 'rb') as f:
      end_time = time.time() + duration_secs
      while time.time() <= end_time:
        data = f.read(1024 * 1024)
        self.assertTrue(data, '/dev/urandom returns nothing!')
