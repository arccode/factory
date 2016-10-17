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

import logging
import threading
import time
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.device import device_utils
from cros.factory.test.fixture import bft_fixture
from cros.factory.test import test_ui
from cros.factory.test.countdown_timer import StartCountdownTimer
from cros.factory.test.event_log import Log

from cros.factory.test.ui_templates import OneSection
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils
from cros.factory.utils.arg_utils import Arg

_DEFAULT_TIMEOUT = 30

_MSG_PROMPT_CSS_CLASS = 'button-test-info'
_MSG_PROMPT_PRESS = ('Press the %s button%s', u'按下%s按钮%s')
_MSG_PROMPT_RELEASE = ('Release the button', u'松开按钮')

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

  def __init__(self, dut_instance):
    """Constructor.

    Args:
      dut_instance: the DUT which this button belongs to.
    """
    self._dut = dut_instance

  def IsPressed(self):
    """Returns True the button is pressed, otherwise False."""
    raise NotImplementedError


class EvtestButton(GenericButton):
  """Buttons can be probed by evtest using /dev/input/event*."""

  def __init__(self, dut_instance, event_id, name):
    """Constructor.

    Args:
      dut_instance: the DUT which this button belongs to.
      event_id: /dev/input/event ID.
      name: A string as key name to be captured by evtest.
    """
    super(EvtestButton, self).__init__(dut_instance)
    # TODO(hungte) Auto-probe if event_id is None.
    self._event_dev = '/dev/input/event%d' % event_id
    self._name = name

  def IsPressed(self):
    return (self._dut.Call(['evtest', '--query', self._event_dev, 'EV_KEY',
                            self._name]) != 0)


class GpioButton(GenericButton):
  """GPIO-based buttons."""

  def __init__(self, dut_instance, number, is_active_high):
    """Constructor.

    Args:
      dut_instance: the DUT which this button belongs to.
      :type dut_instance: cros.factory.device.board.DeviceBoard
      number: An integer for GPIO number.
      is_active_high: Boolean flag for polarity of GPIO ("active" = "pressed").
    """
    super(GpioButton, self).__init__(dut_instance)
    gpio_base = '/sys/class/gpio'
    self._value_path = self._dut.path.join(gpio_base, 'gpio%d' % number,
                                           'value')
    if not self._dut.path.exists(self._value_path):
      self._dut.WriteFile(self._dut.path.join(gpio_base, 'export'),
                          '%d' % number)

    # Exporting new GPIO may cause device busy for a while.
    for unused_counter in xrange(5):
      try:
        self._dut.WriteFile(self._dut.path.join(gpio_base, 'gpio%d' % number,
                                                'active_low'),
                            '%d' % (0 if is_active_high else 1))
        break
      except Exception:
        time.sleep(0.1)

  def IsPressed(self):
    return int(self._dut.ReadSpecialFile(self._value_path)) == 1


class CrossystemButton(GenericButton):
  """A crossystem value that can be mapped as virtual button."""

  def __init__(self, dut_instance, name):
    """Constructor.

    Args:
      dut_instance: the DUT which this button belongs to.
      name: A string as crossystem parameter that outputs 1 or 0.
    """
    super(CrossystemButton, self).__init__(dut_instance)
    self._name = name

  def IsPressed(self):
    return self._dut.Call(['crossystem', '%s?1' % self._name]) == 0


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
          'The name of the button in Chinese.', optional=False),
      Arg('repeat_times', int, 'Number of press/release cycles to test',
          default=1),
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP,
          default=None, optional=True),
      Arg('bft_button_name', str, 'Button name for BFT fixture',
          default=None, optional=True),
      ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_BUTTON_TEST_DEFAULT_CSS)
    self.template.SetState(_HTML_BUTTON_TEST)

    if self.args.button_key_name.startswith(_KEY_GPIO):
      gpio_num = self.args.button_key_name[len(_KEY_GPIO):]
      self.button = GpioButton(self.dut, abs(int(gpio_num, 0)),
                               gpio_num.startswith('-'))
    elif self.args.button_key_name.startswith(_KEY_CROSSYSTEM):
      self.button = CrossystemButton(
          self.dut, self.args.button_key_name[len(_KEY_CROSSYSTEM):])
    else:
      self.button = EvtestButton(self.dut, self.args.event_id,
                                 self.args.button_key_name)

    # Timestamps of starting, pressing, and releasing
    # [started, pressed, released, pressed, released, pressed, ...]
    self._action_timestamps = [time.time()]

    if self.args.bft_fixture:
      self._fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)
    else:
      self._fixture = None

    self._disable_timer = threading.Event()
    # Create a thread to monitor button events.
    process_utils.StartDaemonThread(target=self._MonitorButtonEvent)
    # Create a thread to run countdown timer.
    StartCountdownTimer(
        self.args.timeout_secs,
        lambda: self.ui.Fail('Button test failed due to timeout.'),
        self.ui,
        _ID_COUNTDOWN_TIMER,
        disable_event=self._disable_timer)

  def tearDown(self):
    timestamps = self._action_timestamps + [float('inf')]
    for release_index in xrange(2, len(timestamps), 2):
      Log('button_wait_sec',
          time_to_press_sec=(timestamps[release_index - 1] -
                             timestamps[release_index - 2]),
          time_to_release_sec=(timestamps[release_index] -
                               timestamps[release_index - 1]))
    if self._fixture:
      try:
        self._fixture.SimulateButtonRelease(self.args.bft_button_name)
      except:  # pylint: disable=bare-except
        logging.warning('failed to release button', exc_info=True)
      try:
        self._fixture.Disconnect()
      except:  # pylint: disable=bare-except
        logging.warning('disconnection failure', exc_info=True)

  def _PollForCondition(self, poll_method, condition_name):
    elapsed_time = time.time() - self._action_timestamps[0]
    sync_utils.PollForCondition(
        poll_method=poll_method,
        timeout_secs=self.args.timeout_secs - elapsed_time,
        condition_name=condition_name)
    self._action_timestamps.append(time.time())

  def _MonitorButtonEvent(self):
    for done in xrange(self.args.repeat_times):
      if self.args.repeat_times == 1:
        progress = ''
      else:
        progress = ' (%d/%d)' % (done, self.args.repeat_times)
      label = test_ui.MakeLabel(
          _MSG_PROMPT_PRESS[0] % (self.args.button_name_en, progress),
          _MSG_PROMPT_PRESS[1] % (self.args.button_name_zh, progress),
          _MSG_PROMPT_CSS_CLASS)
      self.ui.SetHTML(label, id=_ID_PROMPT)

      if self._fixture:
        self._fixture.SimulateButtonPress(self.args.bft_button_name, 0)

      self._PollForCondition(self.button.IsPressed, 'WaitForPress')
      label = test_ui.MakeLabel(_MSG_PROMPT_RELEASE[0],
                                _MSG_PROMPT_RELEASE[1],
                                _MSG_PROMPT_CSS_CLASS)
      self.ui.SetHTML(label, id=_ID_PROMPT)

      if self._fixture:
        self._fixture.SimulateButtonRelease(self.args.bft_button_name)

      self._PollForCondition(lambda: not self.button.IsPressed(),
                             'WaitForRelease')
    self._disable_timer.set()
    self.ui.Pass()

  def runTest(self):
    self.ui.Run()
