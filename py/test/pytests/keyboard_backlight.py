# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This is a factory test to test keyboard backlight."""

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils import process_utils


_TEST_TITLE = i18n_test_ui.MakeI18nLabel('Keyboard Backlight Test')

_SUBTESTS = (
    (_('If the keyboard backlight lights up, press ENTER. '), '100'),
    (_('If the keyboard backlight is off, press ENTER. '), '0'))


class KeyboardBacklightTest(unittest.TestCase):

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._current = 0

  def NextSubTest(self):
    inst = _SUBTESTS[self._current][0]
    instruction = (i18n_test_ui.MakeI18nLabel(inst) +
                   test_ui.MakePassFailKeyLabel(pass_key=False))
    self._template.SetState(instruction)
    process_utils.Spawn(['ectool', 'pwmsetkblight',
                         _SUBTESTS[self._current][1]], ignore_stdout=True,
                        log_stderr_on_error=True, check_call=True)
    self._current = self._current + 1

  def PassSubtest(self, unused_event):
    if self._current == len(_SUBTESTS):
      self._ui.Pass()
    else:
      self.NextSubTest()
    return True

  def runTest(self):
    """Main entrance of keyboard backlight test."""
    self._template.SetTitle(_TEST_TITLE)
    self._ui.BindKeyJS(test_ui.ENTER_KEY,
                       'test.sendTestEvent("pass_subtest", {});')
    self._ui.BindStandardKeys(bind_pass_keys=False)
    self._ui.AddEventHandler('pass_subtest', self.PassSubtest)
    self.NextSubTest()
    self._ui.Run()
