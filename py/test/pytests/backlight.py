# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""A factory test to test the function of backlight of display panel.
"""

import logging
import random
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import dut
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils.arg_utils import Arg

_ID_CONTAINER = 'backlight-test-container'

# The style is in backlight.css
# The layout contains one div for display.
_HTML_BACKLIGHT = """
   <link rel="stylesheet" type="text/css" href="backlight.css">
   <div id="%s">
   </div>\n""" % _ID_CONTAINER
_DEFAULT_ADJUST_LEVEL = 0.05
_DEFAULT_RESET_LEVEL = 0.5


class BacklightTest(unittest.TestCase):
  """Tests the function of backlight of display panel.

  There are two subtests in this test. In each subtest, the test will make
  the screen bighter or darker when space is being pressed.
  During each subtest, pressing esc can reset the brightness.
  Operator needs to answer H for brighter screen and L for darker screen.

  Attributes:
    self.ui: test ui.
    self.template: ui template handling html layout.
    self.sequence: The testing sequence of 'high' and 'low'.
    self.index: The index of current testing.
    self.current_level: The current brightness level.
  """
  ARGS = [
      Arg('adjust_level', float,
          'How much the brightness level should be adjusted. Max: 1.0',
          optional=True, default=_DEFAULT_ADJUST_LEVEL),
      Arg('reset_level', float,
          'The brightness level when do reset. Max: 1.0',
          optional=True, default=_DEFAULT_RESET_LEVEL),
  ]

  def AdjustBrightness(self, level):
    """Adjust the intensity."""
    if level > 1:
      level = 1
    if level < 0:
      level = 0
    logging.info('Adjust brightness level to %r', level)
    self.dut.display.SetBacklightBrightness(level)
    self.current_level = level

  def setUp(self):
    """Initializes frontend presentation and properties."""
    self.dut = dut.Create()
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendHTML(_HTML_BACKLIGHT)
    # Randomly sets the testing sequence.
    self.sequence = ['low', 'high'] if random.randint(0, 1) else ['high', 'low']
    logging.info('testing sequence: %r', self.sequence)
    self.index = 0
    self.current_level = 0
    self.ResetBrightness()
    self.ui.CallJSFunction('setupBacklightTest', _ID_CONTAINER)

  def tearDown(self):
    self.ResetBrightness()

  def runTest(self):
    """Sets the callback function of keys and run the test."""
    self.ui.BindKey(test_ui.ESCAPE_KEY, lambda _: self.ResetBrightness())
    self.ui.BindKey(' ', lambda _: self.OnAdjustBrightness())
    self.ui.BindKey('H', lambda _: self.OnAnswerPressed('high'))
    self.ui.BindKey('L', lambda _: self.OnAnswerPressed('low'))
    self.ui.Run()

  def OnAnswerPressed(self, answer):
    """The call back function for user input.

    Args:
      answer: 'high' or 'low'. The test will fail if the answer is incorrect.
    """
    logging.info('Pressed %r', answer)
    if answer == self.sequence[self.index]:
      factory.console.info('Passed for %r', answer)
      self.index = self.index + 1
      self.ResetBrightness()
      if self.index == len(self.sequence):
        self.ui.Pass()
    else:
      self.ui.Fail('Wrong answer: %r' % answer)

  def OnAdjustBrightness(self):
    """Adjusts the brightness value by self.args.adjust_level."""
    if self.sequence[self.index] == 'high':
      target_level = self.current_level + self.args.adjust_level
    elif self.sequence[self.index] == 'low':
      target_level = self.current_level - self.args.adjust_level
    self.AdjustBrightness(target_level)

  def ResetBrightness(self):
    """Resets brightness back to normal value."""
    logging.info('Reset brightness to %r', self.args.reset_level)
    self.AdjustBrightness(self.args.reset_level)
