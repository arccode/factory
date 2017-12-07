# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Verifies physical developer switch can be toggled and end in right state."""

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils

_TEST_PAGE_CSS = """
.on {
  color: green;
}
.off {
  color: red;
}
"""


class DeveloperSwitchTest(test_ui.TestCaseWithUI):
  ARGS = [
      Arg('end_state', bool,
          'The state when leaving test. True as enabled and False as disabled.',
          default=True),
      Arg('timeout_secs', int, 'Time out value in seconds.',
          default=(60 * 60))
  ]

  def setUp(self):
    self.ui.AppendCSS(_TEST_PAGE_CSS)

  def runTest(self):
    initial_state = self.GetState()
    timeout_secs = self.args.timeout_secs
    self.UpdateUI(initial_state)

    sync_utils.WaitFor(lambda: self.GetState() != initial_state, timeout_secs)
    self.UpdateUI(not initial_state)

    sync_utils.WaitFor(lambda: self.GetState() == initial_state, timeout_secs)
    self.UpdateUI(initial_state)

    # Flip again if state is not end_state
    sync_utils.WaitFor(lambda: self.GetState() != int(self.args.end_state),
                       timeout_secs)

  def GetState(self):
    # This will be called so many times so we don't want to be logged.
    return int(process_utils.SpawnOutput(
        ['crossystem', 'devsw_cur'], log=False, check_output=True))

  def UpdateUI(self, state):
    if state:
      self.ui.SetState(
          i18n_test_ui.MakeI18nLabel(
              'Please turn <b class="off">OFF</b> Developer Switch.'))
      self.ui.SetInstruction(
          i18n_test_ui.MakeI18nLabel(
              'Develop switch is currently <b class="on">ON</b>.'))
    else:
      self.ui.SetState(
          i18n_test_ui.MakeI18nLabel(
              'Please turn <b class="on">ON</b> Developer Switch.'))
      self.ui.SetInstruction(
          i18n_test_ui.MakeI18nLabel(
              'Develop switch is currently <b class="off">OFF</b>.'))
