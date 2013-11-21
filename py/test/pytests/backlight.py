# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""
A factory test to test the function of backlight of display panel.
"""

import logging
import random
import unittest
from collections import namedtuple

from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection

_ID_CONTAINER = 'backlight-test-container'

# The style is in backlight.css
# The layout contains one div for display.
_HTML_BACKLIGHT = """
   <link rel="stylesheet" type="text/css" href="backlight.css">
   <div id="%s">
   </div>\n"""  % _ID_CONTAINER
_ADJUST_STEP = 10

BrightnessSetting = namedtuple('BrightnessSetting',
                               ['lowest', 'normal', 'highest'])

class BacklightTest(unittest.TestCase):
  """Tests the function of backlight of display panel.

  There are two subtests in this test. In each subtest, the test will make
  the screen bighter or darker when space is being pressed.
  During each subtest, pressing esc can reset the brightness.
  Operator needs to answer H for brighter screen and L for darker screen.

  Attributes:
    self.ui: test ui.
    self.template: ui template handling html layout.
    self.brightness_setting: The BrightnessSetting containing brightness value
        for lowest, normal, highest.
    self.sequence: The testing sequence of 'high' and 'low'.
    self.index: The index of current testing.
    self.current_brightness: The current brightness.
  """
  ARGS = [
    Arg('brightness_path', str, 'The field under sysfs to control brightness',
        optional=False),
    Arg('brightness', tuple, 'Brightness value (lowest, normal, highest)',
        optional=True, default=(10, 100, 250)),
  ]

  def AdjustBrightness(self, value):
    """Adjust the intensity by writing targeting value to sysfs.

    Args:
      value: The targeted brightness value.
    """
    with open(self.args.brightness_path, 'w') as f:
      try:
        f.write('%d' % value)
      except IOError:
        self.ui.Fail('Can not write %r into brightness. '
                     'Maybe the limit is wrong' % value)
    self.current_brightness = value

  def setUp(self):
    """Initializes frontend presentation and properties."""
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendHTML(_HTML_BACKLIGHT)
    self.brightness_setting = BrightnessSetting(*self.args.brightness)
    self.CheckMaxBrightness()
    # Randomly sets the testing sequence.
    self.sequence = ['low', 'high'] if random.randint(0, 1) else ['high', 'low']
    logging.info('testing sequence: %r', self.sequence)
    self.index = 0
    self.current_brightness = 0
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

  def CheckMaxBrightness(self):
    """Checks maximum brightness value set from args.

    Checks max_brightness under sysfs for maximum brightness.
    If that value is lower than the value set from args, use that
    value instead.
    """
    with open(self.args.brightness_path.replace(
        'brightness', 'max_brightness')) as f:
      max_brightness = int(f.read())
      if self.brightness_setting.highest > max_brightness:
        logging.warning('highest brightness %r is larger than'
            'max_brightness %r under sysfs. Use sysfs value instead',
            self.brightness_setting.highest, max_brightness)
        # pylint: disable=W0212
        self.brightness_setting = self.brightness_setting._replace(
            highest = max_brightness)
        logging.info('New brightness_setting: %r', self.brightness_setting)

  def OnAdjustBrightness(self):
    """Adjusts the brightness value by _ADJUST_STEP."""
    target_brightness = self.current_brightness
    if (self.sequence[self.index] == 'high' and
        (self.current_brightness + _ADJUST_STEP <
         self.brightness_setting.highest)):
      target_brightness = self.current_brightness + _ADJUST_STEP
    elif (self.sequence[self.index] == 'low' and
          (self.current_brightness - _ADJUST_STEP >
           self.brightness_setting.lowest)):
      target_brightness = self.current_brightness - _ADJUST_STEP
    self.AdjustBrightness(target_brightness)
    logging.info('Adjust brightness to %r', target_brightness)

  def ResetBrightness(self):
    """Resets brightness back to normal value."""
    self.AdjustBrightness(self.brightness_setting.normal)
    logging.info('Reset brightness to %r', self.brightness_setting.normal)
