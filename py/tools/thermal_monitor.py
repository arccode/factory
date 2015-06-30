#!/usr/bin/env python
# Copyright (c) 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''Monitor all the thermal sensors.

Only dump when delta is over a predefined value in case making the disk full.
'''

import argparse
import logging
import syslog
import time

import factory_common  # pylint: disable=W0611
from cros.factory import system
from cros.factory.test import factory


class TemperaturesMonitor(object):
  def __init__(self, period_secs, delta):
    self._period_secs = period_secs
    self._delta = delta
    self._last_success = False
    self._last_temperatures = []
    self._sensor_array_changed = False
    factory.init_logging()

  def _GetThermalData(self):
    temperatures = []
    self._sensor_array_changed = False
    try:
      temperatures = system.GetBoard().GetTemperatures()
      self._last_success = True
      # Looking at the len in case the any sensor is broken during the
      # monitoring. In such case, the monitor data should be showed.
      if len(self._last_temperatures) != len(temperatures):
        self._last_temperatures = temperatures
        self._sensor_array_changed = True
    except:  # pylint: disable=W0702
      syslog.syslog('Unable to get all temperatures.')
      logging.exceptions('Unable to get all temperatures.')
      self._last_success = False
    return temperatures

  def Check(self):
    """Checks the current temperatures."""
    current_temperatures = self._GetThermalData()
    if self._last_success:
      worth_to_output = False
      if self._sensor_array_changed == True:
        syslog.syslog('Sensors changed (added or removed).')
        worth_to_output = True
      else:
        # In order not to overflow the logs, only output if the
        # delta is larger than we expected. The _sensor_array_changed
        # guaranteed that length will be the same to compare.
        worth_to_output = any(
            [abs(self._last_temperatures[i] - current_temperatures[i]) >=
             self._delta for i in xrange(len(self._last_temperatures))])

      if worth_to_output:
        self._last_temperatures = current_temperatures
        syslog.syslog('Temperatures: %s' % current_temperatures)
        logging.info('Temperatures: %s', current_temperatures)

  def CheckForever(self):
    while True:
      self.Check()
      time.sleep(self._period_secs)

def main():
  parser = argparse.ArgumentParser(description='Monitor CPU usage')
  syslog.openlog('factory_thermal_monitor')

  parser.add_argument('--period_secs', '-p', help='Interval between checks',
                      type=float, required=False, default=120)
  parser.add_argument('--delta', '-d',
                      help='Changes less than delta will be supressed',
                      type=float, required=False, default=0)
  args = parser.parse_args()
  syslog.syslog('Monitoring thermal with period %.2f, delta %.2f' % (
      args.period_secs, args.delta))
  if args.period_secs <= 0:
    syslog.syslog('Disable monitoring.')
    return

  monitor = TemperaturesMonitor(args.period_secs, args.delta)
  monitor.CheckForever()

if __name__ == '__main__':
  main()
