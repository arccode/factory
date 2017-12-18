# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test if the recovery button works properly.

Description
-----------
For Chromebooks or Chromeboxes with a physical recovery button,
this test can be used to make sure the recovery button status
can be fetched properly.

Test Procedure
--------------
1. Press spacebar to start.
2. Press down the recovery button.

If the recovery button works properly, the test passes.
Otherwise, the test will fail after `timeout_secs` seconds.

Dependency
----------
Use `crossystem recoverysw_cur` to get recovery button status.

Examples
--------
To test recovery button with default parameters, add this in test list::

  {
    "pytest_name": "recovery_button"
  }

One can also set the timeout to 100 seconds by::

  {
    "pytest_name": "recovery_button",
    "args": {
      "timeout_secs": 100
    }
  }
"""

import factory_common  # pylint: disable=unused-import
from cros.factory.test import countdown_timer
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils


class RecoveryButtonTest(test_ui.TestCaseWithUI):
  """Tests Recovery Button."""
  ARGS = [
      Arg('timeout_secs', int, 'Timeout to press recovery button.',
          default=10),
      Arg('polling_interval_secs', float,
          'Interval between checking whether recovery buttion is pressed or '
          'not.', default=0.5)]

  def setUp(self):
    self.ui.AppendCSS('test-template { font-size: 2em; }')

  def runTest(self):
    self.ui.SetState(i18n_test_ui.MakeI18nLabel('Hit SPACE to start test...'))
    self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

    self.ui.SetState('<div>' + i18n_test_ui.MakeI18nLabel(
        'Please press recovery button for {secs:.1f} seconds.',
        secs=self.args.polling_interval_secs) + '</div><div id="timer"></div>')
    countdown_timer.StartNewCountdownTimer(
        self, self.args.timeout_secs,
        'timer', lambda: self.FailTask('Recovery button test failed.'))

    while True:
      if process_utils.SpawnOutput(
          ['crossystem', 'recoverysw_cur'], log=True) == '1':
        return
      self.WaitTaskEnd(timeout=self.args.polling_interval_secs)
