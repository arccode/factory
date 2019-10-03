# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Tests thermal response under load.

Tests that under given load:

- Temperatures don't go over temperature_limit before heat up.
- Temperatures go over lower_threshold within heat_up_timeout_secs.
- Temperatures don't go over temperature_limit throughout the entire test.
"""

import logging
import time
import unittest

from cros.factory.device import device_utils
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.utils import stress_manager
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg


class ThermalLoadTest(unittest.TestCase):
  ARGS = [
      Arg('load', int,
          ('Number of threads stressapptest uses.  If None is '
           'used, this will default to the number of processors in the '
           'system.'),
          default=None),
      Arg('heat_up_timeout_secs', int, 'Timeout interval in seconds for '
          'temperature to go over lower_threshold', default=40),
      Arg('duration_secs', int, 'Time in seconds for the test to run',
          default=80),
      Arg('lower_threshold', (int, list), 'Minimum temperature value required '
          'within heat_up_timeout_secs', default=45),
      Arg('temperature_limit', (int, list),
          'Maximum temperature value allowed throughout the entire test.',
          default=75),
      Arg('sensors', (str, list), 'List of temperature sensors to test. '
          'Default to main sensor, or "*" for all sensors.',
          default=None),
      Arg('temperatures_difference', int, 'The difference of temperatures '
          'should be under a specified limit.', default=None),
  ]

  def GetTemperatures(self):
    """Gets the temperature reading from specified sensors."""
    if len(self.sensors) == 1:
      return [self.dut.thermal.GetTemperature(self.sensors[0])]

    values = self.dut.thermal.GetAllTemperatures()
    return [values[name] for name in self.sensors]

  def CheckTemperatures(self, temperatures, elapsed):
    """Check criterion for all specified temperatures.
    1. Make sure temperatures are under limit.
    2. Make sure the differences of all temperatures are in the range.

    Args:
      temperatures: A list of temperatures in different sensors.
      elapsed: elapsed time since heat up.
    """
    for index, temperature_value in enumerate(temperatures):
      with self.group_checker:
        testlog.LogParam('elapsed', elapsed)
        testlog.LogParam('sensor', self.sensors[index])
        testlog.CheckNumericParam('temperature',
                                  temperature_value,
                                  min=self.args.lower_threshold[index],
                                  max=self.args.temperature_limit[index])

      self.max_temperature[index] = max(
          self.max_temperature[index], temperature_value)

      if not self.heated_up[index] and (
          temperature_value >= self.args.lower_threshold[index]):
        self.heated_up[index] = True
        event_log.Log('heated', temperature_value=temperature_value,
                      lower_threshold=self.args.lower_threshold[index],
                      sensor=self.sensors[index],
                      elapsed_sec=elapsed)
        logging.info('Sensor %s heated up to %d C in %d seconds.',
                     self.sensors[index],
                     self.args.lower_threshold[index], elapsed)

      if temperature_value > self.args.temperature_limit[index]:
        event_log.Log('over_heated', temperature_value=temperature_value,
                      temperature_limit=self.args.temperature_limit[index],
                      sensor=self.sensors[index],
                      elapsed_sec=elapsed)
        self.fail('Sensor %s temperature got over %d.' % (
            self.sensors[index], self.args.temperature_limit[index]))

      if elapsed >= self.args.heat_up_timeout_secs and (
          not self.heated_up[index]):
        event_log.Log('slow_temp_slope', temperature_value=temperature_value,
                      lower_threshold=self.args.lower_threshold[index],
                      sensor=self.sensors[index],
                      timeout=self.args.heat_up_timeout_secs)
        logging.info('temperature track: %r', self.temperatures_track)
        self.fail("Temperature %s didn't go over %d in %s seconds." % (
            self.sensors[index],
            self.args.lower_threshold[index],
            self.args.heat_up_timeout_secs))

    if self.args.temperatures_difference:
      difference = max(temperatures) - min(temperatures)
      if difference > self.args.temperatures_difference:
        logging.info('temperature track: %r', self.temperatures_track)
        self.fail('The difference of temperatures %d exceeds the limit %d.' % (
            difference, self.args.temperatures_difference))

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.load = self.args.load or self.dut.info.cpu_count

    self.assertTrue(self.args.heat_up_timeout_secs <= self.args.duration_secs,
                    'heat_up_timeout_secs must not be greater than '
                    'duration_secs.')

    sensors = self.args.sensors or [self.dut.thermal.GetMainSensorName()]
    self.sensors = sensors

    if isinstance(self.args.lower_threshold, int):
      self.args.lower_threshold = [self.args.lower_threshold]
    if isinstance(self.args.temperature_limit, int):
      self.args.temperature_limit = [self.args.temperature_limit]

    self.assertTrue(
        len(sensors) == len(self.args.lower_threshold) and (
            len(sensors) == len(self.args.temperature_limit)),
        'The number of sensors, lower_threshold, and temperature_limit '
        'should be the same.')

    self.heated_up = [False] * len(sensors)
    self.max_temperature = [0] * len(sensors)
    self.temperatures_track = []

    self.group_checker = testlog.GroupParam(
        'temperature',
        ['elapsed', 'sensor', 'temperature'])
    testlog.UpdateParam('sensor', param_type=testlog.PARAM_TYPE.argument)

  def runTest(self):
    start_temperatures = self.GetTemperatures()
    event_log.Log('start_temperatures', tempertures=start_temperatures)
    testlog.LogParam('start_temperatures', start_temperatures)
    logging.info('Starting temperatures are: %s', start_temperatures)

    # Check temperatures before heat up to make sure all sensors are normal.
    self.CheckTemperatures(start_temperatures, 0)
    logging.info('Stressing with %d threads...', self.load)

    with stress_manager.StressManager(self.dut).Run(num_threads=self.load):
      start_time = time.time()
      while time.time() - start_time < self.args.duration_secs:
        time.sleep(1)
        temperatures = self.GetTemperatures()
        self.temperatures_track.append(temperatures)
        self.CheckTemperatures(temperatures, time.time() - start_time)

      logging.info('Passed. Maximum temperature seen is %s',
                   self.max_temperature)
      event_log.Log('passed', max_temperature=self.max_temperature)
      testlog.LogParam('maximum_temperature', self.max_temperature)
