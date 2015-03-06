# -*- coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests button functionality.

  You can specify the button in multiple ways:

  - gpio:[-]NUM.
    A GPIO button. NUM indicates GPIO number, and +/- indicates polarity
    (- for active low, otherwise active high).

  - crossystem:NAME.
    A crossystem value (1 or 0) that can be retrived by NAME.

  - KEYNAME.
    A /dev/input key matching KEYNAME.
"""

import datetime
import os
import subprocess
import time
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.countdown_timer import StartCountdownTimer
from cros.factory.test.event_log import Log

from cros.factory.test.ui_templates import OneSection
from cros.factory.test.utils import StartDaemonThread
from cros.factory.utils import sync_utils

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

_KEY_GPIO = 'gpio:'
_KEY_CROSSYSTEM = 'crossystem:'


class GenericButton(object):
  """Base class for buttons."""

  def IsPressed(self):
    """Returns True the button is pressed, otherwise False."""
    raise NotImplementedError


class EvtestButton(GenericButton):
  """Buttons can be probed by evtest using /dev/input/event*."""

  def __init__(self, event_id, name):
    """Constructor.

    Args:
      event_id: /dev/input/event ID.
      name: A string as key name to be captured by evtest.
    """
    # TODO(hungte) Auto-probe if event_id is None.
    self._event_dev = '/dev/input/event%d' % event_id
    self._name = name

  def IsPressed(self):
    return (subprocess.Popen(['evtest', '--query', self._event_dev, 'EV_KEY',
                              self._name]).wait() != 0)


class GpioButton(GenericButton):
  """GPIO-based buttons."""

  def __init__(self, number, is_active_high):
    """Constructor.

    Args:
      number: An integer for GPIO number.
      is_active_high: Boolean flag for polarity of GPIO ("active" = "pressed").
    """
    gpio_base = '/sys/class/gpio'
    self._value_path = os.path.join(gpio_base, 'gpio%d' % number, 'value')
    if not os.path.exists(self._value_path):
      with open(os.path.join(gpio_base, 'export'), 'w') as f:
        f.write('%d' % number)
    # Exporting new GPIO may cause device busy for a while.
    for unused_counter in xrange(5):
      try:
        with open(os.path.join(gpio_base, 'gpio%d' % number, 'active_low'),
                  'w')as f:
          f.write('%d' % (0 if is_active_high else 1))
        break
      except IOError:
        time.sleep(0.1)

  def IsPressed(self):
    with open(self._value_path) as f:
      return int(f.read()) == 1


class CrossystemButton(GenericButton):
  """A crossystem value that can be mapped as virtual button."""

  def __init__(self, name):
    """Constructor.

    Args:
      name: A string as crossystem parameter that outputs 1 or 0.
    """
    self._name = name

  def IsPressed(self):
    return subprocess.Popen(['crossystem', '%s?1' % self._name]).wait() == 0


class ButtonTest(unittest.TestCase):
  """Button factory test."""
  ARGS = [
      Arg('timeout_secs', int, 'Timeout value for the test.',
          default=_DEFAULT_TIMEOUT),
      Arg('button_key_name', str, 'Button key name for evdev.',
          optional=False),
      Arg('event_id', int, 'Event ID for evdev. None for auto probe.',
          default=None, optional=True),
      Arg('button_name_en', (str, unicode),
          'The name of the button in English.', optional=False),
      Arg('button_name_zh', (str, unicode),
          'The name of the button in Chinese.', optional=False)]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_BUTTON_TEST_DEFAULT_CSS)
    self.template.SetState(_HTML_BUTTON_TEST)
    self.ui.SetHTML(_MSG_PROMPT_PRESS(self.args.button_name_en,
                                      self.args.button_name_zh), id=_ID_PROMPT)

    if self.args.button_key_name.startswith(_KEY_GPIO):
      gpio_num = self.args.button_key_name[len(_KEY_GPIO):]
      self.button = GpioButton(abs(int(gpio_num, 0)), gpio_num.startswith('-'))
    elif self.args.button_key_name.startswith(_KEY_CROSSYSTEM):
      self.button = CrossystemButton(
          self.args.button_key_name[len(_KEY_CROSSYSTEM):])
    else:
      self.button = EvtestButton(self.args.event_id, self.args.button_key_name)

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
    """Returns the time since epoch."""
    return float(datetime.datetime.now().strftime('%s.%f'))

  def ButtonIsPressed(self):
    return self.button.IsPressed()

  def MonitorButtonEvent(self):
    sync_utils.PollForCondition(
        poll_method=self.ButtonIsPressed,
        timeout_secs=self.args.timeout_secs,
        condition_name='WaitForPress')
    self._pressed_sec = self.getCurrentEpochSec()
    self.AskForButtonRelease()
    elapsed_time = self._pressed_sec - self._start_waiting_sec
    sync_utils.PollForCondition(
        poll_method=lambda: not self.ButtonIsPressed(),
        timeout_secs=self.args.timeout_secs - elapsed_time,
        condition_name='WaitForRelease')
    self._released_sec = self.getCurrentEpochSec()
    self.ui.Pass()

  def AskForButtonRelease(self):
    self.ui.SetHTML(_MSG_PROMPT_RELEASE, id=_ID_PROMPT)

  def runTest(self):
    self.ui.Run()
