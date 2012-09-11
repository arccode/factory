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

  ARGS = [
    Arg('title_en', (str, unicode), 'English title.', 'Countdown'),
    Arg('title_zh', (str, unicode), 'Chinese title.', u'倒數計時'),
    Arg('position_top_right', bool,
        'A workaround for some machines on which graphics test would overlay'
        'countdown info.', False),
    Arg('duration_secs', int, 'Duration of time to countdown.'),
    Arg('log_interval', int,
        'Interval of time in seconds to log system status.', 10)
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
        self._next_log_time = time.time() + self.args.log_interval

      time.sleep(1)
      self._elapsed_secs = time.time() - self._start_secs
      self._remaining_secs = round(self.args.duration_secs - self._elapsed_secs)
