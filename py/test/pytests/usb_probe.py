# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A hardware test for probing USB devices.

It uses lsusb utility to check if there's an USB device with given ID.

dargs:
  vid: (str) 4-digit vendor ID.
  pid: (str) 4-digit product ID.
"""

import unittest

from cros.factory.test.args import Arg
from cros.factory.utils.process_utils import SpawnOutput


class USBProbeTest(unittest.TestCase):
  ARGS = [
    Arg('vid', str, '4-digit vendor ID'),
    Arg('pid', str, '4-digit product ID'),
  ]

  def ProbeUSB(self, vid, pid):
    response = SpawnOutput(['lsusb'], log=True)
    return ('%s:%s' % (vid, pid)) in response

  def runTest(self):
    self.assertTrue(self.ProbeUSB(self.args.vid, self.args.pid),
                    'No specified USB device found.')
