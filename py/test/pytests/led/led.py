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

I18nLabel = namedtuple('I18nLabel', 'en zh')
LEDColor = Board.LEDColor
LEDIndex = Board.LEDIndex
_COLOR_LABEL = {
    LEDColor.YELLOW : I18nLabel('yellow', u'黃色'),
    LEDColor.GREEN  : I18nLabel('green', u'绿色'),
    LEDColor.RED    : I18nLabel('red', u'紅色'),
    LEDColor.WHITE  : I18nLabel('white', u'白色'),
    LEDColor.BLUE   : I18nLabel('blue', u'蓝色'),
    LEDColor.OFF    : I18nLabel('off', u'关闭')}
_INDEX_LABEL = {
    None             : I18nLabel('', ''),
    LEDIndex.POWER   : I18nLabel('power ', u'电源 '),
    LEDIndex.BATTERY : I18nLabel('battery ', u'电池 '),
    LEDIndex.ADAPTER : I18nLabel('adapter ', u'电源适配器 ')}


class CheckLEDTask(InteractiveFactoryTask):
  """An InteractiveFactoryTask that ask operator to check LED color.

  Args:
    ui: test_ui.UI instance.
    template: ui_templates.OneSection() instance.
    board: Board instance to control LED.
    color: LEDColor to inspect.
    index: target LED to inspect. None means default LED.
  """

  def __init__(self, ui, template, board, color, index):
    super(CheckLEDTask, self).__init__(ui)
    self._template = template
    self._board = board
    self._color = color
    self._index = index

  def Run(self):
    """Lights LED in color and asks operator to verify it."""
    self._InitUI()
    if self._index is None:
      self._board.SetLEDColor(self._color)
    else:
      self._board.SetLEDColor(self._color, led_name=self._index)

  def _InitUI(self):
    """Sets instructions and binds pass/fail key."""
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
    Arg('colors', (list, tuple),
        'List of colors or (index, color) to test. color must be in '
        'Board.LEDColor or OFF, and index, if specified, must be in '
        'Board.LEDIndex.',
        default=[LEDColor.YELLOW, LEDColor.GREEN, LEDColor.RED, LEDColor.OFF]),
    Arg('target_leds', (list, tuple),
        'List of LEDs to test. If specified, it turns off all LEDs first, '
        'and turns auto after test.',
        optional=True)
  ]

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
    for index_color in self.args.colors:
      if isinstance(index_color, str):
        color = index_color
        index = None
      else:
        index, color = index_color

      if self._fixture:
        tasks.append(FixtureCheckLEDTask(self._fixture, self._board, color,
                                         index))
      else:
        tasks.append(CheckLEDTask(self._ui, self._template, self._board, color,
                                  index))

    self._task_manager = FactoryTaskManager(self._ui, tasks)
    self._task_manager.Run()

  def SetAllLED(self, leds, color):
    """Sets all LEDs to a given color.

    Args:
      leds: list of LED index. None for default LED.
      color: One of Board.LEDColor.
    """
    if not self._board:
      # Sanity check. It shoud not happen.
      return

    if not leds:
      self._board.SetLEDColor(color)
      return

    for led in leds:
      self._board.SetLEDColor(color, led_name=led)
