# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This is a factory test to test thermal response under load.
Tests that under given load:
  - Temperature goes over lower_threshold within heat_up_timeout_secs.
  - Temperature doesn't go over temperature_limit throughout the entire test.

dargs:
  load: Number of threads stressapptest uses to stress the system. Default
      value is the number of processors.
  heat_up_timeout_secs: Timeout interval in seconds for temperature to go over
      lower_threshold.
  lower_threshold: Minimum temperature value required within
      heat_up_timeout_secs.
  temperature_limit: Maximum temperature value allowed throughout the entire
      test.
  duration_secs: Time in seconds for the test to run.
  sensor_index: The index of temperature sensor to use.
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
      Arg('lower_threshold', int, 'Minimum temperature value required within '
          'heat_up_timeout_secs', optional=True, default=45),
      Arg('temperature_limit', int, 'Maximum temperature value allowed',
          optional=True, default=75),
      Arg('duration_secs', int, 'Time in seconds for the test to run',
          optional=True, default=80),
      Arg('sensor_index', int, 'The index of temperature sensor to use',
          optional=True, default=0)
      ]

  def _GetTemperature(self, sensor_index):
    """Gets the temperature reading from specified sensor."""
    return SystemStatus().temperatures[sensor_index]

  def runTest(self):
    load = self.args.load or multiprocessing.cpu_count()

    self.assertTrue(self.args.heat_up_timeout_secs <= self.args.duration_secs,
                    'heat_up_timeout_secs must not be greater than '
                    'duration_secs.')
    start_temperature = self._GetTemperature(self.args.sensor_index)
    Log('start_temperature', temperture=start_temperature)
    logging.info("Starting temperature is %d C", start_temperature)
    logging.info("Stressing with %d threads...", load)
    with LoadManager(duration_secs=self.args.duration_secs,
                     num_threads=load):
      heated_up = False
      max_temperature = 0
      for elapsed in xrange(self.args.duration_secs):
        time.sleep(1)
        temperature_value = self._GetTemperature(self.args.sensor_index)
        max_temperature = max(max_temperature, temperature_value)

        if not heated_up and temperature_value >= self.args.lower_threshold:
          heated_up = True
          Log('heated', temperature_value=temperature_value,
              lower_threshold=self.args.lower_threshold, elapsed_sec=elapsed)
          logging.info("Heated up to %d C in %d seconds",
                       self.args.lower_threshold, elapsed)
        if elapsed >= self.args.heat_up_timeout_secs and not heated_up:
          Log('slow_temp_slope', temperature_value=temperature_value,
              lower_threshold=self.args.lower_threshold,
              timeout=self.args.heat_up_timeout_secs)
          self.fail("Temperature didn't go over %d in %s seconds." %
                    (self.args.lower_threshold, self.args.heat_up_timeout_secs))

        if temperature_value <= self.args.temperature_limit:
          Log('over_heated', temperature_value=temperature_value,
              temperature_limit=self.args.temperature_limit,
              elapsed_sec=elapsed)
          self.fail("Temperature got over %d." % self.args.temperature_limit)

      logging.info("Passed. Maximum temperature seen is %d C", max_temperature)
      Log('passed', max_temperature=max_temperature)
