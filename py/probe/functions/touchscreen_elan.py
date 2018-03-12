# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import sysfs
from cros.factory.probe.lib import cached_probe_function


class TouchscreenElanFunction(
    cached_probe_function.GlobPathCachedProbeFunction):
  """Probe the ELAN touchscreen information."""

  GLOB_PATH = '/sys/bus/i2c/devices/*'
  DRIVER_NAME = 'elants_i2c'

  @classmethod
  def ProbeDevice(cls, dir_path):
    driver_link = os.path.join(dir_path, 'driver')
    if (not os.path.islink(driver_link) or
        os.path.basename(os.readlink(driver_link)) != cls.DRIVER_NAME):
      return None

    return sysfs.ReadSysfs(dir_path, ['name', 'hw_version', 'fw_version'])
