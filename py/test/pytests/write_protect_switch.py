#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''Verifies that the write-protect switch is on.'''

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn

class WriteProtectSwitchTest(unittest.TestCase):
  ARGS = []
  def runTest(self):
    self.assertEqual(
        '1',
        Spawn(
            ['crossystem', 'wpsw_cur'],
            log=True, check_output=True, log_stderr_on_error=True).stdout_data)
