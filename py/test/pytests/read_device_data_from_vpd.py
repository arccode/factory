# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Reads device data from the RW VPD, if present.

Data is all read as strings."""


import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


_MSG_READING_VPD = lambda vpd_section: i18n_test_ui.MakeI18nLabel(
    'Reading device data from {vpd_section} VPD...',
    vpd_section=vpd_section.upper())


class ReadDeviceDataFromVPD(unittest.TestCase):
  ARGS = [
      Arg('key_map', dict,
          ('Mapping from VPD key to device data key.  For example, '
           '{"foo": "bar.baz"} will read value of "foo" from VPD, and '
           'set device data "bar.baz" to that value.  If VPD key ends with '
           '"*", then all keys with the prefix will be added to device data '
           '(In this case, device data key will be treated as a prefix as '
           'well).  For example, {"foo.*": "bar"} will write all VPD values '
           'with key starts with "foo" to device data, and change the prefix '
           '"foo" to "bar"'),
          default={'factory.device_data.*': ''}, optional=True),
      Arg('vpd_section', str,
          'It should be rw or ro which means RW_VPD or RO_VPD to read.',
          default='rw', optional=True),
  ]

  @staticmethod
  def _MatchKey(rule, vpd_key):
    expected_key = rule[0]
    if expected_key.endswith('*'):
      return vpd_key.startswith(expected_key[:-1])
    else:
      return vpd_key == expected_key

  @staticmethod
  def _DeriveDeviceDataKey(rule, vpd_key):
    expected_key = rule[0]
    if not expected_key.endswith('*'):
      return rule[1]

    # remove the prefix
    vpd_key = vpd_key[len(expected_key[:-1]):]

    # prepend new prefix
    return device_data.JoinKeys(rule[1], vpd_key)

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    if self.args.vpd_section not in ['ro', 'rw']:
      self.fail('Invalid vpd_section: %r, should be %r or %r.' %
                (self.args.vpd_section, 'ro', 'rw'))

    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    template.SetState(_MSG_READING_VPD(self.args.vpd_section))

    vpd_data = getattr(self.dut.vpd, self.args.vpd_section).GetAll()
    self.UpdateDeviceData(self.args.key_map, vpd_data)

  def UpdateDeviceData(self, key_map, vpd_data):
    data = {}
    for rule in key_map.iteritems():
      for vpd_key in vpd_data:
        if self._MatchKey(rule, vpd_key):
          data_key = self._DeriveDeviceDataKey(rule, vpd_key)
          if vpd_data[vpd_key].upper() in ['TRUE', 'FALSE']:
            data[data_key] = (vpd_data[vpd_key].upper() == 'TRUE')
          else:
            data[data_key] = vpd_data[vpd_key]
    device_data.UpdateDeviceData(data)
