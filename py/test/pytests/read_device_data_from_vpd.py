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
    Arg('device_data_keys', list,
         ('List of keys for device_data we want to read from RW_VPD.'
          'Each key is a tuple of (prefix, key) meaning that the '
          'pair (key, value) should be added into device_data if there is '
          'a pair (prefix + key, value) in RW_VPD . If key is *, it means '
          'all keys with the prefix should be added.'),
        default=[('factory.device_data.', '*')], optional=True)
  ]

  @staticmethod
  def _MatchKey(matcher, vpd_key):
    prefix, key = matcher
    if key == '*':
      return vpd_key.startswith(prefix)
    else:
      return vpd_key == prefix + key

  def runTest(self):
    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    template.SetState(test_ui.MakeLabel(
        'Reading device data from RW VPD...',
        '正在从 RW VPD 读机器资料...'))

    vpd_data = vpd.rw.GetAll()
    device_data = {}
    for matcher in self.args.device_data_keys:
      for key in vpd_data:
        if self._MatchKey(matcher, key):
          discarded_prefix = matcher[0]
          device_data_key = key[len(discarded_prefix):]
          device_data[device_data_key] = vpd_data[key]
    shopfloor.UpdateDeviceData(device_data)

    factory.get_state_instance().UpdateSkippedTests()
