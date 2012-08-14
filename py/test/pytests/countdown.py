# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''A count down UI for run-in test.

It only shows count down and system loads for run-in period.

Test parameter:
  duration_secs: Number of seconds to count down.
  log_interval (default: 10): Number of seconds to log system status.
  position_top_right (default: False): If True, the countdown window will
      be placed in the top-right corner. Otherwise, it is center aligned.
'''

import datetime
import time
import unittest

from cros.factory.event_log import EventLog
from cros.factory.goofy.system import SystemStatus
from cros.factory.test import factory, test_ui


class CountDownTest(unittest.TestCase):
  def UpdateTimeAndLoad(self):
    self._ui.SetHTML(
        time.strftime('%H:%M:%S', time.gmtime(self._elapsed_secs)),
        id='elapsed-time')
    self._ui.SetHTML(
        time.strftime('%H:%M:%S', time.gmtime(self._remaining_secs)),
        id='remaining-time')
    self._ui.SetHTML(
        ' '.join(open('/proc/loadavg').read().split()[0:3]),
        id='system-load')

  def runTest(self):
    # Allow attributes to be defined outside __init__
    # pylint: disable=W0201
    args = self.test_info.args

    self._ui = test_ui.UI()
    title_en = args.get('title_en', 'Countdown')
    self._ui.SetHTML(title_en, id='countdown-title-en')
    self._ui.SetHTML(args.get('title_zh', title_en), id='countdown-title-zh')

    # A workaround for some machines in which graphics test would
    # overlay countdown info.
    if self.test_info.args.get('position_top_right', False):
      self._ui.RunJS('document.getElementById("countdown-container").className'
                     ' = "float-right";')

    self._duration_secs = self.test_info.args['duration_secs']
    self._log_interval = self.test_info.args.get('log_interval', 10)
    self._start_secs = time.time()
    self._elapsed_secs = 0
    self._remaining_secs = self._duration_secs
    self._next_log_time = 0
    self._event_log = EventLog.ForAutoTest()

    # Loop until count-down ends.
    while self._remaining_secs >= 0:
      self.UpdateTimeAndLoad()

      if time.time() >= self._next_log_time:
        sys_status = SystemStatus()
        self._event_log.Log('system_status', **sys_status.__dict__)
        factory.console.info('Status at %s: %s' % (
            datetime.datetime.now().isoformat(),
            sys_status.__dict__))
        self._next_log_time = time.time() + self._log_interval

      time.sleep(1)
      self._elapsed_secs = time.time() - self._start_secs
      self._remaining_secs = round(self._duration_secs - self._elapsed_secs)
