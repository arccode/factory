# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""An no-op test.

This test does nothing but sleeps for a given period of time.
"""

import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils.arg_utils import Arg


class NopTest(unittest.TestCase):
  ARGS = [
      Arg('wait_secs', (int, float), 'Wait for N seconds.', default=0)]

  def runTest(self):
    if self.args.wait_secs:
      time.sleep(self.args.wait_secs)
