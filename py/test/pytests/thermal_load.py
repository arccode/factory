# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This is a factory test to test thermal response under load.
Tests that under given load:
  - Temperatures don't go over temperature_limit before heat up.
  - Temperatures go over lower_threshold within heat_up_timeout_secs.
  - Temperatures don't go over temperature_limit throughout the entire test.

dargs:
  load: Number of threads stressapptest uses to stress the system. Default
      value is the number of processors.
  heat_up_timeout_secs: Timeout interval in seconds for temperature to go over
      lower_threshold.
  duration_secs: Time in seconds for the test to run.
  lower_threshold: Minimum temperature value required within
      heat_up_timeout_secs.
  temperature_limit: Maximum temperature value allowed throughout the entire
      test.
  sensor_index: The index of temperature sensor to use.
  temperatures_difference: The difference of temperatures should be under a
      specified limit.
"""

import logging
import multiprocessing
import time
import unittest

import factory_common # pylint: disable=W0611
from cros.factory.system import SystemStatus
from cros.factory.event_log import Log
from cros.factory.test.args import Arg
from cros.factory.test.utils import LoadManager

class ThermalLoadTest(unittest.TestCase):
  ARGS = [
      Arg('load', int, 'Number of threads stressapptest uses',
          optional=True, default=None),
      Arg('heat_up_timeout_secs', int, 'Timeout interval in seconds for '
          'tepmerature to go over lower_threshold', optional=True, default=40),
      Arg('duration_secs', int, 'Time in seconds for the test to run',
          optional=True, default=80),
      Arg('lower_threshold', (int, list), 'Minimum temperature value required '
          'within heat_up_timeout_secs', optional=True, default=45),
      Arg('temperature_limit', (int, list), 'Maximum temperature value allowed',
          optional=True, default=75),
      Arg('sensor_index', (int, list), 'The index of temperature sensor to use',
          optional=True, default=0),
      Arg('temperatures_difference', int, 'The difference of temperatures '
          'should be under a specified limit.', optional=True),
      ]

  def GetTemperatures(self):
    """Gets the temperature reading from specified sensor."""
    temperatures = []
    for sensor_index in self.args.sensor_index:
      temperatures.append(SystemStatus().temperatures[sensor_index])
    return temperatures

  def CheckTemperatures(self, temperatures, elapsed):
    """Check criterion for all specified temperatures.
    1. Make sure tempertures are under limit.
    2. Make sure the differences of all temperatures are in the range.

    Args:
      temperatures: A list of temperstures in different sensors.
      elapsed: elapsed time since heat up.
    """
    for index in xrange(len(temperatures)):
      temperature_value = temperatures[index]
      self.max_temperature[index] = max(
          self.max_temperature[index], temperature_value)

      if not self.heated_up[index] and (
          temperature_value >= self.args.lower_threshold[index]):
        self.heated_up[index] = True
        Log('heated', temperature_value=temperature_value,
            lower_threshold=self.args.lower_threshold[index],
            sensor_index=self.args.sensor_index[index],
            elapsed_sec=elapsed)
        logging.info("Sensor %d heated up to %d C in %d seconds.",
                     self.args.sensor_index[index],
                     self.args.lower_threshold[index], elapsed)

      if temperature_value > self.args.temperature_limit[index]:
        Log('over_heated', temperature_value=temperature_value,
            temperature_limit=self.args.temperature_limit[index],
            sensor_index=self.args.sensor_index[index],
            elapsed_sec=elapsed)
        self.fail("Sensor %d temperature got over %d." % (
            self.args.sensor_index[index], self.args.temperature_limit[index]))

      if elapsed >= self.args.heat_up_timeout_secs and (
          not self.heated_up[index]):
        Log('slow_temp_slope', temperature_value=temperature_value,
            lower_threshold=self.args.lower_threshold[index],
            sensor_index=self.args.sensor_index[index],
            timeout=self.args.heat_up_timeout_secs)
        logging.info("temperature track: %r", self.temperatures_track)
        self.fail("Temperature %d didn't go over %d in %s seconds." % (
            self.args.sensor_index[index],
            self.args.lower_threshold[index],
            self.args.heat_up_timeout_secs))

    if self.args.temperatures_difference:
      difference = max(temperatures) - min(temperatures)
      if difference > self.args.temperatures_difference:
        logging.info("temperature track: %r", self.temperatures_track)
        self.fail("The difference of temperatures %d exceeds the limit %d." % (
            difference, self.args.temperatures_difference))

  def setUp(self):
    self.load = self.args.load or multiprocessing.cpu_count()

    self.assertTrue(self.args.heat_up_timeout_secs <= self.args.duration_secs,
                    'heat_up_timeout_secs must not be greater than '
                    'duration_secs.')

    if type(self.args.sensor_index) is int:
      self.args.sensor_index = [self.args.sensor_index]
    if type(self.args.lower_threshold) is int:
      self.args.lower_threshold = [self.args.lower_threshold]
    if type(self.args.temperature_limit) is int:
      self.args.temperature_limit = [self.args.temperature_limit]

    self.assertTrue(
        len(self.args.sensor_index) == len(self.args.lower_threshold) and (
        len(self.args.sensor_index) == len(self.args.temperature_limit)),
        'The number of sensor_index, lower_threshold, and temperature_limit '
        'should be the same.')

    self.heated_up = [False] * len(self.args.sensor_index)
    self.max_temperature = [0] * len(self.args.sensor_index)
    self.temperatures_track = []

  def runTest(self):
    start_temperatures = self.GetTemperatures()
    Log('start_temperatures', tempertures=start_temperatures)
    logging.info("Starting temperatures are: %s", start_temperatures)

    # Check temperatures before heat up to make sure all sensors are normal.
    self.CheckTemperatures(start_temperatures, 0)
    logging.info("Stressing with %d threads...", self.load)

    with LoadManager(duration_secs=self.args.duration_secs,
                     num_threads=self.load):
      for elapsed in xrange(1, self.args.duration_secs + 1):
        time.sleep(1)
        temperatures = self.GetTemperatures()
        self.temperatures_track.append(temperatures)
        self.CheckTemperatures(temperatures, elapsed)

      logging.info("Passed. Maximum temperature seen is %s",
          self.max_temperature)
      Log('passed', max_temperature=self.max_temperature)
