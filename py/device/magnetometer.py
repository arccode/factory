# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.device import device_types
from cros.factory.device import sensor_utils


class Magnetometer(device_types.DeviceComponent):
  """Base class for magnetometer component module."""

  def GetController(self, location='base'):
    """Gets a controller with specified arguments.

    See sensor_utils.BasicSensorController for more information.
    """
    return sensor_utils.BasicSensorController(
        self._device,
        'cros-ec-mag',
        location,
        ['in_magn_x', 'in_magn_y', 'in_magn_z'])
