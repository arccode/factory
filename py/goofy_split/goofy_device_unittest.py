#!/usr/bin/python -u
#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The unittest for the device-side of the main factory test flow."""


import factory_common  # pylint: disable=W0611

import logging
import threading
import time
import unittest

from cros.factory.goofy_split.goofy_device import GoofyDevice
from cros.factory.test import factory

class GoofyDeviceTest(unittest.TestCase):
  """Base class for GoofyDevice test cases."""

  def setUp(self):
    self.goofy = GoofyDevice()

  def tearDown(self):
    self.goofy.destroy()

    # Make sure we're not leaving any extra threads hanging around
    # after a second.
    for _ in range(10):
      extra_threads = [t for t in threading.enumerate()
               if t != threading.current_thread()]
      if not extra_threads:
        break
      logging.info('Waiting for %d threads to die', len(extra_threads))

      # Wait another 100 ms
      time.sleep(.1)

    self.assertEqual([], extra_threads)


class BasicSanityTest(GoofyDeviceTest):
  """ Do nothing except invoke setup and teardown."""
  def runTest(self):
    self.assertIsNotNone(self.goofy)


if __name__ == "__main__":
  factory.init_logging('goofy_device_unittest')
  unittest.main()
