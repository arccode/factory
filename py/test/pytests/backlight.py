# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to test the function of backlight of display panel."""

import logging
import random

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import session
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg

_DEFAULT_ADJUST_LEVEL = 0.05
_DEFAULT_RESET_LEVEL = 0.5


class BacklightTest(test_ui.TestCaseWithUI):
  """Tests the function of backlight of display panel.

  There are two subtests in this test. In each subtest, the test will make
  the screen bighter or darker when space is being pressed.
  During each subtest, pressing esc can reset the brightness.
  Operator needs to answer H for brighter screen and L for darker screen.
  """
  ARGS = [
      Arg('adjust_level', float,
          'How much the brightness level should be adjusted. Max: 1.0',
          default=_DEFAULT_ADJUST_LEVEL),
      Arg('reset_level', float,
          'The brightness level when do reset. Max: 1.0',
          default=_DEFAULT_RESET_LEVEL),
  ]

  def setUp(self):
    """Initializes frontend presentation and properties."""
    self.dut = device_utils.CreateDUTInterface()

    self.sequence = [+1, -1]
    random.shuffle(self.sequence)

    logging.info('testing sequence: %r', self.sequence)
    self.current_level = 0
    self.ResetBrightness()

    self.ui.AppendCSS('test-template { font-size: 2em; }')
    self.ui.SetState(
        i18n_test_ui.MakeI18nLabel(
            'Press Space to change backlight brightness;<br>'
            'Press Esc to reset backlight brightness to original;<br>'
            'After checking, Enter H if pressing Space changes the '
            'backlight to be brighter;<br>'
            'Enter L if pressing Space changes the backlight to be '
            'dimmer.<br>'
            'This test will be executed twice.'))

  def tearDown(self):
    self.ResetBrightness()

  def runTest(self):
    for direction in self.sequence:
      self.ResetBrightness()
      while True:
        key = self.ui.WaitKeysOnce(
            [test_ui.ESCAPE_KEY, test_ui.SPACE_KEY, 'H', 'L'])
        if key == test_ui.ESCAPE_KEY:
          self.ResetBrightness()
        elif key == test_ui.SPACE_KEY:
          self.AdjustBrightness(self.current_level +
                                direction * self.args.adjust_level)
        else:
          correct_key = 'H' if direction == +1 else 'L'
          if key == correct_key:
            session.console.info('Passed for %r', key)
            break
          else:
            self.FailTask('Wrong answer: %r' % key)

  def AdjustBrightness(self, level):
    """Adjust the intensity."""
    level = max(0, min(1, level))
    logging.info('Adjust brightness level to %r', level)
    self.dut.display.SetBacklightBrightness(level)
    self.current_level = level

  def ResetBrightness(self):
    """Resets brightness back to normal value."""
    logging.info('Reset brightness to %r', self.args.reset_level)
    self.AdjustBrightness(self.args.reset_level)
