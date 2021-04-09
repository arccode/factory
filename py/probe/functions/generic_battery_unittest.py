#!/usr/bin/env python3
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import textwrap
import unittest
from unittest import mock

from cros.factory.probe.functions import generic_battery
from cros.factory.utils import process_utils


class GenericBatteryFunctionTest(unittest.TestCase):

  @mock.patch('cros.factory.utils.process_utils.CheckOutput')
  def testV1ECTool(self, mock_output):
    mock_output.return_value = textwrap.dedent("""\
        Battery info:
          OEM name:               123-ABC
          Model number:           XYZ-123
          Chemistry   :           LION
          Serial number:          12AB
          Design capacity:        6150 mAh
          Last full charge:       5938 mAh
          Design output voltage   7700 mV
          Cycle count             7
          Present voltage         8018 mV
          Present current         4085 mA
          Remaining capacity      1053 mAh
          Flags                   0x0b AC_PRESENT BATT_PRESENT CHARGING""")

    result = generic_battery.GenericBatteryFunction().Probe()
    self.assertEqual(
        result, {
            'manufacturer': '123-ABC',
            'model_name': 'XYZ-123',
            'technology': 'LION',
            'charge_full_design': '6150000'
        })

  @mock.patch('cros.factory.utils.process_utils.CheckOutput')
  def testV2ECTool(self, mock_output):
    mock_output.return_value = textwrap.dedent("""\
        Battery 0 info:
          OEM name:               123-ABCD-EF
          Model number:           XYZ-12345
          Chemistry   :           LION
          Serial number:          12AB
          Design capacity:        6150 mAh
          Last full charge:       5938 mAh
          Design output voltage   7700 mV
          Cycle count             7
          Present voltage         7981 mV
          Present current         -799 mA
          Remaining capacity      4400 mAh
          Desired voltage         8800 mV
          Desired current         4305 mA
          Flags                   0x06 BATT_PRESENT DISCHARGING""")

    result = generic_battery.GenericBatteryFunction().Probe()
    self.assertEqual(
        result, {
            'manufacturer': '123-ABCD-EF',
            'model_name': 'XYZ-12345',
            'technology': 'LION',
            'charge_full_design': '6150000'
        })

  @mock.patch('cros.factory.utils.process_utils.CheckOutput',
              side_effect=process_utils.CalledProcessError(1, 'command'))
  def testNoBattery(self, unused_mock_output):
    result = generic_battery.GenericBatteryFunction().Probe()
    self.assertEqual(result, None)


if __name__ == '__main__':
  unittest.main()
