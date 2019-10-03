# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This is a factory test to test keyboard backlight."""

from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils import process_utils


_SUBTESTS = (
    (_('If the keyboard backlight lights up, press ENTER. '), '100'),
    (_('If the keyboard backlight is off, press ENTER. '), '0'))


class KeyboardBacklightTest(test_case.TestCase):
  def setUp(self):
    for instruction, level in _SUBTESTS:
      self.AddTask(self.RunTask, instruction, level)

  def RunTask(self, instruction, level):
    self.ui.BindStandardKeys()
    self.ui.SetState([instruction, test_ui.FAIL_KEY_LABEL])
    process_utils.Spawn(
        ['ectool', 'pwmsetkblight', level],
        ignore_stdout=True, log_stderr_on_error=True, check_call=True)
    self.WaitTaskEnd()
