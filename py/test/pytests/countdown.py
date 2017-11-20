# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A count down monitor for better user interface in run-in tests.

Description
-----------
Count down and display system load. This is helpful for run-in phase to run
multiple stress tests (for example, CPU, memory, disk, GPU, ... etc) in
background so operator can see how long the run-in has been executed, and a
quick overview of system status.  It also alarms if there's any abnormal status
(for example overheat) detected during run-in.

Test Procedure
--------------
This test is designed to run in parallel with other background tests.
No user interaction is needed but if there were abnormal events operator should
collect debug logs for fault analysis.

Dependency
----------
- Thermal in Device API (`cros.factory.device.thermal`) for system thermal
  sensor readings.

Examples
--------
To run a set of tests for 120 seconds in parallel with countdown showing
progress, add this in test list::

  {
    "pytest_name": "countdown",
    "args": {
      "duration_secs": 120
    }
  }

To run 8 hours and alert if main sensor (CPU) reaches 60 Celcius and fail when
exceeding 65 Celcius::

  {
    "pytest_name": "countdown",
    "args": {
      "duration_secs": 28800,
      "temp_criteria": [
        ["CPU", null, 60, 65]
      ]
    }
  }
"""

import collections
import logging
import os
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import event_log
from cros.factory.test import session
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import time_utils


class CountDownTest(unittest.TestCase):
  """A countdown test that monitors and logs various system status."""

  ARGS = [
      Arg('duration_secs', int, 'Duration of time to countdown.'),
      Arg('log_interval', int,
          'Interval of time in seconds to log system status.', 120),
      Arg('ui_update_interval', int,
          'Interval of time in seconds to update system status on UI.', 10),
      Arg('grace_secs', int,
          'Grace period before starting abnormal status detection.', 120),
      Arg('temp_max_delta', int,
          'Allowed difference between current and last temperature of a '
          'sensor.', None),
      Arg('temp_criteria', (list, tuple),
          'A list of rules to check that temperature is under the given range, '
          'rule format: (name, temp_sensor, warning_temp, critical_temp)', []),
      Arg('relative_temp_criteria', (list, tuple),
          'A list of rules to check the difference between two temp sensors, '
          'rule format: (relation, first_sensor, second_sensor, max_diff). '
          'relation is a text output with warning messages to describe the two '
          'temp sensors in the rule', []),
      Arg('fan_min_expected_rpm', int, 'Minimum fan rpm expected', None)
  ]

  def FormatSeconds(self, secs):
    hours = int(secs / 3600)
    minutes = int((secs / 60) % 60)
    seconds = int(secs % 60)
    return '%02d:%02d:%02d' % (hours, minutes, seconds)

  def UpdateTimeAndLoad(self):
    self._ui.SetHTML(
        self.FormatSeconds(self._elapsed_secs),
        id='cd-elapsed-time')
    self._ui.SetHTML(
        self.FormatSeconds(self._remaining_secs),
        id='cd-remaining-time')
    self._ui.SetHTML(
        ' '.join(open('/proc/loadavg').read().split()[0:3]),
        id='cd-system-load')

  def UpdateUILog(self, sys_status):
    # Simplify thermal output by the order of self._sensors
    log_items = [time_utils.TimeString(), 'Temperatures: %s' %
                 [sys_status.temperatures[sensor] for sensor in self._sensors],
                 'Fan RPM: %s' % sys_status.fan_rpm]
    log_str = '.  '.join(log_items)
    self._verbose_log.write(log_str + os.linesep)
    self._verbose_log.flush()
    self._ui.AppendHTML('<div>%s</div>' % log_str, id='cd-log-panel')
    self._ui.RunJS('const panel = document.getElementById("cd-log-panel");'
                   'if (panel.childNodes.length > 512)'
                   '  panel.removeChild(panel.firstChild);'
                   'panel.scrollTop = panel.scrollHeight;')

  def UpdateLegend(self, sensor_names):
    for i, sensor in enumerate(sensor_names):
      self._ui.AppendHTML('<div class="cd-legend-item">[%d] %s</div>' %
                          (i, sensor), id='cd-legend-item-panel')
    if sensor_names:
      self._ui.RunJS('$("cd-legend-panel").style.display = "block";')

  def DetectAbnormalStatus(self, status, last_status):
    def GetTemperature(sensor):
      try:
        if sensor is None:
          sensor = self._main_sensor  # _main_sensor is basestring.
        return status.temperatures[sensor]
      except IndexError:
        return None

    warnings = []

    if self.args.temp_max_delta:
      if len(status.temperatures) != len(last_status.temperatures):
        warnings.append(
            'Number of temperature sensors differ (current: %d, last: %d) ' %
            (len(status.temperatures), len(last_status.temperatures)))

      for sensor in status.temperatures:
        current = status.temperatures[sensor]
        last = last_status.temperatures[sensor]
        # Ignore the case when both are None since it could just mean the
        # sensor doesn't exist. If only one of them is None, then there
        # is a problem.
        if last is None and current is None:
          continue
        elif last is None or current is None:
          warnings.append(
              'Cannot read temperature sensor %s (current: %r, last: %r)' %
              (sensor, current, last))
        elif abs(current - last) > self.args.temp_max_delta:
          warnings.append(
              'Temperature sensor %s delta over %d (current: %d, last: %d)' %
              (sensor, self.args.temp_max_delta, current, last))

    for name, sensor, warning_temp, critical_temp in self.args.temp_criteria:
      temp = GetTemperature(sensor)
      if temp is None:
        warnings.append('%s temperature unavailable' % name)
      elif temp >= critical_temp:
        warnings.append('%s over critical temperature (now: %d, critical: %d)' %
                        (name, temp, critical_temp))
      elif temp >= warning_temp:
        warnings.append('%s over warning temperature (now: %d, warning: %d)' %
                        (name, temp, warning_temp))

    for (relation, first_sensor, second_sensor,
         max_diff) in self.args.relative_temp_criteria:
      first_temp = GetTemperature(first_sensor)
      second_temp = GetTemperature(second_sensor)
      if first_temp is None or second_temp is None:
        unavailable_sensor = []
        if first_temp is None:
          unavailable_sensor.append(first_sensor)
        if second_temp is None:
          unavailable_sensor.append(second_sensor)
        warnings.append(
            'Cannot measure temperature difference between %s: '
            'temperature %s unavailable' %
            (relation, ', '.join(unavailable_sensor)))
      else:
        if abs(first_temp - second_temp) > max_diff:
          warnings.append('Temperature difference between %s over %d '
                          '(first: %d, second: %d)' %
                          (relation, max_diff, first_temp, second_temp))

    if self.args.fan_min_expected_rpm:
      for i, ith_fan_rpm in enumerate(status.fan_rpm):
        if ith_fan_rpm < self.args.fan_min_expected_rpm:
          warnings.append('Fan %d rpm %d less than min expected %d' %
                          (i, ith_fan_rpm, self.args.fan_min_expected_rpm))

    in_grace_period = self._elapsed_secs < self.args.grace_secs
    if warnings:
      event_log.Log('warnings', elapsed_secs=self._elapsed_secs,
                    in_grace_period=in_grace_period, warnings=warnings)
      if not in_grace_period:
        for w in warnings:
          session.console.warn(w)

  def SnapshotStatus(self):
    return self.Status(self._dut.thermal.GetAllTemperatures(),
                       self._dut.fan.GetFanRPM())

  def setUp(self):
    self.Status = collections.namedtuple('Status', ['temperatures', 'fan_rpm'])
    self._dut = device_utils.CreateDUTInterface()
    self._main_sensor = self._dut.thermal.GetMainSensorName()
    # Normalize the sensors so main sensor is always the first one.
    sensors = self._dut.thermal.GetAllSensorNames()
    sensors.sort()
    sensors.insert(0, sensors.pop(sensors.index(self._main_sensor)))
    self._sensors = sensors
    self._ui = test_ui.UI()

  def runTest(self):
    self._ui.RunInBackground(self._runTest)
    self._ui.Run()

  def _runTest(self):
    # pylint: disable=attribute-defined-outside-init
    verbose_log_path = session.GetVerboseTestLogPath()
    file_utils.TryMakeDirs(os.path.dirname(verbose_log_path))
    logging.info('Raw verbose logs saved in %s', verbose_log_path)
    self._verbose_log = open(verbose_log_path, 'a')
    self._start_secs = time.time()
    self._elapsed_secs = 0
    self._remaining_secs = self.args.duration_secs
    self._next_log_time = 0
    self._next_ui_update_time = 0
    last_status = self.SnapshotStatus()

    try:
      self.UpdateLegend(self._sensors)
    except NotImplementedError:
      pass

    # Loop until count-down ends.
    while self._remaining_secs >= 0:
      self.UpdateTimeAndLoad()

      current_time = time.time()
      if (current_time >= self._next_log_time or
          current_time >= self._next_ui_update_time):
        sys_status = self.SnapshotStatus()

      if current_time >= self._next_log_time:
        event_log.Log('system_status', elapsed_secs=self._elapsed_secs,
                      **sys_status.__dict__)
        self.DetectAbnormalStatus(sys_status, last_status)
        last_status = sys_status
        self._next_log_time = current_time + self.args.log_interval

      if current_time >= self._next_ui_update_time:
        self.UpdateUILog(sys_status)
        self._next_ui_update_time = current_time + self.args.ui_update_interval

      time.sleep(1)
      self._elapsed_secs = time.time() - self._start_secs
      self._remaining_secs = round(self.args.duration_secs - self._elapsed_secs)
