# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests the functionality of hwmon temp sensors.
"""

import glob
import logging
import os
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg


class HwmonProbeTest(unittest.TestCase):
  """Tests hwmon temp sensors by reading all their values and identifying that
  their indicated temperatures are in range as specified by min_temp_celsius and
  max_temp_celsius. Also, ensures that deviation of any hwmon temp sensor is
  less or equal to max_temp_delta_celsius from the mean temperature."""
  ARGS = [
    Arg('hwmon_count', int,
        'Number of hwmon temp sensors the system is supposed to have.'),
    Arg('delta_temp_max_celsius', int,
        'Max allowed delta between temp sensor and an average temp.',
        default=5),
    Arg('min_temp_celsius', int,
        'Min allowed temperature recorded by hwmon.', default=15),
    Arg('max_temp_celsius', int,
        'Max allowed temperature recorded by hwmon.', default=110),
  ]

  def _FindHwmons(self):
    """Finds all hwmon temp sensors, verifies how many sensors are expected, and
    returns a list of their paths."""
    hwmon_temp_sensor = glob.glob('/sys/class/hwmon/hwmon*/device/temp*_input')

    self.assertTrue(len(hwmon_temp_sensor) != 0, 'No hwmon devices found.')

    logging.info('Found hwmons:\n%s', '\n'.join(map(str, hwmon_temp_sensor)))

    self.assertEquals(self.args.hwmon_count, len(hwmon_temp_sensor),
                      'System has %d hwmon sensors instead of expected %d' %
                      (len(hwmon_temp_sensor), self.args.hwmon_count))

    return hwmon_temp_sensor

  def _ReadTemp(self, sensor):
    """Reads hwmon temperature, verifies it's within the expected range, and
    returns the value to the caller"""
    self.assertTrue(os.path.isfile(sensor) and os.access(sensor, os.R_OK),
                    'Unable to locate sensor %s' % sensor)
    try:
      with open(sensor, 'r') as f:
        t = int(f.readline().rstrip())/1000
    except Exception as e:
      raise IOError('Unable to open hwmon sensor %s : %s' % (sensor, e))

    self.assertTrue(t > self.args.min_temp_celsius and
                    t < self.args.max_temp_celsius,
                    'Temp %d out of allowed temp range' % t)
    return t

  def runTest(self):
    sensor_values = []

    hwmon_temp_sensor = self._FindHwmons()

    sensor_values = [self._ReadTemp(sensor) for sensor in hwmon_temp_sensor]

    average_sensor_value = sum(sensor_values)/len(sensor_values)

    for sensor_value in sensor_values:
      self.assertLessEqual(abs(sensor_value-average_sensor_value),
                           self.args.delta_temp_max_celsius,
                           'temp %d C is out of range. Average temp: %d C' %
                           (sensor_value, average_sensor_value))
