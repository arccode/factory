# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for switching the modem's firmware.

This test will first check current firmware and switch if necessary.
"""

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test.rf import cellular
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg


class CellularFirmwareSwitching(test_ui.TestCaseWithUI):
  ARGS = [
      Arg('target', str, 'The firmware name to switch.')]

  def runTest(self):
    self.ui.SetState(
        i18n_test_ui.MakeI18nLabel(
            'Switching firmware to {target!r}', target=self.args.target))
    cellular.SwitchModemFirmware(self.args.target)
