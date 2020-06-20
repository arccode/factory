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

from __future__ import division

import collections
import logging
import os
import time

from cros.factory.device import device_utils
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import time_utils
from cros.factory.utils import type_utils


_WARNING_TEMP_RATIO = 0.95
_CRITICAL_TEMP_RATIO = 0.98


Status = collections.namedtuple('Status', ['temperatures', 'fan_rpm'])


class CountDownTest(test_case.TestCase):
  """A countdown test that monitors and logs various system status."""

  ui_class = test_ui.UI
  ARGS = [
      Arg('duration_secs', int, 'Duration of time to countdown.'),
      Arg('log_interval', int,
          'Interval of time in seconds to log system status.', default=120),
      Arg('ui_update_interval', int,
          'Interval of time in seconds to update system status on UI.',
          default=10),
      Arg('grace_secs', int,
          'Grace period before starting abnormal status detection.',
          default=120),
      Arg('temp_max_delta', int,
          'Allowed difference between current and last temperature of a '
          'sensor.', default=None),
      Arg('temp_criteria', list,
          'A list of rules to check that temperature is under the given range, '
          'rule format: (name, temp_sensor, warning_temp, critical_temp)',
          default=[]),
      Arg('relative_temp_criteria', list,
          'A list of rules to check the difference between two temp sensors, '
          'rule format: (relation, first_sensor, second_sensor, max_diff). '
          'relation is a text output with warning messages to describe the two '
          'temp sensors in the rule', default=[]),
      Arg('fan_min_expected_rpm', int, 'Minimum fan rpm expected',
          default=None),
      Arg('allow_invalid_temp', bool,
          'Allow invalid temperature e.g. values less then or equal to zero, '
          'which may mean thermal nodes are not ready in early builds.',
          default=False)
  ]

  def FormatSeconds(self, secs):
    hours = int(secs / 3600)
    minutes = int((secs / 60) % 60)
    seconds = int(secs % 60)
    return '%02d:%02d:%02d' % (hours, minutes, seconds)

  def UpdateTimeAndLoad(self):
    self.ui.SetHTML(
        self.FormatSeconds(self._elapsed_secs),
        id='cd-elapsed-time')
    self.ui.SetHTML(
        self.FormatSeconds(self.args.duration_secs - self._elapsed_secs),
        id='cd-remaining-time')
    self.ui.SetHTML(
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
    self.ui.AppendHTML(
        '<div>%s</div>' % test_ui.Escape(log_str),
        id='cd-log-panel',
        autoscroll=True)
    self.ui.RunJS('const panel = document.getElementById("cd-log-panel");'
                  'if (panel.childNodes.length > 512)'
                  '  panel.removeChild(panel.firstChild);')

  def UpdateLegend(self, sensor_names):
    for i, sensor in enumerate(sensor_names):
      self.ui.AppendHTML(
          '<div class="cd-legend-item">[%d] %s</div>' % (i, sensor),
          id='cd-legend-item-panel')
    if sensor_names:
      self.ui.ToggleClass('cd-legend-panel', 'hidden', False)

  def DetectAbnormalStatus(self, status, last_status):
    def GetTemperature(sensor):
      try:
        if sensor is None:
          sensor = self._main_sensor
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
        if last is None or current is None:
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
        continue

      if warning_temp is None or critical_temp is None:
        try:
          sys_temp = self._dut.thermal.GetCriticalTemperature(sensor)
        except NotImplementedError:
          raise type_utils.TestFailure(
              'Failed to get the critical temperature of %r, please explicitly '
              'specify the value in the test arguments.' % name)
        if warning_temp is None:
          warning_temp = sys_temp * _WARNING_TEMP_RATIO
        if critical_temp is None:
          critical_temp = sys_temp * _CRITICAL_TEMP_RATIO

      if temp >= critical_temp:
        warnings.append(
            '%s over critical temperature (now: %.1f, critical: %.1f)' % (
                name, temp, critical_temp))
      elif temp >= warning_temp:
        warnings.append(
            '%s over warning temperature (now: %.1f, warning: %.1f)' %
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
      elif abs(first_temp - second_temp) > max_diff:
        warnings.append('Temperature difference between %s over %d '
                        '(first: %d, second: %d)' %
                        (relation, max_diff, first_temp, second_temp))

    if self.args.fan_min_expected_rpm:
      for i, fan_rpm in enumerate(status.fan_rpm):
        if fan_rpm < self.args.fan_min_expected_rpm:
          warnings.append('Fan %d rpm %d less than min expected %d' %
                          (i, fan_rpm, self.args.fan_min_expected_rpm))

    if not self.args.allow_invalid_temp:
      for sensor, temp in status.temperatures.items():
        if temp <= 0:
          warnings.append('Thermal zone %s reports abnormal temperature %d'
                          % (sensor, temp))

    in_grace_period = self._elapsed_secs < self.args.grace_secs
    if warnings:
      event_log.Log('warnings', elapsed_secs=self._elapsed_secs,
                    in_grace_period=in_grace_period, warnings=warnings)
      if not in_grace_period:
        for w in warnings:
          session.console.warn(w)

    with self._group_checker:
      testlog.CheckNumericParam(
          'elapsed', self._elapsed_secs, max=self.args.grace_secs)
      testlog.LogParam('temperatures', status.temperatures)
      testlog.LogParam('fan_rpm', status.fan_rpm)
      testlog.LogParam('warnings', warnings)

  def SnapshotStatus(self):
    return Status(self._dut.thermal.GetAllTemperatures(),
                  self._dut.fan.GetFanRPM())

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._main_sensor = self._dut.thermal.GetMainSensorName()
    # Normalize the sensors so main sensor is always the first one.
    sensors = sorted(self._dut.thermal.GetAllSensorNames())
    sensors.insert(0, sensors.pop(sensors.index(self._main_sensor)))
    self._sensors = sensors
    # Group checker for Testlog.
    self._group_checker = testlog.GroupParam(
        'system_status', ['elapsed', 'temperatures', 'fan_rpm', 'warnings'])
    testlog.UpdateParam('elapsed', description='In grace period or not')

    self._start_secs = time.time()
    self._elapsed_secs = 0
    self._next_log_time = 0
    self._next_ui_update_time = 0
    self._verbose_log = None
    self.goofy = state.GetInstance()

  def runTest(self):
    verbose_log_path = session.GetVerboseTestLogPath()
    file_utils.TryMakeDirs(os.path.dirname(verbose_log_path))
    logging.info('Raw verbose logs saved in %s', verbose_log_path)
    self._verbose_log = open(verbose_log_path, 'a')

    last_status = self.SnapshotStatus()

    self.UpdateLegend(self._sensors)

    # Loop until count-down ends.
    while self._elapsed_secs < self.args.duration_secs:
      self.UpdateTimeAndLoad()

      current_time = time.time()
      if (current_time >= self._next_log_time or
          current_time >= self._next_ui_update_time):
        sys_status = self.SnapshotStatus()

      if current_time >= self._next_log_time:
        event_log.Log('system_status', elapsed_secs=self._elapsed_secs,
                      **sys_status._asdict())
        self.DetectAbnormalStatus(sys_status, last_status)
        last_status = sys_status
        self._next_log_time = current_time + self.args.log_interval

      if current_time >= self._next_ui_update_time:
        self.UpdateUILog(sys_status)
        self._next_ui_update_time = current_time + self.args.ui_update_interval

      self.Sleep(1)
      self._elapsed_secs = time.time() - self._start_secs

    self._verbose_log.close()
    self.goofy.WaitForWebSocketUp()
