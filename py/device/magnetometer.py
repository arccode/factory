#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.device import component
from cros.factory.device import sensor_utils


class Magnetometer(component.DeviceComponent):
  """Base class for magnetometer component module."""

  def __init__(self, board):
    super(Magnetometer, self).__init__(board)

  def GetController(self, location='base'):
    """Gets a controller with specified arguments.

    See sensor_utils.BasicSensorController for more information.
    """
    return sensor_utils.BasicSensorController(
        self._dut,
        'cros-ec-mag',
        location,
        ['in_magn_x', 'in_magn_y', 'in_magn_z'])
