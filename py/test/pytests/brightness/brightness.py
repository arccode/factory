# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is a factory test to check the brightness of LCD backlight or LEDs."""

import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import countdown_timer
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


_MSG_CSS_CLASS = 'brightness-test-info'
_MSG_PASS_FAIL_PROMPT = i18n_test_ui.MakeI18nLabelWithClass(
    '<br>Press ENTER to pass, or ESC to fail.', _MSG_CSS_CLASS)

_ID_PROMPT = 'brightness-test-prompt'
_ID_COUNTDOWN_TIMER = 'brightness-test-timer'

_HTML_BRIGHTNESS_TEST = (
    '<div id="%s"></div>\n<div id="%s" class="%s"></div>\n' %
    (_ID_PROMPT, _ID_COUNTDOWN_TIMER, _MSG_CSS_CLASS))
_BRIGHTNESS_TEST_DEFAULT_CSS = '.brightness-test-info { font-size: 2em; }'


class BrightnessTest(unittest.TestCase):
  ARGS = [
      i18n_arg_utils.I18nArg('msg', 'Message HTML'),
      Arg('timeout_secs', int, 'Timeout value for the test in seconds.',
          default=10),
      Arg('levels', (tuple, list), 'A sequence of brightness levels.'),
      Arg('interval_secs', (int, float),
          'Time for each brightness level in seconds.')
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_BRIGHTNESS_TEST_DEFAULT_CSS)
    self.ui.BindStandardKeys()
    self.template.SetState(_HTML_BRIGHTNESS_TEST)
    self.ui.SetHTML(i18n_test_ui.MakeI18nLabelWithClass(
        self.args.msg, _MSG_CSS_CLASS), id=_ID_PROMPT)
    self.ui.SetHTML(_MSG_PASS_FAIL_PROMPT, append=True, id=_ID_PROMPT)

  def runTest(self):
    self.ui.RunInBackground(self._BrightnessChangeLoop)
    countdown_timer.StartCountdownTimer(
        self.args.timeout_secs,
        lambda: self.ui.Fail('Brightness test failed due to timeout.'),
        self.ui,
        _ID_COUNTDOWN_TIMER)
    self.ui.Run()

  def tearDown(self):
    raise NotImplementedError

  def _SetBrightnessLevel(self, level):
    raise NotImplementedError

  def _BrightnessChangeLoop(self):
    """Starts an infinite loop to change brightness."""
    while True:
      for level in self.args.levels:
        self._SetBrightnessLevel(level)
        time.sleep(self.args.interval_secs)
