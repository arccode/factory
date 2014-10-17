# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This is a factory test to check the functionality of LCD backlight module.

dargs:
  timeout: the test runs at most #seconds (default: 10 seconds).
"""

import unittest
import time

import factory_common  # pylint: disable=W0611
from cros.factory import system
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.test.utils import StartDaemonThread


_MSG_BACKLIGHT_TEST = test_ui.MakeLabel(
    'Please check if backlight brightness is changing from dark to bright.',
    u'请检查萤幕亮度是否由暗变亮',
    'backlight-test-info')
_MSG_PASS_FAIL_PROMPT = test_ui.MakeLabel(
    '</br>Press ENTER to pass, or ESC to fail.',
    u'</br>测试正常请按 ENTER ，不正常请按 ESC',
    'backlight-test-info')
_MSG_TIME_REMAINING = lambda t: test_ui.MakeLabel(
    'Time remaining: %d' % t, u'剩余时间：%d' % t, 'backlight-test-info')

_ID_PROMPT = 'backlight-test-prompt'
_ID_COUNTDOWN_TIMER = 'backlight-test-timer'

_HTML_BACKLIGHT_TEST = '<div id="%s"></div>\n<div id="%s"></div>\n' % (
    _ID_PROMPT, _ID_COUNTDOWN_TIMER)
_BACKLIGHT_TEST_DEFAULT_CSS = '.backlight-test-info { font-size: 2em; }'

class LCDBacklightTest(unittest.TestCase):
  ARGS = [
    Arg('timeout_secs', int, 'Timeout value for the test.',
        default=10)
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.ui.AppendCSS(_BACKLIGHT_TEST_DEFAULT_CSS)
    self.ui.BindStandardKeys()
    self.template = OneSection(self.ui)
    self.template.SetState(_HTML_BACKLIGHT_TEST)
    self.ui.SetHTML(_MSG_BACKLIGHT_TEST, id=_ID_PROMPT)
    self.ui.SetHTML(_MSG_PASS_FAIL_PROMPT, append=True, id=_ID_PROMPT)
    StartDaemonThread(target=self.BrightnessChangeLoop)
    StartDaemonThread(target=self.CountdownTimer)

  def tearDown(self):
    system.SetBacklightBrightness(1.0)

  def CountdownTimer(self):
    """Starts a countdown timer and fails the test if timer reaches zero."""
    time_remaining = self.args.timeout_secs
    while time_remaining > 0:
      self.ui.SetHTML(_MSG_TIME_REMAINING(time_remaining),
                      id=_ID_COUNTDOWN_TIMER)
      time.sleep(1)
      time_remaining -= 1
    self.ui.Fail('Backlight test failed due to timeout.')

  def BrightnessChangeLoop(self):
    """Starts a infinite loop to change backlight brightness from low to high.
    """
    while True:
      for level in [0.2, 0.4, 0.6, 0.8, 1.0]:
        system.SetBacklightBrightness(level)
        time.sleep(0.5)

  def runTest(self):
    self.ui.Run()
