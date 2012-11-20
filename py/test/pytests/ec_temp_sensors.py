#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test for EC temperature sensors control.

The test uses factory.system.EC to probe temperature sensors.
Ported from third_party/autotest/files/client/site_tests/hardware_EC.

dargs:
  num_temp_sensor: Number of temperature sensor(s). Only used when
     temp_sensor_to_test is unset. Default: 0.
  temp_range: A tuple of (min_temp, max_temp) in Celsius. Default (0, 100).
  temp_sensor_to_test: List of temperature sensor(s) to test. Default None.
"""

import logging
import unittest

from cros.factory import system
from cros.factory.test.args import Arg

class ECTempSensorsTest(unittest.TestCase):
  """Tests EC communication with temperature sensors."""
  ARGS = [
    Arg('num_temp_sensor', int, 'Number of temperature sensor(s).', default=0),
    Arg('temp_sensor_to_test', list,
        'List of temperature sensor(s) to test. '
        'If None, it tests all sensors in [0, ..., num_temp_sensor - 1].',
        default=None, optional=True),
    Arg('temp_range', tuple, 'A tuple of (min_temp, max_temp) in Celsius.',
        default=(0, 100)),
  ]

  def setUp(self):
    self._ec = system.GetEC()
    self._ec.Hello()

  def runTest(self):
    temp_sensor_to_test = self.args.temp_sensor_to_test
    if temp_sensor_to_test is None:
      temp_sensor_to_test = xrange(self.args.num_temp_sensor)

    self.assertTrue(
      len(temp_sensor_to_test) > 0,
      'Either num_temp_sensor or temp_sensor_to_test must be set.')

    all_sensors_temp = self._ec.GetTemperatures()
    logging.info('Get temperature sensors from EC: %s', str(all_sensors_temp))
    num_sensors = len(all_sensors_temp)
    for index in temp_sensor_to_test:
      self.assertTrue(0 <= index < num_sensors,
                      'Cannot get temperature sensor %d.' % index)
      temperature = all_sensors_temp[index]
      self.assertFalse(temperature is None,
                       'Cannot get temperature reading from sensor %d.' % index)
      self.assertTrue(
        self.args.temp_range[0] <= temperature <= self.args.temp_range[1],
        'Abnormal temperature reading on sensor %d: %d' % (index, temperature))
