# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test automator for 'shutdown' test."""

import logging

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.e2e_test.automator import Automator, AutomationFunction


class ShutdownAutomator(Automator):
  """The 'shutdown' factory test automator."""
  # pylint: disable=C0322
  pytest_name = 'shutdown'

  @AutomationFunction(automation_mode=AutomationMode.FULL,
                      wait_for_factory_test=False)
  def automateSkipHalt(self):
    if self.args.operation == factory.ShutdownStep.HALT:
      # Skip the test right after it is loaded.
      logging.info('Skip halt in full automation mode.')
      self.uictl.WaitForContent(search_text='Shutdown Test')
    else:
      # Continue with reboot operation. The system should reboot before
      # WaitForPass() reaches its timeout.
      self.WaitForPass(timeout_secs=60,
                       msg='System failed to reboot in 60 seconds.')
