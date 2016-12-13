# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test automator for 'ext_display' test."""

import factory_common  # pylint: disable=unused-import
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.e2e_test.automator import Automator, AutomationFunction


class ExtDisplayAutomator(Automator):
  """The 'ext_display' factory test automator."""
  # pylint: disable=C0322
  pytest_name = 'ext_display'

  @AutomationFunction(automation_mode=AutomationMode.FULL,
                      wait_for_factory_test=False)
  def automateSkipExtDisplay(self):
    # Simply pass the test.
    self.uictl.WaitForContent(search_text='External Display Test')
