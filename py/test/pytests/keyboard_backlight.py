# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This is a factory test to test keyboard backlight."""

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


_SUBTESTS = (
    (_('If the keyboard backlight lights up, press ENTER. '), '100'),
    (_('If the keyboard backlight is off, press ENTER. '), '0'))


class KeyboardBacklightTest(test_ui.TestCaseWithUI):
  def setUp(self):
    for instruction, level in _SUBTESTS:
      self.AddTask(type_utils.BindFunction(self.RunTask, instruction, level))

  def RunTask(self, instruction, level):
    self.ui.BindStandardKeys()
    self.template.SetState(
        i18n_test_ui.MakeI18nLabel(instruction) + test_ui.FAIL_KEY_LABEL)
    process_utils.Spawn(
        ['ectool', 'pwmsetkblight', level],
        ignore_stdout=True, log_stderr_on_error=True, check_call=True)
    self.WaitTaskEnd()
