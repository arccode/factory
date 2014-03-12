# -*- coding=utf-8 -*-
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test automator for 'finalize' test."""

import factory_common  # pylint: disable=W0611
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.e2e_test.automator import Automator, AutomationFunction


class FinalizeAutomator(Automator):
  """The 'finalize' factory test automator."""
  # pylint: disable=C0322
  pytest_name = 'finalize'

  @AutomationFunction(override_dargs=dict(
      allow_force_finalize=['engineer', 'operator'], write_protection=False),
      automation_mode=AutomationMode.FULL)
  def automateFinalize(self):
    # Simply pass the test.
    self.uictl.WaitForContent(
        search_text='Press “f” to force starting finalization procedure.')
    self.uictl.PressKey('F')
