#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Ensures that factory documentation can be built properly."""


import os
import pprint
import re
import sys
import unittest

import factory_common # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.utils.process_utils import Spawn


# Files allowed to have errors now.  TODO: Clean these up.
BLACKLIST = [
  'ac_power.rst',
  'audio_loop.rst',
  'bft_fixture.rst',
  'camera_fixture.rst',
  'charger.rst',
  'check_wifi_calibration.rst',
  'ec_temp_sensors.rst',
  'ectool_i2c_dev_id.rst',
  'ext_display.rst',
  'fan_speed.rst',
  'hwmon_probe.rst',
  'i2c_probe.rst',
  'index.rst',
  'keyboard.rst',
  'led.rst',
  'lid_switch.rst',
  'light_sensor.rst',
  'line_check_item.rst',
  'read_device_data_from_vpd.rst',
  'removable_storage.rst',
  'scan.rst',
  'select_components.rst',
  'thermal_load.rst',
  'touch_device_fw_update.rst',
  'touchscreen_uniformity.rst',
  'touchscreen_wrap.rst',
  'verify_touch_device_fw.rst',
  ]


"""Tests the overall documentation generation process."""


class DocTest(unittest.TestCase):
  def testMakeDoc(self):
    stderr_lines = Spawn(
      ['make', 'doc'], cwd=factory.FACTORY_PATH,
      check_output=True, read_stderr=True,
      log=True, log_stderr_on_error=True).stderr_lines()

    files_with_errors = set()

    for l in stderr_lines:
      match = re.match('^([^:]+):(\d+): (ERROR|WARNING): (.+)',
                       l.strip())

      if match:
        basename = os.path.basename(match.group(1))
        blacklisted = basename in BLACKLIST
        sys.stderr.write("%s%s\n" % (
          l.strip(), ' (blacklisted)' if blacklisted else ''))
        files_with_errors.add(basename)

    if files_with_errors:
      # pprint for easy copy/paste to blacklist
      sys.stderr.write('Files with errors:\n')
      pprint.pprint(sorted(files_with_errors))

    failed_files = files_with_errors - set(BLACKLIST)
    if failed_files:
      self.fail('Found errors in non-blacklisted files %s; '
                'see stderr for details' % sorted(failed_files))


if __name__ == '__main__':
  unittest.main()
