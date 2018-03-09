# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import sysfs
from cros.factory.probe.lib import probe_function


class TouchscreenElanFunction(probe_function.ProbeFunction):
  """Probe the ELAN touchscreen information."""

  I2C_DEVICES_PATH = '/sys/bus/i2c/devices'
  DRIVER_NAME = 'elants_i2c'

  def Probe(self):
    results = []
    for device_path in glob.glob(os.path.join(self.I2C_DEVICES_PATH, '*')):
      driver_link = os.path.join(device_path, 'driver')
      if not os.path.islink(driver_link):
        continue

      driver_name = os.path.basename(os.readlink(driver_link))
      if driver_name != self.DRIVER_NAME:
        continue

      result = sysfs.ReadSysfs(
          device_path, ['name', 'hw_version', 'fw_version'])
      if result:
        results.append(result)

    return results
