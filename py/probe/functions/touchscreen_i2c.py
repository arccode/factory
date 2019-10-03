# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

from cros.factory.probe.functions import sysfs
from cros.factory.probe.lib import cached_probe_function


class I2cTouchscreenFunction(
    cached_probe_function.GlobPathCachedProbeFunction):
  """Probe the generic I2C (i.e. not HID over I2C) touchscreen information.

  Description
  -----------
  The generic I2C driver doesn't export sufficient device attributes to
  '/proc/bus/input/devices'. This function probes the device attributes for
  the generic I2C touchscreens directly from sysfs instead. The output has
  6 fields:

  - ``device_path``: Pathname of the sysfs directory.
  - ``fw_version``: Firmware version exported by the driver.
  - ``hw_version``: Hardware version exported by the driver.
  - ``name``: Name of the device exported by the driver.
  - ``product``: The replica of hw_version.
  - ``vendor``: USB Vendor ID. TODO(chromium:1008159): Remove VID.

  Examples
  --------
  Let's say if we want to verify whether the specific ELAN touchscreen (
  hardware/firmware versions are ``0x1234``/``0x5678``) exists on the device
  or not, we can have the probe statement::

    {
      "eval": "touchscreen_i2c",
      "expect": {
        "hw_version": "1234",
        "fw_version": "5678"
      }
    }

  If the touchscreen is probed, the probed results will be::

    [
      {
        "name": "elan_1234_5678",
        "hw_version": "1234",
        "fw_version": "5678"
      }
    ]

  If the touchscreen is not found, the probed results will be an empty list.
  """

  GLOB_PATH = '/sys/bus/i2c/devices/*'

  # A list of (driver_name, vid) tuples for the touchscreens running
  # the generic I2C driver. TODO(chromium:1008159): Remove VID.
  I2C_TS_TUPLES = [('elants_i2c', '04f3'),   # Elan
                   ('raydium_ts', '27a3'),   # Raydium
                   ('atmel_mxt_ts', '03eb')] # Atmel

  @classmethod
  def ProbeDevice(cls, dir_path):
    driver_link = os.path.join(dir_path, 'driver')
    if not os.path.islink(driver_link):
      return None
    for ts_tuple in cls.I2C_TS_TUPLES:
      if os.path.basename(os.readlink(driver_link)) == ts_tuple[0]:
        data = sysfs.ReadSysfs(dir_path, ['name', 'hw_version', 'fw_version'])
        data['vendor'] = ts_tuple[1]  # Add USB VID
        data['product'] = data['hw_version']
        return data
    return None
