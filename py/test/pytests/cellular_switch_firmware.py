# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for switching the modem's firmware.

This test will first check current firmware and switch if necessary.
"""

from cros.factory.test.i18n import _
from cros.factory.test.rf import cellular
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg


class CellularFirmwareSwitching(test_case.TestCase):
  ARGS = [
      Arg('target', str, 'The firmware name to switch.')]

  def runTest(self):
    self.ui.SetState(
        _('Switching firmware to {target!r}', target=self.args.target))
    cellular.SwitchModemFirmware(self.args.target)
