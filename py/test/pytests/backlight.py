# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Test display backlight.

Description
-----------
This test check if the backlight of display can be adjusted.

The test randomly change the backlight of display to either lower or higher,
and operator should answer the direction of change correctly to pass the test.

Test Procedure
--------------
1. The backlight is reset to ``reset_level``.
2. Operator press space key to adjust the backlight to lower or higher randomly,
   and press escape key to reset the backlight.
3. Operator press 'H' key if the backlight is higher when pressing space key,
   and press 'L' key if it is lower.
4. The test pass if the operator answer correctly two times, and fail if the
   operator answer incorrectly.

Dependency
----------
Device API `display.SetBacklightBrightness`.

Examples
--------
To test display backlight functionality, add this into test list::

  {
    "pytest_name": "backlight"
  }

To test display backlight functionality, and have a smaller change on each
space pressed, add this into test list::

  {
    "pytest_name": "backlight",
    "args": {
      "adjust_level": 0.02
    }
  }
"""

import logging
import random

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg


_DEFAULT_ADJUST_LEVEL = 0.05
_DEFAULT_RESET_LEVEL = 0.5
_DEFAULT_MIN_LEVEL = 0.0


class BacklightTest(test_case.TestCase):
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
      Arg('reset_level', float, 'The brightness level when do reset. Max: 1.0',
          default=_DEFAULT_RESET_LEVEL),
      Arg('min_level', float,
          'The minimal brightness level during the test. Max: 1.0',
          default=_DEFAULT_MIN_LEVEL)
  ]

  def setUp(self):
    """Initializes frontend presentation and properties."""
    self.CheckArgs()
    self.dut = device_utils.CreateDUTInterface()

    self.sequence = [+1, -1]
    random.shuffle(self.sequence)

    logging.info('testing sequence: %r', self.sequence)
    self.current_level = 0
    self.ResetBrightness()

    self.ui.ToggleTemplateClass('font-large', True)
    self.ui.SetState(
        _('Press Space to change backlight brightness;<br>'
          'Press Esc to reset backlight brightness to original;<br>'
          'After checking, Enter H if pressing Space changes the '
          'backlight to be brighter;<br>'
          'Enter L if pressing Space changes the backlight to be '
          'dimmer.<br>'
          'This test will be executed twice.'))

  def CheckArgs(self):
    min_level = self.args.min_level
    if not 0 <= min_level <= 1:
      self.FailTask(f'min_level must between 0 and 1, got: {min_level}')
    reset_level = self.args.reset_level
    if not min_level <= reset_level <= 1:
      self.FailTask(f'reset_level must between min_level: {min_level} '
                    f'and 1, got: {reset_level}')
    adjust_level = self.args.adjust_level
    if not 0 <= adjust_level <= 1:
      self.FailTask(f'adjust_level must between 0 and 1, got: {adjust_level}')

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
          self.FailTask('Wrong answer: %r' % key)

  def AdjustBrightness(self, level):
    """Adjust the intensity."""
    level = max(self.args.min_level, min(1, level))
    logging.info('Adjust brightness level to %r', level)
    self.dut.display.SetBacklightBrightness(level)
    self.current_level = level

  def ResetBrightness(self):
    """Resets brightness back to normal value."""
    logging.info('Reset brightness to %r', self.args.reset_level)
    self.AdjustBrightness(self.args.reset_level)
