# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Uses ectool to control the onboard LED light, and lets either operator
or SMT fixture confirm LED functionality."""

import logging
import random
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.device import led as led_module
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
# The right BFTFixture module is dynamically imported based on args.bft_fixture.
# See setUp() for more detail.
from cros.factory.test.fixture import bft_fixture
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import type_utils


LEDColor = led_module.LED.Color
LEDIndex = led_module.LED.Index
_COLOR_LABEL = {
    LEDColor.YELLOW: _('yellow'),
    LEDColor.GREEN: _('green'),
    LEDColor.RED: _('red'),
    LEDColor.WHITE: _('white'),
    LEDColor.BLUE: _('blue'),
    LEDColor.AMBER: _('amber'),
    LEDColor.OFF: _('off')}
_INDEX_LABEL = {
    None: _('LED'),
    LEDIndex.POWER: _('power LED'),
    LEDIndex.BATTERY: _('battery LED'),
    LEDIndex.ADAPTER: _('adapter LED')}


class LEDTest(test_ui.TestCaseWithUI):
  """Tests if the onboard LED can light up with specified colors."""
  ARGS = [
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP, default=None),
      Arg('challenge', bool, 'Show random LED sequence and let the operator '
          'select LED number instead of pre-defined sequence.', default=False),
      Arg('colors', list,
          'List of colors or [index, color] to test. color must be in '
          'LEDColor or OFF, and index, if specified, must be in LEDIndex.',
          default=[LEDColor.YELLOW, LEDColor.GREEN, LEDColor.RED,
                   LEDColor.OFF]),
      Arg('target_leds', list,
          'List of LEDs to test. If specified, it turns off all LEDs first, '
          'and sets them to auto after test.', default=None)]

  def setUp(self):
    self._led = device_utils.CreateDUTInterface().led
    self._fixture = None
    if self.args.bft_fixture:
      self._fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)

    self._SetAllLED(LEDColor.OFF)

    # Transform the colors to a list of [led_name, color].
    self.colors = [[None, item] if isinstance(item, basestring) else item
                   for item in self.args.colors]

    # Shuffle the colors for interactive challenge, so operators can't guess
    # the sequence.
    if self.args.challenge:
      random.shuffle(self.colors)

    for test_id, [led_name, color] in enumerate(self.colors, 1):
      cleanup = type_utils.BindFunction(self._TurnOffLED, led_name)
      if self._fixture:
        self.AddTask(
            type_utils.BindFunction(self.RunFixtureTask, led_name, color),
            cleanup=cleanup)
      elif self.args.challenge:
        self.AddTask(
            type_utils.BindFunction(self.RunChallengeTask, test_id, led_name,
                                    color),
            cleanup=cleanup)
      else:
        self.AddTask(
            type_utils.BindFunction(self.RunNormalTask, led_name, color),
            cleanup=cleanup)

  def tearDown(self):
    self._SetAllLED(LEDColor.AUTO)

    if self._fixture:
      self._fixture.Disconnect()

  def RunNormalTask(self, led_name, color):
    """Checks for LED colors by asking operator to push ENTER."""
    self._SetLEDColor(led_name, color)

    led_name_label = self._GetNameI18nLabel(led_name)
    color_label = _COLOR_LABEL[color]
    if color == LEDColor.OFF:
      instruction = i18n_test_ui.MakeI18nLabel(
          'If the <strong>{name}</strong> is <strong>off</strong>, '
          'press ENTER.', name=led_name_label)
    else:
      instruction = i18n_test_ui.MakeI18nLabel(
          'If the <strong>{name}</strong> lights up in '
          '<strong>{color}</strong>, press ENTER.',
          name=led_name_label, color=color_label)
    self.ui.SetState(instruction)
    self.ui.BindStandardKeys()
    self.WaitTaskEnd()

  def _CreateChallengeTaskUI(self, test_id, led_name, color_options):
    """Create the UI of challenge task."""
    def _MakeButton(idx, color):
      return '<span class="led-btn color-{color}">{idx}</span>'.format(
          color=color.lower(), idx=idx)

    led_name_label = self._GetNameI18nLabel(led_name)
    description = i18n_test_ui.MakeI18nLabel(
        '<span class="sub-title">Test {test_id}</span><br>'
        'Please press number key according to the <strong>{name}</strong> '
        'color',
        test_id=test_id, name=led_name_label)
    buttons_ui = '<div>' + ''.join(
        _MakeButton(idx, color)
        for idx, color in enumerate(color_options, 1)) + '</div>'
    result_line = (
        '<div class="result-line">' + i18n_test_ui.MakeI18nLabel('Result: ') +
        '<span id="result"></span></div>')
    return description + '<br>' + buttons_ui + result_line

  def RunChallengeTask(self, test_id, led_name, color):
    """Checks for LED colors interactively."""
    self._SetLEDColor(led_name, color)

    color_options = list(set(color for unused_index, color in self.colors))
    color_options.sort()
    answer = color_options.index(color)

    self.ui.SetState(
        self._CreateChallengeTaskUI(test_id, led_name, color_options))

    keys = [str(i) for i in range(1, len(color_options) + 1)]
    pressed_key = int(self.ui.WaitKeysOnce(keys)) - 1
    if pressed_key == answer:
      self.ui.SetHTML('<span class="result-pass">PASS</span>', id='result')
      time.sleep(0.5)
      self.PassTask()
    else:
      self.ui.SetHTML('<span class="result-fail">FAIL</span>', id='result')
      time.sleep(0.5)
      self.FailTask('correct color for %s is %s but got %s.' %
                    (led_name, color, color_options[pressed_key]))

  def RunFixtureTask(self, led_name, color):
    """Lights LED in color and asks fixture to verify it."""
    self._SetLEDColor(led_name, color)
    try:
      if self._fixture.IsLEDColor(color):
        self.PassTask()
      else:
        # Fail later to detect all colors.
        self.FailTask('Unable to detect %s LED.' % color)
    except bft_fixture.BFTFixtureException:
      logging.exception('Failed to send command to BFT fixture')
      self.FailTask('Failed to send command to BFT fixture.')

  def _SetLEDColor(self, led_name, color):
    """Set LED color for a led."""
    if led_name is None:
      self._led.SetColor(color)
    else:
      self._led.SetColor(color, led_name=led_name)

  def _TurnOffLED(self, led_name):
    """Turn off the target LED."""
    self._SetLEDColor(led_name, LEDColor.OFF)

  def _GetNameI18nLabel(self, led_name):
    return _INDEX_LABEL.get(led_name, _(led_name))

  def _SetAllLED(self, color):
    """Sets all LEDs in target_leds to a given color.

    Args:
      color: One of LEDColor.
    """
    if self.args.target_leds:
      for led in self.args.target_leds:
        self._led.SetColor(color, led_name=led)
    else:
      self._led.SetColor(color)