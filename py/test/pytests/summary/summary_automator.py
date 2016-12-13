# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test automator for 'summary' test."""

import factory_common  # pylint: disable=unused-import
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.e2e_test.automator import Automator, AutomationFunction


class SummaryAutomator(Automator):
  """The 'summary' factory test automator."""
  # pylint: disable=C0322
  pytest_name = 'summary'

  @AutomationFunction(override_dargs=dict(
      disable_input_on_fail=False, pass_without_prompt=False),
                      automation_mode=AutomationMode.FULL)
  def automateSkipSummary(self):
    # Simply pass the test.
    if not self.args.pass_without_prompt:
      self.uictl.WaitForContent(
          search_text='Click or press SPACE to continue')
      self.uictl.PressKey(self.uictl.KEY_SPACE)
