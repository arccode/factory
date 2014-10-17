#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test for temperature sensors control.

The test uses factory.system.Board to probe temperature sensors.
Ported from third_party/autotest/files/client/site_tests/hardware_EC.
"""

import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory import system
from cros.factory.test.args import Arg

class BoardTempSensorsTest(unittest.TestCase):
  """Tests communication with temperature sensors."""
  ARGS = [
    Arg('num_temp_sensor', int,
        'Number of temperature sensor(s). '
        'Only used when temp_sensor_to_test is unset.',
        default=0),
    Arg('temp_sensor_to_test', list,
        'List of temperature sensor(s) to test. '
        'If None, it tests all sensors in [0, ..., num_temp_sensor - 1].',
        default=None, optional=True),
    Arg('temp_range', tuple, 'A tuple of (min_temp, max_temp) in Celsius.',
        default=(0, 100)),
  ]

  def setUp(self):
    self._board = system.GetBoard()

  def runTest(self):
    temp_sensor_to_test = self.args.temp_sensor_to_test
    if temp_sensor_to_test is None:
      temp_sensor_to_test = xrange(self.args.num_temp_sensor)

    self.assertTrue(
      len(temp_sensor_to_test) > 0,
      'Either num_temp_sensor or temp_sensor_to_test must be set.')

    all_sensors_temp = self._board.GetTemperatures()
    logging.info('Get temperature sensors: %s', str(all_sensors_temp))
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
