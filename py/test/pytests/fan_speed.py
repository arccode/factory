# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# DESCRIPTION:
#
# This is a factory test to ensure the functionality of CPU fan.
#
# The test work as follows:
# 1. Set the fan speed to a target RPM.
# 2. Monitor the fan speed for a given period and record the largest reading..
# 3. Check if the reading is greater than the given minimum requirement.

import factory_common # pylint: disable=W0611
import logging
import threading
import time
import unittest

from cros.factory import system
from cros.factory.test.args import Arg
from cros.factory.test.test_ui import MakeLabel, UI
from cros.factory.test.ui_templates import OneSection

_TEST_TITLE = MakeLabel('Fan Speed Test', u'风扇转速测试')
_MSG_FAN_TESTING = MakeLabel('Testing Fan Speed...', u'测试风扇转速中...')
_MSG_FAN_TEST_FAIL = MakeLabel('Fan Speed Test Failed!', u'风扇测试失败!')
_MSG_FAN_TEST_PASS = MakeLabel('Fan Speed Test Passed!', u'风扇测试通过!')
_ERR_FAN_TEST_FAIL = (lambda observed_rpm, min_expected_rpm:
    'Fan speed failed to reach minimum expected RPM: %s < %s' %
        (observed_rpm, min_expected_rpm))


class testFan(unittest.TestCase):
  ARGS = [
    Arg('target_rpm', (int, float), 'Target RPM to set during test.'),
    Arg('duration_secs', (int, float),
        'The duration of time in seconds to monitor the fan speed.', 10),
    Arg('min_expected_rpm', (int, float),
        'Minumum expected RPM that the fan should achieve to pass the test.')
  ]

  def __init__(self, *args, **kwargs):
    super(testFan, self).__init__(*args, **kwargs)
    self._ui = UI()
    self._template = OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._ec = system.GetEC()
    self._max_observed_rpm = 0
    self._time_left = 0

  def MonitorFanSpeed(self):
    self._time_left = self.args.duration_secs
    observed_rpm = []
    try:
      # Monitor the fan speed for duration_secs seconds.
      while self._time_left > 0:
        try:
          observed_rpm.append(self._ec.GetFanRPM())
        except Exception as e:  # pylint: disable=W0703
          logging.warning(e)
          continue
        time.sleep(0.5)
        self._time_left -= 0.5

      logging.info('Observed RPM: %s', observed_rpm)
      self._max_observed_rpm = max(observed_rpm)
      if self._max_observed_rpm > self.args.min_expected_rpm:
        self._template.SetState(_MSG_FAN_TEST_PASS)
        self._ui.Pass()
      else:
        self._template.SetState(_MSG_FAN_TEST_FAIL)
        self._ui.Fail(_ERR_FAN_TEST_FAIL(self._max_observed_rpm,
                                         self.args.min_expected_rpm))
    finally:
      # Reset fan speed control to auto.
      self._ec.SetFanRPM('auto')

  def runTest(self):
    # Set fan speed to target RPM.
    self._ec.SetFanRPM(self.args.target_rpm)
    self._template.SetState(_MSG_FAN_TESTING)
    threading.Thread(target=self.MonitorFanSpeed).start()
    self._ui.Run()
