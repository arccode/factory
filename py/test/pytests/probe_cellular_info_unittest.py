#!/usr/bin/env python3
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Probes information from 'modem status'.

Requested data are probed, written to the event log, and saved to device data.
"""

import unittest
from unittest import mock

from cros.factory.test.pytests import probe_cellular_info
from cros.factory.utils.arg_utils import Args


class ProbeCellularInfoTestTest(unittest.TestCase):

  def setUp(self):
    self.test = probe_cellular_info.ProbeCellularInfoTest()

  @mock.patch('cros.factory.utils.process_utils.CheckOutput')
  @mock.patch('cros.factory.test.event_log.Log')
  @mock.patch('cros.factory.testlog.testlog.LogParam')
  @mock.patch('cros.factory.test.device_data.UpdateDeviceData')
  def testValid(self, update_device_data_mock, log_param_mock, log_mock,
                check_output_mock):
    stdout = """
Modem /org/chromium/ModemManager/Gobi/1:
  GetStatus:
    imei: 838293836198373
    meid: Q9298301CDF827
"""

    log_param_calls = [
        mock.call('modem_status_stdout', stdout),
        mock.call('imei', '838293836198373'),
        mock.call('meid', 'Q9298301CDF827')]

    check_output_mock.return_value = stdout

    self.test.args = Args(*self.test.ARGS).Parse({})
    self.test.runTest()

    check_output_mock.assert_called_once_with(['modem', 'status'], log=True)
    self.assertEqual(log_param_mock.call_args_list, log_param_calls)
    log_mock.assert_called_once_with(
        'cellular_info', modem_status_stdout=stdout,
        imei='838293836198373', meid='Q9298301CDF827')
    update_device_data_mock.assert_called_once_with(
        {'component.cellular.imei': '838293836198373',
         'component.cellular.meid': 'Q9298301CDF827'})

  @mock.patch('cros.factory.utils.process_utils.CheckOutput')
  @mock.patch('cros.factory.test.event_log.Log')
  @mock.patch('cros.factory.testlog.testlog.LogParam')
  @mock.patch('cros.factory.test.device_data.UpdateDeviceData')
  def testValidLTE(self, update_device_data_mock, log_param_mock, log_mock,
                   check_output_mock):
    stdout = """
Modem /org/freedesktop/ModemManager1/Modem/0:
  GetStatus:
    state: 7
  Properties:
    Sim: /org/freedesktop/ModemManager1/SIM/0
    SupportedCapabilities: 8
    CurrentCapabilities: 8
    MaxBearers: 1
    MaxActiveBearers: 1
    Manufacturer: ALTAIR-SEMICONDUCTOR
    Model: ALT3100
    Revision: ALT3100_04_05_06_00_58_TF
    DeviceIdentifier: 14336085e42e1bc2ea8da6e1f52a86f55f2a54b1
    Device: /sys/devices/s5p-ehci/usb1/1-2/1-2.2
    Drivers: cdc_ether, cdc_acm
    Plugin: Altair LTE
    PrimaryPort: ttyACM0
    EquipmentIdentifier: 359636040066332
    UnlockRequired: 1
    UnlockRetries: 3, 3, 10, 10
    State: 7
    StateFailedReason: 0
    AccessTechnologies: 0
    SignalQuality: 0, false
    OwnNumbers: +16503189999
    PowerState: 3
    SupportedModes: 8, 0
    CurrentModes: 8, 0
    SupportedBands: 43
    CurrentBands: 43
    SupportedIpFamilies: 1
  3GPP:
    Imei: 359636040066332
    RegistrationState: 4
    OperatorCode:
    OperatorName:
    EnabledFacilityLocks: 0
  CDMA:
  SIM /org/freedesktop/ModemManager1/SIM/0:
    SimIdentifier: 89148000000328035895
    Imsi: 204043996791870
    OperatorIdentifier: 20404
    OperatorName:
"""

    log_param_calls = [
        mock.call('modem_status_stdout', stdout),
        mock.call('lte_imei', '359636040066332'),
        mock.call('lte_iccid', '89148000000328035895')]

    check_output_mock.return_value = stdout

    self.test.args = Args(*self.test.ARGS).Parse(
        {'probe_imei': False,
         'probe_meid': False,
         'probe_lte_imei': True,
         'probe_lte_iccid': True})
    self.test.runTest()

    check_output_mock.assert_called_once_with(['modem', 'status'], log=True)
    self.assertEqual(log_param_mock.call_args_list, log_param_calls)
    log_mock.assert_called_once_with(
        'cellular_info', modem_status_stdout=stdout,
        lte_imei='359636040066332', lte_iccid='89148000000328035895')
    update_device_data_mock.assert_called_once_with(
        {'component.cellular.lte_imei': '359636040066332',
         'component.cellular.lte_iccid': '89148000000328035895'})

  @mock.patch('cros.factory.utils.process_utils.CheckOutput')
  @mock.patch('cros.factory.test.event_log.Log')
  @mock.patch('cros.factory.testlog.testlog.LogParam')
  def testMissingIMEI(self, log_param_mock, log_mock, check_output_mock):
    stdout = """
Modem /org/chromium/ModemManager/Gobi/1:
  GetStatus:
    meid: Q9298301CDF827
"""

    log_param_calls = [
        mock.call('modem_status_stdout', stdout),
        mock.call('imei', None),
        mock.call('meid', 'Q9298301CDF827')]

    check_output_mock.return_value = stdout

    self.test.args = Args(*self.test.ARGS).Parse({})
    self.assertRaisesRegex(AssertionError, r"Missing elements.+: \['imei'\]",
                           self.test.runTest)

    check_output_mock.assert_called_once_with(['modem', 'status'], log=True)
    self.assertEqual(log_param_mock.call_args_list, log_param_calls)
    log_mock.assert_called_once_with(
        'cellular_info', modem_status_stdout=stdout,
        imei=None, meid='Q9298301CDF827')

  @mock.patch('cros.factory.utils.process_utils.CheckOutput')
  @mock.patch('cros.factory.test.event_log.Log')
  @mock.patch('cros.factory.testlog.testlog.LogParam')
  def testBlankIMEI(self, log_param_mock, log_mock, check_output_mock):
    stdout = """
Modem /org/chromium/ModemManager/Gobi/1:
  GetStatus:
    imei: #
    meid: Q9298301CDF827
""".replace('#', '')
    # Remove hash mark; necessary to make white-space check pass

    log_param_calls = [
        mock.call('modem_status_stdout', stdout),
        mock.call('imei', None),
        mock.call('meid', 'Q9298301CDF827')]

    check_output_mock.return_value = stdout

    self.test.args = Args(*self.test.ARGS).Parse({})
    self.assertRaisesRegex(AssertionError, r"Missing elements.+: \['imei'\]",
                           self.test.runTest)

    check_output_mock.assert_called_once_with(['modem', 'status'], log=True)
    log_mock.assert_called_once_with(
        'cellular_info', modem_status_stdout=stdout,
        imei=None, meid='Q9298301CDF827')
    self.assertEqual(log_param_mock.call_args_list, log_param_calls)

  @mock.patch('cros.factory.utils.process_utils.CheckOutput')
  @mock.patch('cros.factory.test.event_log.Log')
  @mock.patch('cros.factory.testlog.testlog.LogParam')
  @mock.patch('cros.factory.test.device_data.UpdateDeviceData')
  def testSpecifiedFields(self, update_device_data_mock, log_param_mock,
                          log_mock, check_output_mock):
    stdout = """
Modem /org/freedesktop/ModemManager1/Modem/7:
  Properties:
    EquipmentIdentifier: 862227050001326
"""

    log_param_calls = [
        mock.call('modem_status_stdout', stdout),
        mock.call('imei', '862227050001326')
    ]

    check_output_mock.return_value = stdout

    self.test.args = Args(*self.test.ARGS).Parse({
        'probe_meid': False,
        'fields': {
            'imei': 'EquipmentIdentifier'
        }
    })
    self.test.runTest()

    check_output_mock.assert_called_once_with(['modem', 'status'], log=True)
    log_mock.assert_called_once_with(
        'cellular_info', modem_status_stdout=stdout, imei='862227050001326')
    self.assertEqual(log_param_mock.call_args_list, log_param_calls)
    update_device_data_mock.assert_called_once_with(
        {'component.cellular.imei': '862227050001326'})


if __name__ == '__main__':
  unittest.main()
