# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test for temperature sensors control.

Description
-----------
The test uses device API to check if temperature sensors is connected and the
temperature lies in the given range `temp_range`.

Test Procedure
--------------
This is an automated test without user interaction.

Dependency
----------
Device API `cros.factory.device.thermal`.

This is usually implemented in `/sys` with properties like `thermal_zone`
or command `ectool temps` / `ectool tempsinfo`.

Examples
--------
To check if the temperature sensors is connected and temperature is in default
range ([0, 100]), add this in test list::

  {
    "pytest_name": "thermal_sensors"
  }

To check if the temperature is in range [30, 80], add this in test list::

  {
    "pytest_name": "thermal_sensors",
    "args": {
      "temp_range": [30, 80]
    }
  }
"""

import logging
import unittest

from cros.factory.device import device_utils
from cros.factory.utils.arg_utils import Arg


class BoardTempSensorsTest(unittest.TestCase):
  """Tests communication with temperature sensors."""
  ARGS = [
      Arg('temp_sensor_to_test', (str, list),
          'List of temperature sensor(s) to test, "*" for all sensors. '
          'Default to test only the main sensor (usually CPU).',
          default=None),
      Arg('temp_range', list,
          '[min_temp, max_temp] in Celsius.', default=[0, 100]),
  ]

  def GetTemperature(self, name):
    """Gets temperature from a reference (name or index).

    Args:
      name: An integer for index of sensor or string for sensor name to read.

    Returns:
      Temperature of given sensor.
    """
    return self.thermal.GetTemperature(name)

  def setUp(self):
    self.thermal = device_utils.CreateDUTInterface().thermal

  def runTest(self):
    sensors = self.args.temp_sensor_to_test
    if sensors == '*':
      values = self.thermal.GetAllTemperatures()
    else:
      if sensors is None:
        sensors = [self.thermal.GetMainSensorName()]
      values = {name: self.GetTemperature(name) for name in sensors}

    logging.info('Got temperatures: %r', values)
    min_temp, max_temp = self.args.temp_range
    for name, temperature in values.items():
      self.assertTrue(
          min_temp <= temperature <= max_temp,
          'Abnormal temperature reading on sensor %s: %s' % (name, temperature))
