# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Uses ectool to control the onboard LED light, and lets either operator
or SMT fixture confirm LED functionality.
"""

from collections import namedtuple
import logging
import random
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory import system
from cros.factory.system.board import Board
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
LEDColor = Board.LEDColor
LEDIndex = Board.LEDIndex
_COLOR_LABEL = {
    LEDColor.YELLOW: I18nLabel('yellow', u'黃色'),
    LEDColor.GREEN: I18nLabel('green', u'绿色'),
    LEDColor.RED: I18nLabel('red', u'紅色'),
    LEDColor.WHITE: I18nLabel('white', u'白色'),
    LEDColor.BLUE: I18nLabel('blue', u'蓝色'),
    LEDColor.OFF: I18nLabel('off', u'关闭')}
_INDEX_LABEL = {
    None: I18nLabel('', ''),
    LEDIndex.POWER: I18nLabel('power ', u'电源 '),
    LEDIndex.BATTERY: I18nLabel('battery ', u'电池 '),
    LEDIndex.ADAPTER: I18nLabel('adapter ', u'电源适配器 ')}

_COLOR_CODE = {
    LEDColor.YELLOW: ('#ffff00', 'black'),
    LEDColor.GREEN: ('#00ff00', 'black'),
    LEDColor.RED: ('#ff0000', 'black'),
    LEDColor.WHITE: ('#ffffff', 'black'),
    LEDColor.BLUE: ('#0000ff', 'white'),
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
    test_ui.MakeLabel("Result: ", u"测试结果: ") +
    '<span id="result"></span></div>')

_CSS_ITERACTIVE = """
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
  """An InteractiveFactoryTask that ask operator to check LED color.

  Args:
    ui: test_ui.UI instance.
    template: ui_templates.OneSection() instance.
    board: Board instance to control LED.
    nth: The number of task.
    color: LEDColor to inspect.
    index: Target LED to inspect. None means default LED.
    challenge: Whether this is a challenge test or not.
    colors: The sequence of LEDColor in arg.colors.
  """

  def __init__(self, ui, template, board, nth, color, index, challenge=False,
               colors=None):
    super(CheckLEDTask, self).__init__(ui)
    self._template = template
    self._board = board
    self._nth = nth
    self._color = color
    self._index = index
    self._challenge = challenge
    self._colors = colors

  def Run(self):
    """Lights LED in color and asks operator to verify it."""
    self._InitUI()
    if self._index is None:
      self._board.SetLEDColor(self._color)
    else:
      self._board.SetLEDColor(self._color, led_name=self._index)

  def _InitUI(self):
    """Sets instructions and binds pass/fail key."""
    if not self._challenge:
      self._InitUINormal()
    else:
      self._InitUIChallange()

  def _InitUINormal(self):
    index_label = _INDEX_LABEL[self._index]
    if self._color == LEDColor.OFF:
      instruction = test_ui.MakeLabel(
          'If the %sLED is off, press ENTER.' % index_label.en,
          u'請檢查 %sLED 是否关掉了，关掉了請按 ENTER。' % index_label.zh)
    else:
      color_label = _COLOR_LABEL[self._color]
      instruction = test_ui.MakeLabel(
          'If the %sLED lights up in %s, press ENTER.' % (index_label.en,
                                                          color_label.en),
          u'請檢查 %sLED 是否亮%s，是請按 ENTER。' % (index_label.zh,
                                           color_label.zh))
    self._template.SetState(instruction)

    self.BindPassFailKeys(fail_later=_FAIL_LATER)

  def _InitUIChallange(self):
    index_label = _INDEX_LABEL[self._index]

    desc = test_ui.MakeLabel(
        '<span class="sub-title">Test %d</span><br />'
        'Please press number key according to the %sLED color'
        % (self._nth, index_label.en),
        u'<span class="sub-title">测试 %d</span><br />'
        u'请根据 %sLED 的颜色按下数字键' % (self._nth, index_label.zh))

    btn_ui = ''.join([_HTML_KEY_TEMPLATE % (_COLOR_CODE[c] + (j + 1,))
                      for j, c in enumerate(self._colors)])

    ui = [desc, '<br /><br />', btn_ui, _HTML_RESULT]

    def Pass(_):
      self._ui.CallJSFunction("UpdateResult", True)
      time.sleep(_SHOW_RESULT_SECONDS)
      self.Pass()

    def Fail(_):
      self._ui.CallJSFunction("UpdateResult", False)
      time.sleep(_SHOW_RESULT_SECONDS)
      self.Fail('LED color incorrect or wrong button pressed')

    target = self._colors.index(self._color)

    for i, _ in enumerate(self._colors):
      self._ui.BindKey(str(i + 1), Pass if i == target else Fail)

    self._ui.AppendCSS(_CSS_ITERACTIVE)
    self._template.SetState(''.join(ui))
    self._ui.RunJS(_JS_OP_RESPONSE)


class FixtureCheckLEDTask(FactoryTask):
  """A FactoryTask that uses fixture to check LED color.

  Args:
    fixture: BFTFixture instance.
    board: Board instance to control LED.
    color: LEDColor to inspect.
    index: target LED to inspect (unused yet).
  """

  def __init__(self, fixture, board, color, index):
    super(FixtureCheckLEDTask, self).__init__()
    self._fixture = fixture
    self._board = board
    self._color = color
    self._index = index

  def Run(self):
    """Lights LED in color and asks fixture to verify it."""
    self._board.SetLEDColor(self._color)
    self._CheckFixture()

  def _CheckFixture(self):
    """Asks fixture to check if LED lights self._color.

    It passes the task if fixture replies the expected value.
    """
    try:
      if self._fixture.IsLEDColor(self._color):
        self.Pass()
      else:
        # Fail later to detect all colors.
        self.Fail('Unable to detect %s LED.' % _COLOR_LABEL[self._color].en,
                  later=_FAIL_LATER)
    except BFTFixtureException:
      logging.exception('Failed to send command to BFT fixture')
      self.Fail('Failed to send command to BFT fixture.')


class LEDTest(unittest.TestCase):
  """Tests if the onboard LED can light yellow/green/red colors."""
  ARGS = [
      Arg('bft_fixture', dict, TEST_ARG_HELP, optional=True),
      Arg('challenge', bool, 'Show random LED sequence and let the operator '
          'select LED number instead of pre-defined sequence.', default=False),
      Arg(
          'colors', (list, tuple),
          'List of colors or (index, color) to test. color must be in '
          'Board.LEDColor or OFF, and index, if specified, must be in '
          'Board.LEDIndex.',
          default=[LEDColor.YELLOW, LEDColor.GREEN, LEDColor.RED,
                   LEDColor.OFF]),
      Arg(
          'target_leds', (list, tuple),
          'List of LEDs to test. If specified, it turns off all LEDs first, '
          'and turns auto after test.', optional=True)]

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._task_manager = None
    self._fixture = None
    self._board = None
    self._board = system.GetBoard()
    if self.args.bft_fixture:
      self._fixture = CreateBFTFixture(**self.args.bft_fixture)

    self.SetAllLED(self.args.target_leds, LEDColor.OFF)

  def tearDown(self):
    self.SetAllLED(self.args.target_leds, LEDColor.AUTO)

    if self._fixture:
      self._fixture.Disconnect()

  def runTest(self):
    self._template.SetTitle(_TEST_TITLE)

    tasks = []
    colors = [x if isinstance(x, str) else x[1] for x in self.args.colors]

    # Shuffle the colors so operators can't guess the sequence.
    if self.args.challenge:
      random.shuffle(self.args.colors)

    for i, index_color in enumerate(self.args.colors):
      if isinstance(index_color, str):
        color = index_color
        index = None
      else:
        index, color = index_color

      if self._fixture:
        tasks.append(FixtureCheckLEDTask(self._fixture, self._board, color,
                                         index))
      else:
        tasks.append(CheckLEDTask(self._ui, self._template, self._board, i + 1,
                                  color, index, self.args.challenge, colors))

    self._task_manager = FactoryTaskManager(self._ui, tasks)
    self._task_manager.Run()

  def SetAllLED(self, leds, color):
    """Sets all LEDs to a given color.

    Args:
      leds: list of LED index. None for default LED.
      color: One of Board.LEDColor.
    """
    if not self._board:
      # Sanity check. It should not happen.
      return

    if not leds:
      self._board.SetLEDColor(color)
      return

    for led in leds:
      self._board.SetLEDColor(color, led_name=led)
