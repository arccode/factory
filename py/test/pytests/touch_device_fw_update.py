# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Update touch device firmware.

This test checks and updates touch device firmware.
"""


import glob
import os
import unittest

from cros.factory.utils.process_utils import Spawn
from cros.factory.test.args import Arg

UPDATER = '/opt/google/touch/firmware/chromeos-touch-firmwareupdate.sh'

class UpdateTouchDeviceFWTest(unittest.TestCase):
  ARGS = [
    Arg('device_name', str, 'Name of the touch device as in'
        '/sys/bus/i2c/devices/*/name)'),
    Arg('fw_name', str, 'Expected firmware file name (in /lib/firmware)'),
    Arg('fw_version', str, 'Expected firmware version'),
  ]

  def runTest(self):
    # Find the appropriate device sysfs file.
    devices = [x for x in glob.glob('/sys/bus/i2c/devices/*/name')
               if open(x).read().strip() == self.args.device_name]
    self.assertEqual(
        1, len(devices),
        'Expected to find one device but found %s' % devices)
    device_path = os.path.dirname(devices[0])

    expected_ver = getattr(self.args, 'fw_version')
    actual_ver = open(os.path.join(device_path, 'fw_version')).read().strip()
    if expected_ver != actual_ver:
      # touch firmware updater fails sometimes, retry 5 times
      for _ in range(5):
        device_name = getattr(self.args, 'device_name')
        fw_name = getattr(self.args, 'fw_name')
        # updater needs a shell, parameters should be concated into
        # command string before spawn
        updater_cmd = "%s -f -d %s -n %s" % (UPDATER, device_name,
                      fw_name)
        updater = Spawn(updater_cmd, log=True, read_stdout=True, shell=True)
        updater.wait()
        if updater.returncode == 0:
          return
      raise ValueError('Touch device firmware update failed')
