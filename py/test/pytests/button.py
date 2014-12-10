# -*- coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests button functionality.
"""

import datetime
import subprocess
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import Log

from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.countdown_timer import StartCountdownTimer

from cros.factory.test.ui_templates import OneSection
from cros.factory.test.utils import StartDaemonThread
from cros.factory.utils import net_utils

_DEFAULT_TIMEOUT = 30

_MSG_PROMPT_PRESS = lambda en, zh: test_ui.MakeLabel(
    'Press the %s button' % en, u'按下%s按钮' % zh, 'button-test-info')
_MSG_PROMPT_RELEASE = test_ui.MakeLabel(
    'Release the button', u'松开按钮', 'button-test-info')

_ID_PROMPT = 'button-test-prompt'
_ID_COUNTDOWN_TIMER = 'button-test-timer'
_HTML_BUTTON_TEST = ('<div id="%s"></div>\n'
                     '<div id="%s" class="button-test-info"></div>\n' %
                     (_ID_PROMPT, _ID_COUNTDOWN_TIMER))

_BUTTON_TEST_DEFAULT_CSS = '.button-test-info { font-size: 2em; }'


class ButtonTest(unittest.TestCase):
  """Button factory test."""
  ARGS = [
    Arg('timeout_secs', int, 'Timeout value for the test.',
        default=_DEFAULT_TIMEOUT),
    Arg('button_key_name', str, 'Button key name for evdev.',
        optional=False),
    Arg('event_id', int, 'Event ID for evdev. None for auto probe.',
        default=None, optional=True),
    Arg('button_name_en', (str, unicode), 'The name of the button in English.',
        optional=False),
    Arg('button_name_zh', (str, unicode), 'The name of the button in Chinese.',
        optional=False),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.event_dev = '/dev/input/event%d' % self.args.event_id
    self.ui.AppendCSS(_BUTTON_TEST_DEFAULT_CSS)
    self.template.SetState(_HTML_BUTTON_TEST)
    self.ui.SetHTML(_MSG_PROMPT_PRESS(self.args.button_name_en,
                                      self.args.button_name_zh), id=_ID_PROMPT)

    # Create a thread to monitor button events.
    StartDaemonThread(target=self.MonitorButtonEvent)
    # Create a thread to run countdown timer.
    StartCountdownTimer(
        self.args.timeout_secs,
        lambda: self.ui.Fail('Button test failed due to timeout.'),
        self.ui,
        _ID_COUNTDOWN_TIMER)

    # Variables to track the time it takes to press and release the button
    self._start_waiting_sec = self.getCurrentEpochSec()
    self._pressed_sec = 0
    self._released_sec = 0

  def tearDown(self):
    Log('button_wait_sec',
        time_to_press_sec=(self._pressed_sec - self._start_waiting_sec),
        time_to_release_sec=(self._released_sec - self._pressed_sec))

  def getCurrentEpochSec(self):
    '''Returns the time since epoch.'''
    return float(datetime.datetime.now().strftime("%s.%f"))

  def ButtonIsPressed(self):
    return (subprocess.Popen(['evtest', '--query', self.event_dev, 'EV_KEY',
                              self.args.button_key_name]).wait() != 0)

  def MonitorButtonEvent(self):
    net_utils.PollForCondition(
        self.ButtonIsPressed,
        timeout=self.args.timeout_secs,
        condition_name='WaitForPress')
    self._pressed_sec = self.getCurrentEpochSec()
    self.AskForButtonRelease()
    elapsed_time = self._pressed_sec - self._start_waiting_sec
    net_utils.PollForCondition(
        lambda: not self.ButtonIsPressed(),
        timeout=self.args.timeout_secs - elapsed_time,
        condition_name='WaitForRelease')
    self._released_sec = self.getCurrentEpochSec()
    self.ui.Pass()

  def AskForButtonRelease(self):
    self.ui.SetHTML(_MSG_PROMPT_RELEASE, id=_ID_PROMPT)

  def runTest(self):
    self.ui.Run()
