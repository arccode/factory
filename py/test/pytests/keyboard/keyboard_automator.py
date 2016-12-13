# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test automator for 'keyboard' test."""

import factory_common  # pylint: disable=unused-import
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.e2e_test.automator import Automator, AutomationFunction


class KeyboardAutomator(Automator):
  """The 'keyboard' factory test automator."""
  # pylint: disable=C0322
  pytest_name = 'keyboard'

  @AutomationFunction(automation_mode=AutomationMode.FULL,
                      wait_for_factory_test=False)
  def automateSkipKeyboard(self):
    # Simply pass the test.
    self.uictl.WaitForContent(search_text='Keyboard')
