# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''A factory test to stress CPU.

It stresses CPU by generating random number using /dev/urandom for a specified
period of time.

Test parameter:
  duration_secs: Number of seconds to stress CPU.
'''

import logging
import time
import unittest

class UrandomTest(unittest.TestCase):
  def runTest(self):
    duration_secs = self.test_info.args['duration_secs']
    logging.info('Getting /dev/urandom for %d seconds', duration_secs)

    with open('/dev/urandom') as f:
      end_time = time.time() + duration_secs
      while time.time() <= end_time:
        data = f.read(1024*1024)
        self.assertTrue(data, '/dev/urandom returns nothing!')
