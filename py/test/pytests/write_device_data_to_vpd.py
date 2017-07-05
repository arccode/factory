# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Writes a subset device data to the RW VPD.

Data is all written as strings.
"""


import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


_MSG_WRITING_VPD = lambda vpd_section: i18n_test_ui.MakeI18nLabel(
    'Writing device data to {vpd_section} VPD...',
    vpd_section=vpd_section.upper())


class CallShopfloor(unittest.TestCase):
  ARGS = [
      Arg('key_map', dict,
          ('Mapping from VPD key to device data key, e.g. {"foo": "bar.baz"} '
           'will write the value of "bar.baz" in device data to VPD with key '
           '"foo". If set to None, write both RO and RW from "device.vpd".'),
          default=None),
      Arg('vpd_section', str,
          'Set to "rw" or "ro" to specify target VPD region (RW_VPD or RO_VPD)'
          'to write. Default to "rw" if key_map is not None.',
          default=None, optional=True),
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)

    key_map = self.args.key_map
    vpd_section = self.args.vpd_section

    data = {
        'ro': {},
        'rw': {},
    }

    if key_map is None:
      data['ro'] = device_data.GetDeviceData(device_data.KEY_VPD_RO, {})
      data['ro'].update(device_data.GetDeviceData('serials', {}))
      data['rw'] = device_data.GetDeviceData(device_data.KEY_VPD_RW, {})
      self.assertEqual(vpd_section, None,
                       'vpd_section must be None when key_map is None.')
    else:
      self.assertIn(vpd_section, data, 'vpd_section (%s) must be in %s' %
                    (vpd_section, data.keys()))
      for k, v in key_map.iteritems():
        data[vpd_section][k] = device_data.GetDeviceData(v, None)

      missing_keys = [k for k, v in data[vpd_section].iteritems() if v is None]
      if missing_keys:
        self.fail('Missing device data keys: %r' % sorted(missing_keys))

    for section, entries in data.iteritems():
      template.SetState(_MSG_WRITING_VPD(section))
      if not entries:
        continue
      # Normalize boolean and integer types to strings.
      output = dict((k, str(v)) for k, v in entries.iteritems())
      vpd = getattr(self.dut.vpd, section)
      vpd.Update(output)
