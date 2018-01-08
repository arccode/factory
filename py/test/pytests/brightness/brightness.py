# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is a factory test to check the brightness of LCD backlight or LEDs."""

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg


class BrightnessTest(test_ui.TestCaseWithUI):
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
    self.ui.AppendCSS('test-template { font-size: 2em; }')
    self.ui.BindStandardKeys()
    self.ui.SetState(i18n_test_ui.MakeI18nLabel(self.args.msg))
    self.ui.SetState(
        i18n_test_ui.MakeI18nLabel('Press ENTER to pass, or ESC to fail.'),
        append=True)

  def runTest(self):
    """Starts an infinite loop to change brightness."""
    self.ui.StartFailingCountdownTimer(self.args.timeout_secs)

    def _SetLevel():
      while True:
        for level in self.args.levels:
          yield self._SetBrightnessLevel(level)

    self.event_loop.AddTimedIterable(_SetLevel(), self.args.interval_secs)
    self.WaitTaskEnd()

  def _SetBrightnessLevel(self, level):
    raise NotImplementedError
