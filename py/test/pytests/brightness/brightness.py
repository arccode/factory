# -*- coding: utf-8 -*-
#
# Copyright (c) 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''This is a factory test to check the brightness of LCD backlight or LEDs.'''

import unittest
import time

import factory_common  # pylint: disable=W0611
from cros.factory.test import dut, test_ui
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils.process_utils import StartDaemonThread


_MSG_CSS_CLASS = 'brightness-test-info'
_MSG_PASS_FAIL_PROMPT = test_ui.MakeLabel(
    '</br>Press ENTER to pass, or ESC to fail.',
    u'</br>测试正常请按 ENTER ，不正常请按 ESC',
    _MSG_CSS_CLASS)
_MSG_TIME_REMAINING = (
    'Time remaining: %d',
    u'剩余时间：%d')

_ID_PROMPT = 'brightness-test-prompt'
_ID_COUNTDOWN_TIMER = 'brightness-test-timer'

_HTML_BRIGHTNESS_TEST = '<div id="%s"></div>\n<div id="%s"></div>\n' % (
    _ID_PROMPT, _ID_COUNTDOWN_TIMER)
_BRIGHTNESS_TEST_DEFAULT_CSS = '.brightness-test-info { font-size: 2em; }'


class BrightnessTest(unittest.TestCase):
  ARGS = [
      Arg('timeout_secs', int, 'Timeout value for the test in seconds.',
          default=10),
      Arg('msg_en', str, 'Message (HTML in English)'),
      Arg('msg_zh', (str, unicode), 'Message (HTML in Chinese)',
          optional=True),
      Arg('levels', (tuple, list), 'A sequence of brightness levels.'),
      Arg('interval_secs', (int, float),
          'Time for each brightness level in seconds.')]

  def setUp(self):
    self.dut = dut.Create()
    self.ui = test_ui.UI()
    self.ui.AppendCSS(_BRIGHTNESS_TEST_DEFAULT_CSS)
    self.ui.BindStandardKeys()
    self.template = OneSection(self.ui)
    self.template.SetState(_HTML_BRIGHTNESS_TEST)
    self.ui.SetHTML(test_ui.MakeLabel(self.args.msg_en, self.args.msg_zh,
                                      _MSG_CSS_CLASS), id=_ID_PROMPT)
    self.ui.SetHTML(_MSG_PASS_FAIL_PROMPT, append=True, id=_ID_PROMPT)
    StartDaemonThread(target=self._BrightnessChangeLoop)
    StartDaemonThread(target=self._CountdownTimer)

  def runTest(self):
    self.ui.Run()

  def tearDown(self):
    raise NotImplementedError

  def _SetBrightnessLevel(self, level):
    raise NotImplementedError

  def _BrightnessChangeLoop(self):
    '''Starts an infinite loop to change brightness.'''
    while True:
      for level in self.args.levels:
        self._SetBrightnessLevel(level)
        time.sleep(self.args.interval_secs)

  def _CountdownTimer(self):
    '''Starts a countdown timer and fails the test if timer reaches zero.'''
    time_remaining = self.args.timeout_secs
    while time_remaining > 0:
      label = test_ui.MakeLabel(_MSG_TIME_REMAINING[0] % time_remaining,
                                _MSG_TIME_REMAINING[1] % time_remaining,
                                _MSG_CSS_CLASS)
      self.ui.SetHTML(label, id=_ID_COUNTDOWN_TIMER)
      time.sleep(1)
      time_remaining -= 1
    self.ui.Fail('Brightness test failed due to timeout.')
