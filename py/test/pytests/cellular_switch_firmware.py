# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for switching the modem's firmware.

This test will first check current firmware and switch if necessary.
"""

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test.rf import cellular
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


class CellularFirmwareSwitching(unittest.TestCase):
  ARGS = [
      Arg('target', str, 'The firmware name to switch.', optional=False)]

  def runTest(self):
    ui = test_ui.UI()
    ui.Run(blocking=False)
    template = ui_templates.OneSection(ui)
    template.SetState(
        i18n_test_ui.MakeI18nLabelWithClass(
            'Switching firmware to {target!r}<br>',
            'status-info',
            target=self.args.target))
    cellular.SwitchModemFirmware(self.args.target)
