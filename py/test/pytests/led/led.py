# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Uses ectool to control the onboard LED light, and lets either operator
or SMT fixture confirm LED functionality."""

from collections import namedtuple
import logging
import random
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import led as led_module
from cros.factory.test import dut
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.factory_task import (FactoryTask, FactoryTaskManager,
                                            InteractiveFactoryTask)

# The right BFTFixture module is dynamically imported based on args.bft_fixture.
# See setUp() for more detail.
from cros.factory.test.fixture.bft_fixture import (BFTFixtureException,
                                                   CreateBFTFixture,
                                                   TEST_ARG_HELP)


_TEST_TITLE = test_ui.MakeLabel('LED Test', u'LED 测试')

# True to test all colors regardless of failure.
_FAIL_LATER = True
_SHOW_RESULT_SECONDS = 0.5

I18nLabel = namedtuple('I18nLabel', 'en zh')
LEDColor = led_module.LED.Color
LEDIndex = led_module.LED.Index
_COLOR_LABEL = {
    LEDColor.YELLOW: I18nLabel('yellow', u'黃色'),
    LEDColor.GREEN: I18nLabel('green', u'绿色'),
    LEDColor.RED: I18nLabel('red', u'紅色'),
    LEDColor.WHITE: I18nLabel('white', u'白色'),
    LEDColor.BLUE: I18nLabel('blue', u'蓝色'),
    LEDColor.AMBER: I18nLabel('amber', u'琥珀色'),
    LEDColor.OFF: I18nLabel('off', u'关闭')}
_INDEX_LABEL = {
    None: I18nLabel('', ''),
    LEDIndex.POWER: I18nLabel('power', u'电源'),
    LEDIndex.BATTERY: I18nLabel('battery', u'电池'),
    LEDIndex.ADAPTER: I18nLabel('adapter', u'电源适配器')}

# Hash values are: (LED color, readable text color).
_COLOR_CODE = {
    LEDColor.YELLOW: ('#ffff00', 'black'),
    LEDColor.GREEN: ('#00ff00', 'black'),
    LEDColor.RED: ('#ff0000', 'black'),
    LEDColor.WHITE: ('#ffffff', 'black'),
    LEDColor.BLUE: ('#0000ff', 'white'),
    LEDColor.AMBER: ('#ffbf00', 'black'),
    LEDColor.OFF: ('#000000', 'white')}

_JS_OP_RESPONSE = """
function UpdateResult(result) {
  res = $('result');
  if (result) {
    res.innerHTML = '<span class="result-pass">PASS</span>';
  } else {
    res.innerHTML = '<span class="result-fail">FAIL</span>';
  }
}
"""

_HTML_KEY_TEMPLATE = """
<span class="led-btn" style="background-color: %s; color: %s">%d</span>
"""

_HTML_RESULT = (
    '<div class="result-line">' +
    test_ui.MakeLabel('Result: ', u'测试结果：') +
    '<span id="result"></span></div>')

_CSS = """
.sub-title {
  font-size: 200%;
  font-weight: bold;
  line-height: 100px;
}

.led-btn {
  display: inline-block;
  width: 50px;
  height: 50px;
  line-height: 50px;
  font-size: 200%;
  padding: 5px;
  margin: 3px;
  border-radius: 3px;
  font-weight: bold;
  border: 1px solid #7D7D7D;
}

strong {
  background: #ccc;
  padding: 3px 6px;
  margin: 0 2px;
  font-weight: normal;
}

.result-line {
  margin-top: 30px;
}

.result-pass {
  color: green;
  font-weight: bold;
}

.result-fail {
  color: red;
  font-weight: bold;
}
"""


class CheckLEDTask(InteractiveFactoryTask):
  """An InteractiveFactoryTask that asks operator to check LED color.

  Args:
    ui: test_ui.UI instance.
    template: ui_templates.OneSection instance.
    led: dut.led.LED instance to control LED.
    nth: The number of task.
    color: LEDColor to inspect.
    color_label: I18nLabel for inspected color.
    index: Target LED to inspect. None means default LED.
    index_label: I18nLabel for inspected index.
  """

  def __init__(self, ui, template, led, nth, color, color_label,
               index, index_label):
    super(CheckLEDTask, self).__init__(ui)
    self._template = template
    self._led = led
    self._nth = nth
    self._color = color
    self._color_label = color_label
    self._index = index
    self._index_label = index_label

  def Run(self):
    """Lights LED in color and asks operator to verify it."""
    self._InitUI()
    if self._index is None:
      self._led.SetColor(self._color)
    else:
      self._led.SetColor(self._color, led_name=self._index)

  def _InitUI(self):
    """Sets instructions and binds pass/fail key."""
    raise NotImplementedError

  def Cleanup(self):
    """Turns the light off after the test."""
    if self._index is None:
      self._led.SetColor(LEDColor.OFF)
    else:
      self._led.SetColor(LEDColor.OFF, led_name=self._index)


class CheckLEDTaskNormal(CheckLEDTask):
  """Checks for LED colors by asking operator to push ENTER."""

  def __init__(self, ui, template, led, nth, color, color_label,
               index, index_label):
    super(CheckLEDTaskNormal, self).__init__(
        ui, template, led, nth, color, color_label, index, index_label)

  def _InitUI(self):
    if self._color == LEDColor.OFF:
      instruction = test_ui.MakeLabel(
          'If the <strong>%s LED</strong> is <strong>off</strong>, '
          'press ENTER.' % self._index_label.en,
          u'請檢查 <strong>%s LED</strong> 是否 <strong>关掉</strong> 了，'
          u'关掉了請按 ENTER。' % self._index_label.zh)
    else:
      instruction = test_ui.MakeLabel(
          'If the <strong>%s LED</strong> lights up in <strong>%s</strong>, '
          'press ENTER.' % (self._index_label.en, self._color_label.en),
          u'請檢查 <strong>%s LED</strong> 是否亮 <strong>%s</strong>，'
          u'是請按 ENTER。' % (self._index_label.zh, self._color_label.zh))
    self._ui.AppendCSS(_CSS)
    self._template.SetState(instruction)

    self.BindPassFailKeys(fail_later=_FAIL_LATER)


class CheckLEDTaskChallenge(CheckLEDTask):
  """Checks for LED colors interactively.

  Args:
    challenge_colors: The colors to propose for the challenge.
  """

  def __init__(self, ui, template, led, nth, color, color_label,
               index, index_label, challenge_colors):
    super(CheckLEDTaskChallenge, self).__init__(
        ui, template, led, nth, color, color_label, index, index_label)
    self._challenge_colors = challenge_colors

  def _InitUI(self):
    desc = test_ui.MakeLabel(
        '<span class="sub-title">Test %d</span><br />'
        'Please press number key according to the <strong>%s LED</strong> color'
        % (self._nth, self._index_label.en),
        u'<span class="sub-title">测试 %d</span><br />'
        u'请根据 <strong>%s LED</strong> 的颜色按下数字键'
        % (self._nth, self._index_label.zh))

    btn_ui = ''.join([_HTML_KEY_TEMPLATE % (_COLOR_CODE[c] + (j + 1,))
                      for j, c in enumerate(self._challenge_colors)])

    ui = [desc, '<br /><br />', btn_ui, _HTML_RESULT]

    def _PassHook(_):
      self._ui.CallJSFunction('UpdateResult', True)
      time.sleep(_SHOW_RESULT_SECONDS)
      self.Pass()

    def _FailHook(_):
      self._ui.CallJSFunction('UpdateResult', False)
      time.sleep(_SHOW_RESULT_SECONDS)
      self.Fail('LED color incorrect or wrong button pressed')

    target = self._challenge_colors.index(self._color)

    for i, _ in enumerate(self._challenge_colors):
      self._ui.BindKey(str(i + 1), _PassHook if i == target else _FailHook)

    self._ui.AppendCSS(_CSS)
    self._template.SetState(''.join(ui))
    self._ui.RunJS(_JS_OP_RESPONSE)


class FixtureCheckLEDTask(FactoryTask):
  """A FactoryTask that uses fixture to check LED color.

  Args:
    fixture: BFTFixture instance.
    led: dut.led.LED instance to control LED.
    color: LEDColor to inspect.
    color_label: I18nLabel for inspected color.
    index: Target LED to inspect (unused yet).
    index_label: I18nLabel for inspected index (unused yet).
  """

  def __init__(self, fixture, led, color, color_label, index, index_label):
    super(FixtureCheckLEDTask, self).__init__()
    self._fixture = fixture
    self._led = led
    self._color = color
    self._color_label = color_label
    self._index = index
    self._index_label = index_label

  def Run(self):
    """Lights LED in color and asks fixture to verify it."""
    self._led.SetColor(self._color)
    self._CheckFixture()

  def _CheckFixture(self):
    """Asks fixture to check if LED lights self._color.

    It passes the task if fixture replies with the expected value.
    """
    try:
      if self._fixture.IsLEDColor(self._color):
        self.Pass()
      else:
        # Fail later to detect all colors.
        self.Fail('Unable to detect %s LED.' % self._color_label.en,
                  later=_FAIL_LATER)
    except BFTFixtureException:
      logging.exception('Failed to send command to BFT fixture')
      self.Fail('Failed to send command to BFT fixture.')


class LEDTest(unittest.TestCase):
  """Tests if the onboard LED can light up with specified colors."""
  ARGS = [
      Arg('bft_fixture', dict, TEST_ARG_HELP, optional=True),
      Arg('challenge', bool, 'Show random LED sequence and let the operator '
          'select LED number instead of pre-defined sequence.', default=False),
      Arg('colors', (list, tuple),
          'List of colors or (index, color) to test. color must be in '
          'LEDColor or OFF, and index, if specified, must be in LEDIndex.',
          default=[LEDColor.YELLOW, LEDColor.GREEN, LEDColor.RED,
                   LEDColor.OFF]),
      Arg('target_leds', (list, tuple),
          'List of LEDs to test. If specified, it turns off all LEDs first, '
          'and sets them to auto after test.', optional=True),
      Arg('index_i18n', dict,
          'Mapping of (index, zh) translations.  If an index is used without '
          'providing a translation, it will simply show the original index '
          'name.', optional=True, default={})]

  def setUp(self):
    self._dut = dut.Create()
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._task_manager = None
    self._fixture = None
    if self.args.bft_fixture:
      self._fixture = CreateBFTFixture(**self.args.bft_fixture)

    self._SetAllLED(self.args.target_leds, LEDColor.OFF)

  def tearDown(self):
    self._SetAllLED(self.args.target_leds, LEDColor.AUTO)

    if self._fixture:
      self._fixture.Disconnect()

  def runTest(self):
    self._template.SetTitle(_TEST_TITLE)

    tasks = []

    # Shuffle the colors for interactive challenge, so operators can't guess
    # the sequence.
    if self.args.challenge:
      challenge_colors = list(set([x if isinstance(x, str) else x[1]
                                   for x in self.args.colors]))
      random.shuffle(challenge_colors)

    for i, index_color in enumerate(self.args.colors):
      if isinstance(index_color, str):
        color = index_color
        index = None
      else:
        index, color = index_color

      color_label = _COLOR_LABEL[color]
      index_label = self._GetIndexLabel(index)

      if self._fixture:
        tasks.append(FixtureCheckLEDTask(self._fixture, self._dut.led,
                                         color, color_label,
                                         index, index_label))
      elif self.args.challenge:
        tasks.append(CheckLEDTaskChallenge(self._ui, self._template,
                                           self._dut.led, i + 1,
                                           color, color_label,
                                           index, index_label,
                                           challenge_colors))
      else:
        tasks.append(CheckLEDTaskNormal(self._ui, self._template,
                                        self._dut.led, i + 1,
                                        color, color_label,
                                        index, index_label))

    self._task_manager = FactoryTaskManager(self._ui, tasks)
    self._task_manager.Run()

  def _GetIndexLabel(self, index):
    if index in self.args.index_i18n:
      return I18nLabel(index, self.args.index_i18n[index])
    elif index in _INDEX_LABEL:
      return _INDEX_LABEL[index]
    else:
      return I18nLabel(index, index)

  def _SetAllLED(self, leds, color):
    """Sets all LEDs to a given color.

    Args:
      leds: List of LED index. None for default LED.
      color: One of LEDColor.
    """
    if not self._dut.led:
      # Sanity check. It should not happen.
      return

    if not leds:
      self._dut.led.SetColor(color)
      return

    for led in leds:
      self._dut.led.SetColor(color, led_name=led)
