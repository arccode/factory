# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Writes a subset device data to the RW VPD.

Data is all written as strings."""


import unittest


import factory_common  # pylint: disable=W0611
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg

_MSG_WRITING_VPD = lambda vpd_section: test_ui.MakeLabel(
    'Writing device data to %s VPD...' % vpd_section.upper(),
    '机器资料正在写入到 %s VPD...' % vpd_section.upper())


class CallShopfloor(unittest.TestCase):
  ARGS = [
      Arg('device_data_keys', list,
          ('List of keys for device_data we want to write into RW_VPD.'
           'Each key is a tuple of (prefix, key) meaning that the pair '
           '(prefix + key, value) should be added into RW_VPD if there is '
           'a pair (key, value) in device_data.')),
      Arg('vpd_section', str,
          'It should be rw or ro which means RW_VPD or RO_VPD to write.',
          default='rw', optional=True),
  ]

  def runTest(self):
    if self.args.vpd_section not in ['ro', 'rw']:
      self.fail('Invalid vpd_section:% r, should be %r or %r.' %
                (self.args.vpd_section, 'ro', 'rw'))

    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    template.SetState(_MSG_WRITING_VPD(self.args.vpd_section))

    device_data = shopfloor.GetDeviceData()
    data_to_write = {}
    for prefix, key in self.args.device_data_keys:
      data_to_write[prefix + key] = device_data.get(key)

    missing_keys = [k for k, v in data_to_write.iteritems() if v is None]
    if missing_keys:
      self.fail('Missing device data keys: %r' % sorted(missing_keys))

    vpd = self.dut.vpd
    getattr(vpd, self.args.vpd_section).Update(
        dict((k, str(v)) for k, v in data_to_write.iteritems()))
