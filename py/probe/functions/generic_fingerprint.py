# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

from cros.factory.probe.lib import cached_probe_function
from cros.factory.test.utils import fpmcu_utils
from cros.factory.utils import sys_interface


class FingerprintFunction(cached_probe_function.CachedProbeFunction):
  """Probe the fingerprint information."""

  def GetCategoryFromArgs(self):
    return None

  @classmethod
  def ProbeAllDevices(cls):
    if not os.path.exists('/dev/cros_fp'):
      return None

    _fpmcu = fpmcu_utils.FpmcuDevice(sys_interface.SystemInterface())

    sensor_vendor, sensor_model = _fpmcu.GetFpSensorInfo()
    fpmcu_name = _fpmcu.GetFpmcuName()
    # pylint: disable=unused-variable
    ro_fw_version, unused = _fpmcu.GetFpmcuFirmwareVersion()

    results = [{
        'sensor_vendor': sensor_vendor,
        'sensor_model': sensor_model,
        'fpmcu_name': fpmcu_name,
        'ro_fw_version': ro_fw_version
    }]
    return results
