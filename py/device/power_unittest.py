#!/usr/bin/env python3
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for Power."""

from subprocess import CalledProcessError
import textwrap
import unittest
from unittest import mock

from cros.factory.device import device_utils
from cros.factory.device import power


class ECToolPowerControlTest(unittest.TestCase):
  """Unittest for power.ECToolPowerControlMixin."""

  def setUp(self):
    self.board = device_utils.CreateDUTInterface()
    self.power = power.CreatePower(self.board, power.ECToolPowerControlMixin)

  def testCharge(self):
    self.board.CheckCall = mock.MagicMock()
    self.power.SetChargeState(self.power.ChargeState.CHARGE)
    self.board.CheckCall.assert_called_once_with(
        ['ectool', 'chargecontrol', 'normal'])

  def testDischarge(self):
    self.board.CheckCall = mock.MagicMock()
    self.power.SetChargeState(self.power.ChargeState.DISCHARGE)
    self.board.CheckCall.assert_called_once_with(
        ['ectool', 'chargecontrol', 'discharge'])

  def testStopCharge(self):
    self.board.CheckCall = mock.MagicMock()
    self.power.SetChargeState(self.power.ChargeState.IDLE)
    self.board.CheckCall.assert_called_once_with(
        ['ectool', 'chargecontrol', 'idle'])

class SysfsPowerInfoTest(unittest.TestCase):
  """Unittest for power.SysfsPowerInfoMixin."""

  def setUp(self):
    self.board = device_utils.CreateDUTInterface()
    self.power = power.CreatePower(self.board, power.SysfsPowerInfoMixin)

  def testCheckACPresent(self):
    self.power.FindPowerPath = mock.MagicMock(return_value='')
    self.power.ReadOneLine = mock.MagicMock(return_value='1')
    self.assertEqual(self.power.CheckACPresent(), True)
    self.power.ReadOneLine = mock.MagicMock(return_value='0')
    self.assertEqual(self.power.CheckACPresent(), False)

  def testGetACType(self):
    self.power.FindPowerPath = mock.MagicMock(return_value='')
    self.power.ReadOneLine = mock.MagicMock(return_value='USB_PD')
    self.assertEqual(self.power.GetACType(), 'USB_PD')

  def testCheckBatteryPresent(self):
    _MOCK_BATTERY_PATH = '/sys/class/power_supply/BAT0'
    # pylint: disable=protected-access
    type(self.power)._battery_path = mock.PropertyMock(
        return_value=_MOCK_BATTERY_PATH)
    self.assertEqual(self.power.CheckBatteryPresent(), True)
    # pylint: disable=protected-access
    type(self.power)._battery_path = mock.PropertyMock(return_value='')
    self.assertEqual(self.power.CheckBatteryPresent(), False)

  def testGetChargerCurrent(self):
    _MOCK_ECTOOL_CHARGESTATE = textwrap.dedent("""
        ac = 1
        chg_voltage = 13200mV
        chg_current = 3200mA
        chg_input_current = 3000mA
        batt_state_of_charge = 86%
        """)
    self.board.CheckOutput = mock.MagicMock(
        return_value=_MOCK_ECTOOL_CHARGESTATE)
    self.assertEqual(self.power.GetChargerCurrent(), 3200)

  def testGetBatteryVoltage(self):
    self.power.FindPowerPath = mock.MagicMock(return_value='')
    self.power.ReadOneLine = mock.MagicMock(return_value='12660000')
    self.assertEqual(self.power.GetBatteryVoltage(), 12660)

  def testGetBatteryCycleCount(self):
    self.power.FindPowerPath = mock.MagicMock(return_value='')
    self.power.ReadOneLine = mock.MagicMock(return_value='10')
    self.assertEqual(self.power.GetBatteryCycleCount(), 10)

  def testGetBatteryManufacturer(self):
    self.power.FindPowerPath = mock.MagicMock(return_value='')
    self.power.ReadOneLine = mock.MagicMock(return_value='LGC')
    self.assertEqual(self.power.GetBatteryManufacturer(), 'LGC')


class ECToolPowerInfoTest(unittest.TestCase):
  """Unittest for power.ECToolPowerInfoMixin."""
  _MOCK_EC_BATTERY_READ = textwrap.dedent("""
      Battery info:
        OEM name:               LGC
        Model number:           AC14B8K
        Chemistry   :           LION
        Serial number:          09FE
        Design capacity:        3220 mAh
        Last full charge:       3194 mAh
        Design output voltage   15200 mV
        Cycle count             4
        Present voltage         15370 mV
        Present current         128 mA
        Remaining capacity      1597 mAh
        Flags                   0x03 AC_PRESENT BATT_PRESENT CHARGING
      """)

  def setUp(self):
    self.board = device_utils.CreateDUTInterface()
    self.power = power.CreatePower(self.board, power.ECToolPowerInfoMixin)

  def testCheckACPresent(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    self.assertEqual(self.power.CheckACPresent(), True)

  def testGetACType(self):
    self.assertEqual(self.power.GetACType(), 'Unknown')

  def testCheckBatteryPresent(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    self.assertEqual(self.power.CheckBatteryPresent(), True)

  def testGetCharge(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    self.assertEqual(self.power.GetCharge(), 1597)

  def testGetChargeFull(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    self.assertEqual(self.power.GetChargeFull(), 3194)

  def testGetChargePct(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    self.assertEqual(self.power.GetChargePct(), 50.0)

  def testGetWearPct(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    self.assertEqual(self.power.GetWearPct(), 1.0)

  def testGetChargeState(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    self.assertEqual(self.power.GetChargeState(), 'CHARGE')

  def testGetBatteryCurrent(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    self.assertEqual(self.power.GetBatteryCurrent(), 128)

  def testGetBatteryDesignCapacity(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    self.assertEqual(self.power.GetBatteryDesignCapacity(), 3220)

  def testGetChargerCurrent(self):
    _MOCK_ECTOOL_CHARGESTATE = textwrap.dedent("""
        ac = 1
        chg_voltage = 13200mV
        chg_current = 3200mA
        chg_input_current = 3000mA
        batt_state_of_charge = 86%
        """)
    self.board.CheckOutput = mock.MagicMock(
        return_value=_MOCK_ECTOOL_CHARGESTATE)
    self.assertEqual(self.power.GetChargerCurrent(), 3200)

  def testGetBatteryVoltage(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    self.assertEqual(self.power.GetBatteryVoltage(), 15370)

  def testGetBatteryCycleCount(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    self.assertEqual(self.power.GetBatteryCycleCount(), 4)

  def testGetBatteryManufacturer(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    self.assertEqual(self.power.GetBatteryManufacturer(), 'LGC')

  def testGetInfoDict(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    expected_dict = {
        'current_now': 128,
        'status': 'CHARGE',
        'present': True,
        'voltage_now': 15370,
        'charge_full': 3194,
        'charge_full_design': 3220,
        'charge_now': 1597,
        'fraction_full': 0.5
    }
    self.assertEqual(self.power.GetInfoDict(), expected_dict)

  def testProbeBatteryFail(self):
    _BATTERY_INFO = textwrap.dedent("""
        Battery info:
          OEM name:          FOO
        """)
    self.board.CallOutput = mock.MagicMock(return_value=_BATTERY_INFO)
    self.assertRaises(self.power.Error, self.power.GetBatteryDesignCapacity)

  def testGetECToolBatteryFlags(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    # pylint: disable=protected-access
    self.assertCountEqual(
        ['0x03', 'AC_PRESENT', 'BATT_PRESENT', 'CHARGING'],
        self.power._GetECToolBatteryFlags())

  def testGetECToolBatteryAttribute(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_EC_BATTERY_READ)
    # pylint: disable=protected-access
    self.assertEqual('AC14B8K',
                     self.power._GetECToolBatteryAttribute('Model number:'))
    # pylint: disable=protected-access
    self.assertEqual(4,
                     self.power._GetECToolBatteryAttribute('Cycle count', int))

  def testUSBPDPowerInfo(self):
    _USB_PD_POWER_INFO = textwrap.dedent("""
        Port 0: Disconnected
        Port 1: SNK Charger PD 22mV / 33mA, max 44mV / 55mA / 66mW
        Port 2: SRC
        """)
    self.board.CheckOutput = mock.MagicMock(return_value=_USB_PD_POWER_INFO)
    self.assertEqual(
        [(0, 'Disconnected', None, None),
         (1, 'SNK', 22, 33),
         (2, 'SRC', None, None)],
        self.power.GetUSBPDPowerInfo())

  def testUSBPDPowerInfoCommandFailed(self):
    exception = CalledProcessError(
        returncode=1, cmd='cmd', output='output')
    self.board.CheckOutput = mock.MagicMock(side_effect=exception)

    try:
      self.power.GetUSBPDPowerInfo()
    except CalledProcessError as e:
      self.assertEqual(e, exception)

  def testUSBPDPowerInfoEmptyString(self):
    _USB_PD_POWER_INFO = ""
    self.board.CheckOutput = mock.MagicMock(return_value=_USB_PD_POWER_INFO)
    self.assertEqual([], self.power.GetUSBPDPowerInfo())

  def testUSBPDPowerInfoUnexpectedPDState(self):
    _USB_PD_POWER_INFO = textwrap.dedent("""
        Port 0: Disconnected
        Port 1: XXX
        Port 2: SNK Charger PD 22mV / 33mA, max 44mV / 55mA / 66mW
        Port 3: SRC
        """)
    self.board.CheckOutput = mock.MagicMock(return_value=_USB_PD_POWER_INFO)
    self.assertRaisesRegex(self.power.Error, 'unexpected PD state',
                           self.power.GetUSBPDPowerInfo)

  def testUSBPDPowerInfoIncorrectSNKOutput(self):
    _USB_PD_POWER_INFO = textwrap.dedent("""
        Port 0: Disconnected
        Port 1: SNK Charger XXXX
        Port 2: SRC
        """)
    self.board.CheckOutput = mock.MagicMock(return_value=_USB_PD_POWER_INFO)
    self.assertRaisesRegex(self.power.Error, 'unexpected output for SNK',
                           self.power.GetUSBPDPowerInfo)


class PowerDaemonPowerInfoTest(unittest.TestCase):
  """Unittest for power.PowerDaemonPowerInfoMixin."""
  _MOCK_DUMP_POWER_STATUS_CHARGE = textwrap.dedent("""
      line_power_connected 1
      line_power_type USB_PD
      line_power_current 0.00
      battery_present 1
      battery_percent 36.45
      battery_display_percent 37.58
      battery_charge 1.72
      battery_charge_full 4.71
      battery_charge_full_design 4.67
      battery_current 2.92
      battery_energy 19.84
      battery_energy_rate 35.59
      battery_voltage 12.21
      battery_status Charging
      battery_discharging 0
      """)
  _MOCK_DUMP_POWER_STATUS_DISCHARGE = textwrap.dedent("""
      line_power_connected 0
      line_power_type
      line_power_current 0.00
      battery_present 1
      battery_percent 36.45
      battery_display_percent 37.58
      battery_charge 1.72
      battery_charge_full 4.71
      battery_charge_full_design 4.67
      battery_current 2.92
      battery_energy 19.84
      battery_energy_rate 35.59
      battery_voltage 12.21
      battery_status Discharging
      battery_discharging 1
      """)
  _MOCK_DUMP_POWER_STATUS_FULL = textwrap.dedent("""
      line_power_connected 1
      line_power_type USB
      line_power_current 0.00
      battery_present 1
      battery_percent 88.78
      battery_display_percent 91.16
      battery_charge 3.32
      battery_charge_full 3.73
      battery_charge_full_design 3.73
      battery_current 0.00
      battery_energy 41.73
      battery_energy_rate 0.00
      battery_voltage 12.59
      battery_status Full
      battery_discharging 1
      """)

  def setUp(self):
    self.board = device_utils.CreateDUTInterface()
    self.power = power.CreatePower(self.board, power.PowerDaemonPowerInfoMixin)

  def testCheckACPresent(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEqual(self.power.CheckACPresent(), True)
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_DISCHARGE)
    self.assertEqual(self.power.CheckACPresent(), False)

  def testGetACType(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEqual(self.power.GetACType(), 'USB_PD')
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_DISCHARGE)
    self.assertEqual(self.power.GetACType(), '')

  def testCheckBatteryPresent(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEqual(self.power.CheckBatteryPresent(), True)

  def testGetCharge(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEqual(self.power.GetCharge(), 1720)

  def testGetChargeFull(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEqual(self.power.GetChargeFull(), 4710)

  def testGetChargePct(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEqual(self.power.GetChargePct(), 36.0)

  def testGetWearPct(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEqual(self.power.GetWearPct(), -1.0)

  def testGetChargeState(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEqual(self.power.GetChargeState(), 'CHARGE')
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_DISCHARGE)
    self.assertEqual(self.power.GetChargeState(), 'DISCHARGE')
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_FULL)
    self.assertEqual(self.power.GetChargeState(), 'FULL')

  def testGetBatteryCurrent(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEqual(self.power.GetBatteryCurrent(), 2920)
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_DISCHARGE)
    self.assertEqual(self.power.GetBatteryCurrent(), -2920)
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_FULL)
    self.assertEqual(self.power.GetBatteryCurrent(), 0)

  def testGetBatteryDesignCapacity(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEqual(self.power.GetBatteryDesignCapacity(), 4670)

  def testGetBatteryVoltage(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEqual(self.power.GetBatteryVoltage(), 12210)


if __name__ == '__main__':
  unittest.main()
