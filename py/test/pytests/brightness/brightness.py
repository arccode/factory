# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is a factory test to check the brightness of LCD backlight or LEDs."""

from cros.factory.device import device_utils
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg


class BrightnessTest(test_case.TestCase):
  ARGS = [
      i18n_arg_utils.I18nArg('msg', 'Message HTML'),
      Arg('timeout_secs', int, 'Timeout value for the test in seconds.',
          default=10),
      Arg('levels', list, 'A sequence of brightness levels.'),
      Arg('interval_secs', (int, float),
          'Time for each brightness level in seconds.')
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui.ToggleTemplateClass('font-large', True)
    self.ui.BindStandardKeys()
    self.ui.SetState([self.args.msg, test_ui.PASS_FAIL_KEY_LABEL])

  def runTest(self):
    """Starts an infinite loop to change brightness."""
    self.ui.StartFailingCountdownTimer(self.args.timeout_secs)

    while True:
      for level in self.args.levels:
        self._SetBrightnessLevel(level)
        self.Sleep(self.args.interval_secs)

  def _SetBrightnessLevel(self, level):
    raise NotImplementedError
