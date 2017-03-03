# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Uses ectool to control the onboard LED light, and lets either operator
or SMT fixture confirm LED functionality."""

import logging
import random
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.device import led as led_module
from cros.factory.test import factory_task
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
# The right BFTFixture module is dynamically imported based on args.bft_fixture.
# See setUp() for more detail.
from cros.factory.test.fixture import bft_fixture
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


_TEST_TITLE = i18n_test_ui.MakeI18nLabel('LED Test')

# True to test all colors regardless of failure.
_FAIL_LATER = True
_SHOW_RESULT_SECONDS = 0.5

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

_SELECT_COLOR_EVENT = 'led-select-color'

_HTML_KEY_TEMPLATE = """
<span class="led-btn" style="background-color: %s; color: %s"
    onclick="window.test.sendTestEvent('%s', %d);">%d</span>
"""

_HTML_RESULT = (
    '<div class="result-line">' +
    i18n_test_ui.MakeI18nLabel('Result: ') +
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


class CheckLEDTask(factory_task.InteractiveFactoryTask):
  """An InteractiveFactoryTask that asks operator to check LED color.

  Args:
    ui: test_ui.UI instance.
    template: ui_templates.OneSection instance.
    led: dut.led.LED instance to control LED.
    nth: The number of task.
    color: LEDColor to inspect.
    color_label: Label for inspected color.
    index: Target LED to inspect. None means default LED.
    index_label: Label for inspected index.
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
      instruction = i18n_test_ui.MakeI18nLabel(
          'If the <strong>{name}</strong> is <strong>off</strong>, '
          'press ENTER.', name=self._index_label)
    else:
      instruction = i18n_test_ui.MakeI18nLabel(
          'If the <strong>{name}</strong> lights up in '
          '<strong>{color}</strong>, press ENTER.',
          name=self._index_label, color=self._color_label)
    self._ui.AppendCSS(_CSS)
    self._template.SetState(instruction)

    self.BindPassFailKeys(fail_later=_FAIL_LATER)


class CheckLEDTaskChallenge(CheckLEDTask):
  """Checks for LED colors interactively.

  Args:
    color_options: The color options for the operator to choose.
  """

  def __init__(self, ui, template, led, nth, color, color_label,
               index, index_label, color_options):
    super(CheckLEDTaskChallenge, self).__init__(
        ui, template, led, nth, color, color_label, index, index_label)
    self._color_options = color_options

  def _InitUI(self):
    desc = i18n_test_ui.MakeI18nLabel(
        '<span class="sub-title">Test {test_id}</span><br>'
        'Please press number key according to the <strong>{name}</strong> '
        'color',
        test_id=self._nth, name=self._index_label)

    btn_ui = ''.join([
        _HTML_KEY_TEMPLATE % (_COLOR_CODE[c] + (_SELECT_COLOR_EVENT, j, j + 1))
        for j, c in enumerate(self._color_options)])

    ui = [desc, '<br><br>', btn_ui, _HTML_RESULT]

    def _Judge(event):
      if event.data == target:
        self._ui.CallJSFunction('UpdateResult', True)
        time.sleep(_SHOW_RESULT_SECONDS)
        self.Pass()
      else:
        self._ui.CallJSFunction('UpdateResult', False)
        time.sleep(_SHOW_RESULT_SECONDS)
        self.Fail('LED color incorrect or wrong button pressed')

    target = self._color_options.index(self._color)

    self._ui.AddEventHandler(_SELECT_COLOR_EVENT, _Judge)

    for i, _ in enumerate(self._color_options):
      self._ui.BindKey(str(i + 1), _Judge, i, virtual_key=False)

    self._ui.AppendCSS(_CSS)
    self._template.SetState(''.join(ui))
    self._ui.RunJS(_JS_OP_RESPONSE)


class FixtureCheckLEDTask(factory_task.FactoryTask):
  """A FactoryTask that uses fixture to check LED color.

  Args:
    fixture: BFTFixture instance.
    led: dut.led.LED instance to control LED.
    color: LEDColor to inspect.
    color_label: Label for inspected color.
    index: Target LED to inspect (unused yet).
    index_label: Label for inspected index (unused yet).
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
        self.Fail('Unable to detect %s LED.' % self._color_label['en-US'],
                  later=_FAIL_LATER)
    except bft_fixture.BFTFixtureException:
      logging.exception('Failed to send command to BFT fixture')
      self.Fail('Failed to send command to BFT fixture.')

  def Cleanup(self):
    """Turns the light off after the test."""
    if self._index is None:
      self._led.SetColor(LEDColor.OFF)
    else:
      self._led.SetColor(LEDColor.OFF, led_name=self._index)


class LEDTest(unittest.TestCase):
  """Tests if the onboard LED can light up with specified colors."""
  ARGS = [
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP, optional=True),
      Arg('challenge', bool, 'Show random LED sequence and let the operator '
          'select LED number instead of pre-defined sequence.', default=False),
      Arg('colors', (list, tuple),
          'List of colors or (index, color) to test. color must be in '
          'LEDColor or OFF, and index, if specified, must be in LEDIndex.',
          default=[LEDColor.YELLOW, LEDColor.GREEN, LEDColor.RED,
                   LEDColor.OFF]),
      Arg('target_leds', (list, tuple),
          'List of LEDs to test. If specified, it turns off all LEDs first, '
          'and sets them to auto after test.', optional=True)]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._task_manager = None
    self._fixture = None
    if self.args.bft_fixture:
      self._fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)

    self._SetAllLED(self.args.target_leds, LEDColor.OFF)

  def tearDown(self):
    self._SetAllLED(self.args.target_leds, LEDColor.AUTO)

    if self._fixture:
      self._fixture.Disconnect()

  def runTest(self):
    self._template.SetTitle(_TEST_TITLE)

    tasks = []
    colors = self.args.colors

    # Shuffle the colors for interactive challenge, so operators can't guess
    # the sequence.
    if self.args.challenge:
      color_options = list(set([x if isinstance(x, str) else x[1]
                                for x in colors]))
      colors = list(colors)
      random.shuffle(colors)

    for i, index_color in enumerate(colors):
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
                                           color_options))
      else:
        tasks.append(CheckLEDTaskNormal(self._ui, self._template,
                                        self._dut.led, i + 1,
                                        color, color_label,
                                        index, index_label))

    self._task_manager = factory_task.FactoryTaskManager(self._ui, tasks)
    self._task_manager.Run()

  def _GetIndexLabel(self, index):
    if index in _INDEX_LABEL:
      return _INDEX_LABEL[index]
    else:
      return _(index)

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
