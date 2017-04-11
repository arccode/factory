#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test for temperature sensors control.

The test uses cros.factory.device.thermal to probe temperature sensors.
"""

import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.utils.arg_utils import Arg


class BoardTempSensorsTest(unittest.TestCase):
  """Tests communication with temperature sensors."""
  ARGS = [
      Arg('temp_sensor_to_test', (str, list),
          'List of temperature sensor(s) to test, "*" for all sensors. '
          'Default to test only the main sensor (usually CPU).',
          default=None, optional=True),
      Arg('temp_range', tuple, 'A tuple of (min_temp, max_temp) in Celsius.',
          default=(0, 100)),
  ]

  def GetTemperature(self, name):
    """Gets temperature from a reference (name or index).

    Args:
      name: An integer for index of sensor or string for sensor name to read.

    Returns:
      Temperature of given sensor.
    """
    # TODO(hungte) Deprecate the legacy index API.
    if isinstance(name, int):
      name = self.thermal.GetTemperatureSensorNames()[name]
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
      values = dict((name, self.GetTemperature(name)) for name in sensors)

    logging.info('Got temperatures: %r', values)
    min_temp, max_temp = self.args.temp_range
    for name, temperature in values.iteritems():
      self.assertTrue(
          min_temp <= temperature <= max_temp,
          'Abnormal temperature reading on sensor %s: %s' % (name, temperature))
