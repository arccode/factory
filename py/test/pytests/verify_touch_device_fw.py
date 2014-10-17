# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Checks touch device firmware and config checksum.

This looks for a touch device configured with the given 'config_file'
name, and verifies that its fw_version and config_csum (read from
/sys) match the expected values.
"""


import glob
import os
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg


class VerifyTouchDeviceFWTest(unittest.TestCase):
  ARGS = [
    Arg('config_file', str,
        'Name of the touch config file (as in '
        '/sys/bus/i2c/devices/\\*/config_file)'),
    Arg('fw_version', str, 'Expected firmware version'),
    Arg('config_csum', str, 'Expected config checksum'),
  ]

  def runTest(self):
    # Find the appropriate config file.
    configs = [x for x in glob.glob('/sys/bus/i2c/devices/*/config_file')
               if open(x).read().strip() == self.args.config_file]
    self.assertEqual(
        1, len(configs),
        'Expected to find one config file but found %s' % configs)
    device_path = os.path.dirname(configs[0])

    for atom in ('fw_version', 'config_csum'):
      expected = getattr(self.args, atom)
      actual = open(os.path.join(device_path, atom)).read().strip()
      self.assertEquals(expected, actual,
                        'Mismatched %s (expected %r, found %r)' % (
                            atom, expected, actual))
