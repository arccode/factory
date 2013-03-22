# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A hardware test for probing USB devices.

It uses the lsusb utility to check if there's an USB device with given VID:PID
or containing a specified string in lsusb.

If search_string is defined it searches for it in lsusb -v and passes if the
string exists, vid and pid are ignored in this case.

If vid and pid are defined it searches for them in lsusb -v and passes if they
exist.

dargs:
  vid: (str) optional 4-digit vendor ID.
  pid: (str) optional 4-digit product ID.
  search_string: (str) optional manual string to check for in lsusb -v
"""

import unittest

from cros.factory.event_log import Log
from cros.factory.test.args import Arg
from cros.factory.utils.process_utils import SpawnOutput


class USBProbeTest(unittest.TestCase):
  ARGS = [
    Arg('vid', str, '4-digit vendor ID', '', optional=True),
    Arg('pid', str, '4-digit product ID', '', optional=True),
    Arg('search_string', str, 'manual string to check for in lsusb -v', None,
        optional=True),
  ]

  def _ProbeUSB(self, lsusb_string):
    """Search for a string in lsusb -v.

    Args:
      lsusb_string: string to search for

    Returns:
      True if the string is found, false if not.
    """
    response = SpawnOutput(['lsusb', '-v'], log=True)
    return (lsusb_string) in response

  def runTest(self):
    if (self.args.search_string):
      usb_string = self.args.search_string
    else:
      usb_string = '%s:%s' % (self.args.vid, self.args.pid)
    probed_result = self._ProbeUSB(usb_string)
    Log('usb_probed', result=probed_result, usb_string=usb_string)
    self.assertTrue(probed_result,
                    'String: %s was not found in lsusb -v.' % usb_string)
