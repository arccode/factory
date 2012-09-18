# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''A count down UI for run-in test.

It shows count down and system loads for run-in period. It also alarms if
there's any abnormal status detected during run-in.
'''

import datetime
import time
import unittest

from cros.factory.event_log import EventLog
from cros.factory.system import SystemStatus
from cros.factory.test import factory, test_ui
from cros.factory.test.args import Arg


class CountDownTest(unittest.TestCase):
  def FormatSeconds(self, secs):
    hours = int(secs / 3600)
    minutes = int((secs / 60) % 60)
    seconds = int(secs % 60)
    return '%02d:%02d:%02d' % (hours, minutes, seconds)

  def UpdateTimeAndLoad(self):
    self._ui.SetHTML(
        self.FormatSeconds(self._elapsed_secs),
        id='elapsed-time')
    self._ui.SetHTML(
        self.FormatSeconds(self._remaining_secs),
        id='remaining-time')
    self._ui.SetHTML(
        ' '.join(open('/proc/loadavg').read().split()[0:3]),
        id='system-load')

  def DetectAbnormalStatus(self, status, last_status):
    warnings = []

    if self.args.temp_max_delta:
      for index, (current, last) in enumerate(
          zip(status.temperatures, last_status.temperatures)):
        # Ignore the case when both are None since it could just mean the
        # sensor doesn't exist. If only one of them is None, then there
        # is a problem.
        if last is None and current is None:
          continue
        if last is None or current is None:
          warnings.append(
              'Cannot read temperature index %d (current: %r, last: %r)' %
              (index, current, last))
        if abs(current - last) > self.args.temp_max_delta:
          warnings.append(
              'Temperature index %d delta over %d (current: %d, last: %d)' %
              (index, self.args.temp_max_delta, current, last))

    for name, index, warning_temp, critical_temp in self.args.temp_criteria:
      temp = status.temperatures[index]
      if warning_temp < temp < critical_temp:
        warnings.append('%s over warning temperature (now: %d, warning: %d)' %
                        (name, temp, warning_temp))
      if temp >= critical_temp:
        warnings.append('%s over critical temperature (now: %d, critical: %d)' %
                        (name, temp, critical_temp))

    for (relation, first_index, second_index,
        max_diff) in self.args.relative_temp_criteria:
      first_temp = status.temperatures[first_index]
      second_temp = status.temperatures[second_index]
      if abs(first_temp - second_temp) > max_diff:
        warnings.append('Temperature difference between %s over %d '
                        '(first: %d, second: %d)' %
                        (relation, max_diff, first_temp, second_temp))

    if (self.args.fan_min_expected_rpm and
        status.fan_rpm < self.args.fan_min_expected_rpm):
      warnings.append('Fan rpm %d less than min expected %d' %
                      (status.fan_rpm, self.args.fan_min_expected_rpm))

    in_grace_period = self._elapsed_secs < self.args.grace_secs
    if warnings:
      self._event_log.Log('warnings', elapsed_secs=self._elapsed_secs,
                          in_grace_period=in_grace_period, warnings=warnings)
      if not in_grace_period:
        for w in warnings:
          factory.console.warn(w)

  ARGS = [
    Arg('title_en', (str, unicode), 'English title.', 'Countdown'),
    Arg('title_zh', (str, unicode), 'Chinese title.', u'倒數計時'),
    Arg('position_top_right', bool,
        'A workaround for some machines on which graphics test would overlay '
        'countdown info.', False),
    Arg('duration_secs', int, 'Duration of time to countdown.'),
    Arg('log_interval', int,
        'Interval of time in seconds to log system status.', 10),
    Arg('grace_secs', int,
        'Grace period before starting abnormal status detection.', 120,
        optional=True),
    Arg('temp_max_delta', int,
        'Allowed difference between current and last temperature of a sensor.',
        None, optional=True),
    Arg('temp_criteria', (list, tuple),
        'A list of rules to check that temperature is under the given range, '
        'rule format: (name, temp_index, warning_temp, critical_temp)', [],
        optional=True),
    Arg('relative_temp_criteria', (list, tuple),
        'A list of rules to check the difference between two temp sensors, '
        'rule format: (relation, first_index, second_index, max_diff). '
        'relation is a text output with warning messages to describe the two '
        'temp sensors in the rule', [], optional=True),
    Arg('fan_min_expected_rpm', int, 'Minimum fan rpm expected', None,
        optional=True),
  ]

  def runTest(self):
    # Allow attributes to be defined outside __init__
    # pylint: disable=W0201

    self._ui = test_ui.UI()
    self._ui.SetHTML(self.args.title_en, id='countdown-title-en')
    self._ui.SetHTML(self.args.title_zh, id='countdown-title-zh')

    # A workaround for some machines in which graphics test would
    # overlay countdown info.
    if self.args.position_top_right:
      self._ui.RunJS('document.getElementById("countdown-container").className'
                     ' = "float-right";')

    self._start_secs = time.time()
    self._elapsed_secs = 0
    self._remaining_secs = self.args.duration_secs
    self._next_log_time = 0
    self._event_log = EventLog.ForAutoTest()
    last_status = SystemStatus()

    # Loop until count-down ends.
    while self._remaining_secs >= 0:
      self.UpdateTimeAndLoad()

      if time.time() >= self._next_log_time:
        sys_status = SystemStatus()
        self._event_log.Log('system_status', elapsed_secs=self._elapsed_secs,
                            **sys_status.__dict__)
        factory.console.info('Status at %s (%d seconds elapsed): %s' % (
            datetime.datetime.now().isoformat(),
            self._elapsed_secs,
            sys_status.__dict__))
        self.DetectAbnormalStatus(sys_status, last_status)
        last_status = sys_status
        self._next_log_time = time.time() + self.args.log_interval

      time.sleep(1)
      self._elapsed_secs = time.time() - self._start_secs
      self._remaining_secs = round(self.args.duration_secs - self._elapsed_secs)
