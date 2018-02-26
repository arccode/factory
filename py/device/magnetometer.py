# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.device import sensor_utils
from cros.factory.device import types


class Magnetometer(types.DeviceComponent):
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
