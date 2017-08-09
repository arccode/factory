# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.device import types
from cros.factory.device import sensor_utils


class Gyroscope(types.DeviceComponent):
  """Gyroscope component module."""

  def GetController(self, location='base'):
    """Gets a controller with specified arguments.

    See sensor_utils.BasicSensorController for more information.
    """
    return sensor_utils.BasicSensorController(
        self._device,
        'cros-ec-gyro',
        location,
        ['in_anglvel_x', 'in_anglvel_y', 'in_anglvel_z'])
