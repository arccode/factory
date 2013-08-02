# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests onboard LED.

It uses ectool to control onboard LED light and let either operator
or SMT fixture to determine if the LED functions well.

dargs:
  bft_fixture: (optional) {class_name: BFTFixture's import path + module name
                           params: a dict of params for BFTFixture's Init()}.
      Default None means no BFT fixture is used.
"""

from collections import namedtuple
import logging
import unittest

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
                                                   CreateBFTFixture)


_TEST_TITLE = test_ui.MakeLabel('LED Test', u'LED 测试')

# True to test all colors regardless of failure.
_FAIL_LATER = True

I18nLabel = namedtuple('I18nLabel', 'en zh')
LEDColor = Board.LEDColor
_COLOR_LABEL = {
    LEDColor.YELLOW : I18nLabel('yellow', u'黃色'),
    LEDColor.GREEN  : I18nLabel('green', u'绿色'),
    LEDColor.RED    : I18nLabel('red', u'紅色'),
    LEDColor.OFF    : I18nLabel('off', u'关闭')}


class CheckLEDTask(InteractiveFactoryTask):
  """An InteractiveFactoryTask that ask operator to check LED color.

  Args:
    ui: test_ui.UI instance.
    template: ui_templates.OneSection() instance.
    board: Board instance to control LED.
    color: LEDColor to inspect.
  """

  def __init__(self, ui, template, board, color):
    super(CheckLEDTask, self).__init__(ui)
    self._template = template
    self._board = board
    self._color = color

  def Run(self):
    """Lights LED in color and asks operator to verify it."""
    self._InitUI()
    self._board.SetLEDColor(self._color)

  def _InitUI(self):
    """Sets instructions and binds pass/fail key."""
    if self._color == LEDColor.OFF:
      instruction = test_ui.MakeLabel(
          'If the LED is off, press ENTER.',
          u'請檢查 LED 是否关掉了，关掉了請按 ENTER。')
    else:
      color_label = _COLOR_LABEL[self._color]
      instruction = test_ui.MakeLabel(
          'If the LED lights up in %s, press ENTER.' % color_label.en,
          u'請檢查 LED 是否亮%s，是請按 ENTER。' % color_label.zh)
    self._template.SetState(instruction)

    self.BindPassFailKeys(fail_later=_FAIL_LATER)


class FixtureCheckLEDTask(FactoryTask):
  """A FactoryTask that uses fixture to check LED color.

  Args:
    fixture: BFTFixture instance.
    board: Board instance to control LED.
    color: LEDColor to inspect.
  """

  def __init__(self, fixture, board, color):
    super(FixtureCheckLEDTask, self).__init__()
    self._fixture = fixture
    self._board = board
    self._color = color

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
    Arg('bft_fixture', dict,
        '{class_name: BFTFixture\'s import path + module name\n'
        ' params: a dict of params for BFTFixture\'s Init()}.\n'
        'Default None means no BFT fixture is used.',
        default=None, optional=True),
    Arg('colors', (list, tuple),
        'List of colors to test, must be one of YELLOW, GREEN, RED, OFF.',
        default=[LEDColor.YELLOW, LEDColor.GREEN, LEDColor.RED, LEDColor.OFF]),
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

    _VALID_COLOR = set([LEDColor.YELLOW, LEDColor.GREEN, LEDColor.RED,
                        LEDColor.OFF])
    for color in self.args.colors:
      if color not in _VALID_COLOR:
        self.fail('Invalid color %s' % color)

  def tearDown(self):
    if self._board:
      self._board.SetLEDColor(LEDColor.AUTO)
    if self._fixture:
      self._fixture.Disconnect()

  def runTest(self):
    self._template.SetTitle(_TEST_TITLE)

    tasks = []
    for color in self.args.colors:
      if self._fixture:
        tasks.append(FixtureCheckLEDTask(self._fixture, self._board, color))
      else:
        tasks.append(CheckLEDTask(self._ui, self._template, self._board, color))

    self._task_manager = FactoryTaskManager(self._ui, tasks)
    self._task_manager.Run()
