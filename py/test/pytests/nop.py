# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""An no-op test.

It is used to wait for previous test before starting the following
backgroundable tests.
"""

import time
import unittest

from cros.factory.test.args import Arg

class NopTest(unittest.TestCase):
  ARGS = [
      Arg('wait_secs', (int, float), 'Wait for N seconds.', default=0)]

  def runTest(self):
    if self.args.wait_secs:
      time.sleep(self.args.wait_secs)
