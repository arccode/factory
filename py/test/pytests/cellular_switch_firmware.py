# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for switching the modem's firmware.

This test will first check current firmware and switch if necessary.
"""

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.rf import cellular
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg


class CellularFirmwareSwitching(unittest.TestCase):
  ARGS = [
    Arg('target', str, 'The firmware name to switch.', optional=False)]

  def runTest(self):
    ui = test_ui.UI()
    ui.Run(blocking=False)
    template = ui_templates.OneSection(ui)
    template.SetState(test_ui.MakeLabel(
        'Switching firmware to %r<br>' % self.args.target,
        '切换数据机至%r韧体' % self.args.target,
        'status-info'))
    cellular.SwitchModemFirmware(self.args.target)
