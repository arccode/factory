# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''A count down UI for run-in test.

It only shows count down and system loads for run-in period.

Test parameter:
  duration_secs: Number of seconds to count down.
  log_interval (default: 10): Interval of time in seconds to log system status.
  position_top_right (default: False): If True, the countdown window will
      be placed in the top-right corner. Otherwise, it is center aligned.
'''

import datetime
import time
import unittest

from cros.factory.event_log import EventLog
from cros.factory.system import SystemStatus
from cros.factory.test import factory, test_ui
from cros.factory.test.args import Arg


_DEFAULT_GRACE_SECS = 120
_DEFAULT_TEMP_MAX_DELTA = 10


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

  def SetupStatusDetection(self):
    self._grace_secs = self.args.detection_params.get(
        'grace_secs', _DEFAULT_GRACE_SECS)
    self._temp_max_delta = self.args.detection_params.get(
        'temp_max_delta', _DEFAULT_TEMP_MAX_DELTA)
    self._temp_criteria = self.args.detection_params.get(
        'temp_criteria', [])
    self._relative_temp_criteria = self.args.detection_params.get(
        'relative_temp_criteria', [])
    self._fan_min_expected_rpm = self.args.detection_params.get(
        'fan_min_expected_rpm')

  def DetectAbnormalStatus(self, status, last_status):
    # Start abnormal status detection after run-in for a while.
    if self._elapsed_secs < self._grace_secs:
      return

    for index, (current, last) in enumerate(
        zip(status.temperatures, last_status.temperatures)):
      if abs(current - last) > self._temp_max_delta:
        factory.console.warn(
            'ALARM! Temperature index %d delta over %d (current: %d, last: %d)',
            index, self._temp_max_delta, current, last)

    for name, index, warning_temp, critical_temp in self._temp_criteria:
      temp = status.temperatures[index]
      if warning_temp < temp < critical_temp:
        factory.console.warn(
            'ALARM! %s over warning temperature (now: %d, warning: %d)',
            name, temp, warning_temp)
      if temp >= critical_temp:
        factory.console.warn(
            'ALARM! %s over critical temperature (now: %d, critical: %d)',
            name, temp, critical_temp)

    for (relation, first_index, second_index,
        max_diff) in self._relative_temp_criteria:
      first_temp = status.temperatures[first_index]
      second_temp = status.temperatures[second_index]
      if abs(first_temp - second_temp) > max_diff:
        factory.console.warn(
            'ALARM! Temperature between %s over %d (first: %d, second: %d)',
            relation, max_diff, first_temp, second_temp)

    if (self._fan_min_expected_rpm and
        status.fan_rpm < self._fan_min_expected_rpm):
      factory.console.warn('ALARM! Fan rpm %d less than min expected %d',
          status.fan_rpm, self._fan_min_expected_rpm)

  ARGS = [
    Arg('title_en', (str, unicode), 'English title.', 'Countdown'),
    Arg('title_zh', (str, unicode), 'Chinese title.', u'倒數計時'),
    Arg('position_top_right', bool,
        'A workaround for some machines on which graphics test would overlay'
        'countdown info.', False),
    Arg('duration_secs', int, 'Duration of time to countdown.'),
    Arg('log_interval', int,
        'Interval of time in seconds to log system status.', 10),
    Arg('detection_params', dict,
        'Board-specific params for detecting abnormal status', {})
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
    self.SetupStatusDetection()

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
