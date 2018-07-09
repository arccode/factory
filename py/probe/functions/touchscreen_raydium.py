# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import sysfs
from cros.factory.probe.lib import cached_probe_function


class TouchscreenRaydiumFunction(
    cached_probe_function.GlobPathCachedProbeFunction):
  """Probe the Raydium touchscreen information.

  Description
  -----------
  The driver of Raydium touchscreens doesn't export the attributes for identifying
  devices to the regular linux input device interface so this function probes
  all Raydium touchscreens and output the attributes of the device.  The output
  of each Raydium touchscreen must have 3 fields:

  - ``device_path``: Pathname of the sysfs directory.
  - ``name``: Name of the device exported by the driver.
  - ``hw_version``: Hardware version exported by the driver.
  - ``fw_version``: Firmware version exported by the driver.

  Examples
  --------
  Let's say if we want to verify whether the specific Raydium touchscreen (
  hardware/firmware versions are ``0x1234``/``0x5678``) exists on the device
  or not, we can have the probe statement::

    {
      "eval": "touchscreen_raydium",
      "expect": {
        "hw_version": "1234",
        "fw_version": "5678"
      }
    }

  If the touchscreen is probed, the probed results will be::

    [
      {
        "name": "RAYD_1234_5678",
        "hw_version": "1234",
        "fw_version": "5678"
      }
    ]

  If the touchscreen is not found, the probed results will be an empty list.
  """

  GLOB_PATH = '/sys/bus/i2c/devices/*'
  DRIVER_NAME = 'raydium_ts'

  @classmethod
  def ProbeDevice(cls, dir_path):
    driver_link = os.path.join(dir_path, 'driver')
    if (not os.path.islink(driver_link) or
        os.path.basename(os.readlink(driver_link)) != cls.DRIVER_NAME):
      return None

    return sysfs.ReadSysfs(dir_path, ['name', 'hw_version', 'fw_version'])
