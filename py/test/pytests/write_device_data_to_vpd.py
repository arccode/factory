# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Writes a subset device data to the RW VPD.

Data is all written as strings."""


import unittest


import factory_common  # pylint: disable=W0611
from cros.factory.system import vpd
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg


class CallShopfloor(unittest.TestCase):
  ARGS = [
    Arg('keys', (list, tuple), 'Keys to write to the VPD.'),
    Arg('prefix', str, 'Prefix to use when writing keys to the VPD.',
        default='factory.device_data.'),

  ]

  def runTest(self):
    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    template.SetState(test_ui.MakeLabel(
        'Writing device data to RW VPD...',
        '机器资料正在写入到 RW VPD...'))

    device_data = shopfloor.GetDeviceData()
    data_to_write = dict((k, device_data.get(k))
                         for k in self.args.keys)
    missing_keys = [k for k, v in data_to_write.iteritems() if v is None]
    if missing_keys:
      self.fail('Missing device data keys: %r' % sorted(missing_keys))

    vpd.rw.Update(dict((self.args.prefix + k, str(v))
                       for k, v in data_to_write.iteritems()))
