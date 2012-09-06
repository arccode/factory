# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''A factory test to ensure the functionality of CPU fan.

1. Sets the fan speed to a target RPM.
2. Monitors the fan speed for a given period and records the largest reading.
3. Checks that the reading is greater than the given minimum requirement, and
   optionally that the reading has never exceeded a particular maximum.
'''

import factory_common # pylint: disable=W0611
import logging
import threading
import time
import unittest

from cros.factory import system
from cros.factory.event_log import EventLog
from cros.factory.test.args import Arg
from cros.factory.test.test_ui import MakeLabel, UI
from cros.factory.test.ui_templates import OneSection

_TEST_TITLE = MakeLabel('Fan Speed Test', u'风扇转速测试')
_MSG_FAN_TESTING = MakeLabel('Testing Fan Speed...', u'测试风扇转速中...')

def FanTooSlowMessage(observed_rpm, min_expected_rpm):
  return 'Fan speed failed to reach minimum expected RPM: %s < %s' % (
      (observed_rpm, min_expected_rpm))

def FanTooFastMessage(observed_rpm, max_expected_rpm):
  return 'Fan speed exceeded maximum expected RPM: %s > %s' % (
      (observed_rpm, max_expected_rpm))

class testFan(unittest.TestCase):
  ARGS = [
    Arg('target_rpm', (int, float), 'Target RPM to set during test.'),
    Arg('duration_secs', (int, float),
        'The duration of time in seconds to monitor the fan speed.', 10),
    Arg('min_expected_rpm', (int, float),
        'Minumum expected RPM that the fan should achieve to pass the test.'),
    Arg('max_expected_rpm', (int, float),
        'Maximum expected RPM; if this is exceeded the test fails.',
        optional=True),
  ]

  def __init__(self, *args, **kwargs):
    super(testFan, self).__init__(*args, **kwargs)
    self._ui = UI()
    self._template = OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._ec = system.GetEC()
    self._event_log = EventLog.ForAutoTest()

  def MonitorFanSpeed(self):
    end_time = time.time() + self.args.duration_secs
    observed_rpm = []
    # Monitor the fan speed for duration_secs seconds.
    while time.time() < end_time:
      fan_speed_rpm = self._ec.GetFanRPM()
      observed_rpm.append(fan_speed_rpm)
      logging.info('Observed RPM: %s', fan_speed_rpm)
      self._event_log.Log('fan_speed', fan_speed_rpm=fan_speed_rpm)
      time.sleep(0.5)

    max_observed_rpm = max(observed_rpm)
    if max_observed_rpm < self.args.min_expected_rpm:
      self._ui.Fail(FanTooSlowMessage(max_observed_rpm,
                                      self.args.min_expected_rpm))
    elif (self.args.max_expected_rpm and
          max_observed_rpm > self.args.max_expected_rpm):
      self._ui.Fail(FanTooFastMessage(max_observed_rpm,
                                      self.args.max_expected_rpm))
    else:
      self._ui.Pass()

  def tearDown(self):
    self._ec.SetFanRPM(self._ec.AUTO)

  def runTest(self):
    # Set fan speed to target RPM.
    self._ec.SetFanRPM(self.args.target_rpm)
    self._template.SetState(_MSG_FAN_TESTING)
    threading.Thread(target=self.MonitorFanSpeed).start()
    self._ui.Run()
