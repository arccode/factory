# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test automator for 'led' test."""

import factory_common  # pylint: disable=unused-import
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.e2e_test.automator import Automator, AutomationFunction


class LedAutomator(Automator):
  """The 'led' factory test automator."""
  # pylint: disable=C0322
  pytest_name = 'led'

  @AutomationFunction(automation_mode=AutomationMode.FULL,
                      wait_for_factory_test=False)
  def automateSkipLed(self):
    # Simply pass the test.
    self.uictl.WaitForContent(search_text='If the LED lights up')
