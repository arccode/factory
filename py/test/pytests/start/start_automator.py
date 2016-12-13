# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test automator for 'start' test."""

import factory_common  # pylint: disable=unused-import
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.e2e_test.automator import Automator, AutomationFunction


class StartAutomator(Automator):
  """The 'start' factory test automator."""
  # pylint: disable=C0322
  pytest_name = 'start'

  @AutomationFunction(automation_mode=AutomationMode.FULL)
  def automatePressSpace(self):
    # Wait for the instruction on UI to show.
    self.uictl.WaitForContent(search_text='Hit SPACE to start testing')
    # Press SPACE key.
    self.uictl.PressKey(self.uictl.KEY_SPACE)
