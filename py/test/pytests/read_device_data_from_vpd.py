# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Reads device data from the RW VPD, if present.

Data is all read as strings."""


import unittest


import factory_common  # pylint: disable=W0611
from cros.factory.system import vpd
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg


class CallShopfloor(unittest.TestCase):
  ARGS = [
    Arg('prefix', str,
        ('Prefix to use when reading keys from the VPD. The prefix is '
         'stripped; e.g., if there is a VPD entry for '
         'factory.device_data.foo=bar, then foo=bar is added to device_data.'),
        default='factory.device_data.'),
  ]

  def runTest(self):
    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    template.SetState(test_ui.MakeLabel(
        'Reading device data from RW VPD...',
        '正在从 RW VPD 读机器资料...'))

    vpd_data = vpd.rw.GetAll()
    shopfloor.UpdateDeviceData(
        dict((k[len(self.args.prefix):], v)
             for k, v in vpd_data.iteritems() if k.startswith(
                 self.args.prefix)))
    factory.get_state_instance().UpdateSkippedTests()
