# -*- coding: utf-8 -*-
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

u"""Determines how fast the processor heats/cools.

1. 'cool_down' stage: Runs the fan at <cool_down_fan_rpm> until it
   reaches <cool_down_temperature_c> (at least
   <cool_down_min_duration_secs> but at most
   <cool_down_max_duration_secs>).  Fails if unable to cool down to
   <cool_down_max_temperature_c>.

2. 'idle' stage: Spins the fan to <target_fan_rpm> and waits
   <fan_spin_down_secs>.

3. 'one_core' stage: Runs one core at full speed for <duration_secs>.

4. Determines the thermal slope during this period.  The thermal slope
   is defined as

     ΔT / ΔP / Δt

   where

     ΔT is the change in temperature between the idle and one_core stages.
     ΔP is the change in power usage between the idle and one_core stages.
     Δt is the amount of time the one_core stage was run

   If the thermal slope is not between min_slope and max_slope, the test
   fails.
"""

import logging
import time
import unittest

from cros.factory.device import device_utils
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test import session
from cros.factory.test.utils import stress_manager
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg


POWER_SAMPLES = 3


class ThermalSlopeTest(unittest.TestCase):
  ARGS = [
      Arg('cool_down_fan_rpm', (int, float, str),
          'Fan RPM during cool_down, or the string "auto".',
          default=10000),
      Arg('cool_down_min_duration_secs', (int, float),
          'Minimum duration of cool_down',
          default=10),
      Arg('cool_down_max_duration_secs', (int, float),
          'Maximum duration of cool_down',
          default=60),
      Arg('cool_down_temperature_c', (int, float),
          'Target temperature for cool_down',
          default=50),
      Arg('cool_down_max_temperature_c', (int, float),
          'Maximum allowable temperature after cool_down '
          '(if higher than this, the test will not run). '
          'Defaults to cool_down_temperature_c',
          default=None),
      Arg('target_fan_rpm', (int, float, str),
          'Target RPM of fan during slope test, or the string "auto".',
          default=4000),
      Arg('fan_spin_down_secs', (int, float),
          'Number of seconds to allow for fan spin down',
          default=5),
      Arg('duration_secs', (int, float),
          'Duration of slope test',
          default=5),
      Arg('min_slope', (int, float),
          u'Minimum allowable thermal slope in °C/J',
          default=None),
      Arg('max_slope', (int, float),
          u'Maximum allowable thermal slope in °C/J',
          default=None),
      Arg('console_log', bool,
          'Enable console log (disabling may make results more accurate '
          'since updating the console log on screen requires CPU cycles)',
          default=False),
      Arg('sensor_id', str,
          'An id to specify the power sensor. See Thermal.GetPowerUsage.',
          default=None)
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.log = session.console if self.args.console_log else logging

    # Process to terminate in tear-down.
    self.process = None
    # Last power usage snapshot.
    self.snapshot = None
    # Stage we are currently in and when it starts.
    self.stage = None
    self.stage_start_time = None
    # Last time we slept.
    self.last_sleep = None
    # Group checker and units info for testlog.
    self.sample_group_checker = testlog.GroupParam(
        'sample',
        ['stage', 'fan_rpm', 'temperatures', 'energy', 'power', 'elapsed'])
    testlog.UpdateParam('stage', param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam('energy', value_unit='Joule')
    testlog.UpdateParam('power', value_unit='Watt')
    self.result_group_checker = testlog.GroupParam(
        'result', ['result_stage', 'result_temperature', 'result_power'])
    testlog.UpdateParam('result_temperature', value_unit='degree Celsius')
    testlog.UpdateParam('result_power', value_unit='Watt')

  def _Log(self):
    """Logs the current stage and status.

    Writes an entry to the event log, and either to the session.console
    (if the console_log arg is True) or to the default log (if console_log
    is False).
    """
    self.snapshot = self.dut.thermal.GetPowerUsage(
        last=self.snapshot,
        sensor_id=self.args.sensor_id)
    fan_rpm = self.dut.fan.GetFanRPM()
    elapsed_time = time.time() - self.stage_start_time
    temperatures = self.dut.thermal.GetAllTemperatures()
    self.log.info(
        u'%s (%.1f s): fan_rpm=%s, temp=%d°C, power=%.3f W' % (
            self.stage, elapsed_time,
            fan_rpm, self._MainTemperature(),
            (float('nan') if self.snapshot['power'] is None
             else self.snapshot['power'])))
    event_log.Log('sample',
                  stage=self.stage,
                  fan_rpm=fan_rpm,
                  temperature=temperatures,
                  energy_j=self.snapshot['energy'],
                  power_w=self.snapshot['power'])
    with self.sample_group_checker:
      testlog.LogParam('elapsed', elapsed_time)
      testlog.LogParam('stage', self.stage)
      testlog.LogParam('fan_rpm', fan_rpm)
      testlog.LogParam('temperatures', temperatures)
      testlog.LogParam('energy', self.snapshot['energy'])
      testlog.LogParam('power', self.snapshot['power'])

  def _StartStage(self, stage):
    """Begins a new stage."""
    self.stage = stage
    self.stage_start_time = time.time()
    self.last_sleep = time.time()

  def _MainTemperature(self):
    """Returns the main temperature."""
    return self.dut.thermal.GetTemperature()

  def _Sleep(self):
    """Sleeps one second since the last sleep.

    The time at which the last sleep should have ended is stored
    in last_sleep; we sleep until one second after that.  This
    ensures that we sleep until x seconds since the beginning of
    the stage, even if past sleeps were slightly more or less
    than a second and/or there was any processing time in between
    sleeps.
    """
    time.sleep(max(0, self.last_sleep + 1 - time.time()))
    self.last_sleep += 1

  def runTest(self):
    self._StartStage('cool_down')
    self.dut.fan.SetFanRPM(self.args.cool_down_fan_rpm)
    for i in range(self.args.cool_down_max_duration_secs):
      self._Log()
      if (i >= self.args.cool_down_min_duration_secs and
          self._MainTemperature() <= self.args.cool_down_temperature_c):
        break
      self._Sleep()
    else:
      max_temperature_c = (self.args.cool_down_max_temperature_c or
                           self.args.cool_down_temperature_c)
      if self._MainTemperature() > max_temperature_c:
        self.fail(u'Temperature never got down to %s°C' %
                  max_temperature_c)

    self.dut.fan.SetFanRPM(self.args.target_fan_rpm)

    def RunStage(stage, duration_secs):
      """Runs a stage.

      Args:
        stage: The stage name.
        duration_secs: The duration of the stage in seconds.  If less than
          POWER_SAMPLES, then POWER_SAMPLES is used in order to ensure that
          there are enough samples.

      Returns:
        A tuple containing:
          temp: The final temperature reading.
          power_w: The power used by the CPU package, as determined by
            the last POWER_SAMPLES readings.
          duration_secs: The actual duration of the stage.
      """
      duration_secs = max(duration_secs, POWER_SAMPLES)

      self._StartStage(stage)
      power_w = []
      for i in range(duration_secs + 1):
        self._Log()
        power_w.append(self.snapshot['power'])
        if i != duration_secs:
          self._Sleep()

      temp = self._MainTemperature()
      power_w = sum(power_w[-POWER_SAMPLES:]) / POWER_SAMPLES
      self.log.info(u'%s: temp=%d°C, power: %.3f W',
                    stage, temp, power_w)
      event_log.Log('stage_result',
                    stage=self.stage, temp=temp, power_w=power_w)
      with self.result_group_checker:
        testlog.LogParam('result_stage', self.stage)
        testlog.LogParam('result_temperature', temp)
        testlog.LogParam('result_power', power_w)
      return temp, power_w, duration_secs

    base_temp, base_power_w, _ = RunStage(
        'spin_down', self.args.fan_spin_down_secs)

    with stress_manager.StressManager(self.dut).Run():
      one_core_temp, one_core_power_w, one_core_duration_secs = RunStage(
          'one_core', self.args.duration_secs)

    slope = ((one_core_temp - base_temp) /
             (one_core_power_w - base_power_w) /
             one_core_duration_secs)
    # Always use session.console for this one, since we're done and
    # don't need to worry about conserving CPU cycles.
    session.console.info(u'Δtemp=%d°C, Δpower=%.03f W, duration=%s s',
                         one_core_temp - base_temp,
                         one_core_power_w - base_power_w,
                         one_core_duration_secs)
    session.console.info(u'slope=%.5f°C/J', slope)
    event_log.Log('result', slope=slope)
    testlog.LogParam('result_slope', slope)

    errors = []
    if self.args.min_slope is not None and slope < self.args.min_slope:
      errors.append(
          'Slope %.5f is less than minimum slope %.5f' % (
              slope, self.args.min_slope))
    if self.args.max_slope is not None and slope > self.args.max_slope:
      errors.append(
          'Slope %.5f is greater than maximum slope %.5f' % (
              slope, self.args.max_slope))
    if errors:
      self.fail(', '.join(errors))

  def tearDown(self):
    self.dut.fan.SetFanRPM(self.dut.fan.AUTO)
