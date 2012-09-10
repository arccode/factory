# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

u'''Determines how fast the processor heats/cools.

1. 'cool_down' stage: Runs the fan at <cool_down_fan_rpm> until it
   reaches <cool_down_temperature_c> (at least
   <cool_down_min_duration_secs> but at most
   <cool_down_max_duration_secs>).  Fails if unable to cool down to
   that temperature.

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
'''

import logging
import time
import unittest

import factory_common # pylint: disable=W0611
from cros.factory import system
from cros.factory.event_log import EventLog
from cros.factory.system import SystemStatus
from cros.factory.system.msr import MSRSnapshot
from cros.factory.test import factory
from cros.factory.test.args import Arg
from cros.factory.utils.process_utils import Spawn

POWER_SAMPLES = 3

class ThermalSlopeTest(unittest.TestCase):
  ARGS = [
      Arg('cool_down_fan_rpm', (int, float),
          'Fan RPM during cool_down',
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
      Arg('target_fan_rpm', (int, float),
          'Target RPM of fan during slope test',
          default=4000),
      Arg('fan_spin_down_secs', (int, float),
          'Number of seconds to allow for fan spin down',
          default=5),
      Arg('duration_secs', (int, float),
          'Duration of slope test',
          default=5),
      Arg('min_slope', (int, float),
          u'Minimum allowable thermal slope in °C/J',
          optional=True),
      Arg('max_slope', (int, float),
          u'Maximum allowable thermal slope in °C/J',
          optional=True),
      Arg('console_log', bool,
          'Enable console log (disabling may make results more accurate '
          'since updating the console log on screen requires CPU cycles)',
          default=False),
      ]


  def setUp(self):
    self.event_log = EventLog.ForAutoTest()
    self.log = factory.console if self.args.console_log else logging
    self.ec = system.GetEC()

    # Process to terminate in tear-down.
    self.process = None
    # Last MSR snapshot and system status read.
    self.msr = None
    self.system_status = None
    # Stage we are currently in and when it starts.
    self.stage = None
    self.stage_start_time = None
    # Last time we slept.
    self.last_sleep = None

  def _Log(self):
    '''Logs the current stage and status.

    Writes an entry to the event log, and either to the factory console
    (if the console_log arg is True) or to the default log (if console_log
    is False).
    '''
    self.msr = MSRSnapshot(self.msr)
    self.system_status = SystemStatus()
    elapsed_time = time.time() - self.stage_start_time
    self.log.info(
        u'%s (%.1f s): fan_rpm=%d, temp=%d°C, pkg_power_w=%.3f W' % (
            self.stage, elapsed_time,
            self.system_status.fan_rpm, self._MainTemperature(),
            (float('nan') if self.msr.pkg_power_w is None
             else self.msr.pkg_power_w)))
    self.event_log.Log('sample',
                       stage=self.stage,
                       status=self.system_status.__dict__,
                       pkg_energy_j=self.msr.pkg_energy_j,
                       pkg_power_w=self.msr.pkg_power_w)

  def _StartStage(self, stage):
    '''Begins a new stage.'''
    self.stage = stage
    self.stage_start_time = time.time()
    self.last_sleep = time.time()

  def _MainTemperature(self):
    '''Returns the main temperature.'''
    return self.system_status.temperatures[
        self.system_status.main_temperature_index]

  def _Sleep(self):
    '''Sleeps one second since the last sleep.

    The time at which the last sleep should have ended is stored
    in last_sleep; we sleep until one second after that.  This
    ensures that we sleep until x seconds since the beginning of
    the stage, even if past sleeps were slightly more or less
    than a second and/or there was any processing time in between
    sleeps.
    '''
    time.sleep(max(0, self.last_sleep + 1 - time.time()))
    self.last_sleep += 1

  def runTest(self):
    self._StartStage('cool_down')
    self.ec.SetFanRPM(self.args.cool_down_fan_rpm)
    for i in range(self.args.cool_down_max_duration_secs):
      self._Log()
      if (i >= self.args.cool_down_min_duration_secs and
          self._MainTemperature() <= self.args.cool_down_temperature_c):
        break
      self._Sleep()
    else:
      self.fail(u'Temperature never got down to %s°C' %
                self.args.cool_down_max_duration_secs)

    self.ec.SetFanRPM(self.args.target_fan_rpm)

    def RunStage(stage, duration_secs):
      '''Runs a stage.

      Args:
        stage: The stage name.
        duration_secs: The duration of the stage in seconds.  If less than
          POWER_SAMPLES, then POWER_SAMPLES is used in order to ensure that
          there are enough samples.

      Returns:
        A tuple containing:
          temp: The final temperature reading.
          pkg_power_w: The power used by the CPU package, as determined by
            the last POWER_SAMPLES readings.
          duration_secs: The actual duration of the stage.
      '''
      duration_secs = max(duration_secs, POWER_SAMPLES)

      self._StartStage(stage)
      pkg_power_w = []
      for i in range(duration_secs + 1):
        self._Log()
        pkg_power_w.append(self.msr.pkg_power_w)
        if i != duration_secs:
          self._Sleep()

      temp = self._MainTemperature()
      pkg_power_w = sum(pkg_power_w[-POWER_SAMPLES:]) / POWER_SAMPLES
      self.log.info(u'%s: temp=%d°C, pkg_power_w: %.3f W',
                    stage, temp, pkg_power_w)
      self.event_log.Log('stage_result', stage=self.stage,
                         temp=temp, pkg_power_w=pkg_power_w)
      return temp, pkg_power_w, duration_secs

    base_temp, base_pkg_power_w, _ = RunStage(
        'spin_down', self.args.fan_spin_down_secs)

    # Start a while loop in a separate process to use one CPU core
    # (don't do it in-process since Python doesn't have true
    # multithreading)
    self.process = Spawn(['python', '-c', 'while True: pass'])
    one_core_temp, one_core_pkg_power_w, one_core_duration_secs = RunStage(
        'one_core', self.args.duration_secs)

    slope = ((one_core_temp - base_temp) /
             (one_core_pkg_power_w - base_pkg_power_w) /
             one_core_duration_secs)
    # Always use factory.console for this one, since we're done and
    # don't need to worry about conserving CPU cycles.
    factory.console.info(u'Δtemp=%d°C, Δpower=%.03f W, duration=%s s',
                         one_core_temp - base_temp,
                         one_core_pkg_power_w - base_pkg_power_w,
                         one_core_duration_secs)
    factory.console.info(u'slope=%.5f°C/J', slope)
    self.event_log.Log('result', slope=slope)

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
    self.ec.SetFanRPM(self.ec.AUTO)
    if self.process:
      self.process.terminate()
      self.process.wait()
