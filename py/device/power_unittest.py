#!/usr/bin/env python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for Power."""

from __future__ import print_function

from subprocess import CalledProcessError
import textwrap
import unittest

import mock
import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.device import power
from cros.factory.device import types


class PowerTest(unittest.TestCase):
  """Unittest for power.Power."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(types.DeviceBoard)
    self.power = power.Power(self.board)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testGetChargerCurrent(self):
    _MOCK_EC_CHARGER_READ = textwrap.dedent("""
        ac = 1
        chg_voltage = 0mV
        chg_current = 128mA
        chg_input_current = 2048mA
        batt_state_of_charge = 52%
        """)
    self.board.CheckOutput(['ectool', 'chargestate', 'show']).AndReturn(
        _MOCK_EC_CHARGER_READ)
    self.mox.ReplayAll()
    self.assertEquals(self.power.GetChargerCurrent(), 128)
    self.mox.VerifyAll()

  def testCharge(self):
    self.board.CheckCall(['ectool', 'chargecontrol', 'normal'])
    self.mox.ReplayAll()
    self.power.SetChargeState(self.power.ChargeState.CHARGE)
    self.mox.VerifyAll()

  def testDischarge(self):
    self.board.CheckCall(['ectool', 'chargecontrol', 'discharge'])
    self.mox.ReplayAll()
    self.power.SetChargeState(self.power.ChargeState.DISCHARGE)
    self.mox.VerifyAll()

  def testStopCharge(self):
    self.board.CheckCall(['ectool', 'chargecontrol', 'idle'])
    self.mox.ReplayAll()
    self.power.SetChargeState(self.power.ChargeState.IDLE)
    self.mox.VerifyAll()


class ECToolPowerTest(unittest.TestCase):
  """Unittest for power.ECToolPower."""
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
        Remaining capacity      1642 mAh
        Flags                   0x03 AC_PRESENT BATT_PRESENT CHARGING
      """)

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(types.DeviceBoard)
    self.power = power.ECToolPower(self.board)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testGetBatteryCurrent(self):
    self.board.CallOutput(['ectool', 'battery']).MultipleTimes().AndReturn(
        self._MOCK_EC_BATTERY_READ)
    self.mox.ReplayAll()
    self.assertEquals(self.power.GetBatteryCurrent(), 128)
    self.mox.VerifyAll()

  def testProbeBattery(self):
    self.board.CallOutput(['ectool', 'battery']).AndReturn(
        self._MOCK_EC_BATTERY_READ)
    self.mox.ReplayAll()
    self.assertEqual(3220, self.power.GetBatteryDesignCapacity())
    self.mox.VerifyAll()

  def testProbeBatteryFail(self):
    _BATTERY_INFO = textwrap.dedent("""
        Battery info:
          OEM name:          FOO
        """)
    self.board.CallOutput(['ectool', 'battery']).AndReturn(_BATTERY_INFO)
    self.mox.ReplayAll()
    self.assertRaises(self.power.Error, self.power.GetBatteryDesignCapacity)
    self.mox.VerifyAll()

  def testGetECToolBatteryFlags(self):
    self.board.CallOutput(['ectool', 'battery']).AndReturn(
        self._MOCK_EC_BATTERY_READ)
    self.mox.ReplayAll()
    # pylint: disable=protected-access
    self.assertItemsEqual(['0x03', 'AC_PRESENT', 'BATT_PRESENT', 'CHARGING'],
                          self.power._GetECToolBatteryFlags())
    self.mox.VerifyAll()

  def testGetECToolBatteryAttribute(self):
    self.board.CallOutput(['ectool', 'battery']).MultipleTimes().AndReturn(
        self._MOCK_EC_BATTERY_READ)
    self.mox.ReplayAll()
    # pylint: disable=protected-access
    self.assertEqual(3220,
                     self.power._GetECToolBatteryAttribute('Design capacity:'))
    # pylint: disable=protected-access
    self.assertEqual(4,
                     self.power._GetECToolBatteryAttribute('Cycle count'))
    # pylint: disable=protected-access
    self.assertEqual(128,
                     self.power._GetECToolBatteryAttribute('Present current'))
    self.mox.VerifyAll()

  def testUSBPDPowerInfo(self):
    _USB_PD_POWER_INFO = textwrap.dedent("""
        Port 0: Disconnected
        Port 1: SNK Charger PD 22mV / 33mA, max 44mV / 55mA / 66mW
        Port 2: SRC
        """)

    self.board.CheckOutput(['ectool',
                            'usbpdpower']).AndReturn(_USB_PD_POWER_INFO)
    self.mox.ReplayAll()
    self.assertEqual(
        [(0, 'Disconnected', None, None),
         (1, 'SNK', 22, 33),
         (2, 'SRC', None, None)],
        self.power.GetUSBPDPowerInfo())
    self.mox.VerifyAll()

  def testUSBPDPowerInfoCommandFailed(self):
    exception = CalledProcessError(
        returncode=1, cmd='cmd', output='output')
    self.board.CheckOutput(['ectool',
                            'usbpdpower']).AndRaise(exception)
    self.mox.ReplayAll()

    try:
      self.power.GetUSBPDPowerInfo()
    except CalledProcessError as e:
      self.assertEqual(e, exception)
    self.mox.VerifyAll()

  def testUSBPDPowerInfoEmptyString(self):
    _USB_PD_POWER_INFO = ""
    self.board.CheckOutput(['ectool',
                            'usbpdpower']).AndReturn(_USB_PD_POWER_INFO)
    self.mox.ReplayAll()
    self.assertEqual([], self.power.GetUSBPDPowerInfo())
    self.mox.VerifyAll()

  def testUSBPDPowerInfoUnexpectedPDState(self):
    _USB_PD_POWER_INFO = textwrap.dedent("""
        Port 0: Disconnected
        Port 1: XXX
        Port 2: SNK Charger PD 22mV / 33mA, max 44mV / 55mA / 66mW
        Port 3: SRC
        """)

    self.board.CheckOutput(['ectool',
                            'usbpdpower']).AndReturn(_USB_PD_POWER_INFO)
    self.mox.ReplayAll()
    self.assertRaisesRegexp(self.power.Error, 'unexpected PD state',
                            self.power.GetUSBPDPowerInfo)
    self.mox.VerifyAll()

  def testUSBPDPowerInfoIncorrectSNKOutput(self):
    _USB_PD_POWER_INFO = textwrap.dedent("""
        Port 0: Disconnected
        Port 1: SNK Charger XXXX
        Port 2: SRC
        """)

    self.board.CheckOutput(['ectool',
                            'usbpdpower']).AndReturn(_USB_PD_POWER_INFO)
    self.mox.ReplayAll()
    self.assertRaisesRegexp(self.power.Error, 'unexpected output for SNK',
                            self.power.GetUSBPDPowerInfo)
    self.mox.VerifyAll()


class PowerDaemonPowerTest(unittest.TestCase):
  """Unittest for power.PowerDaemonPower."""
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

  def setUp(self):
    self.board = device_utils.CreateDUTInterface()
    self.power = power.PowerDaemonPower(self.board)

  def testCheckACPresent(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEquals(self.power.CheckACPresent(), True)
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_DISCHARGE)
    self.assertEquals(self.power.CheckACPresent(), False)

  def testGetACType(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEquals(self.power.GetACType(), 'USB_PD')
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_DISCHARGE)
    self.assertEquals(self.power.GetACType(), '')

  def testCheckBatteryPresent(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEquals(self.power.CheckBatteryPresent(), True)

  def testGetCharge(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEquals(self.power.GetCharge(), 1720)

  def testGetChargeFull(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEquals(self.power.GetChargeFull(), 4710)

  def testGetChargePct(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEquals(self.power.GetChargePct(), 36.0)
    self.assertEquals(self.power.GetChargePct(True), 36.45)

  def testGetWearPct(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEquals(self.power.GetWearPct(), -1.0)

  def testGetChargeState(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEquals(self.power.GetChargeState(), 'Charging')
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_DISCHARGE)
    self.assertEquals(self.power.GetChargeState(), 'Discharging')

  def testGetBatteryCurrent(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEquals(self.power.GetBatteryCurrent(), 2920)
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_DISCHARGE)
    self.assertEquals(self.power.GetBatteryCurrent(), -2920)

  def testGetBatteryDesignCapacity(self):
    self.board.CallOutput = mock.MagicMock(
        return_value=self._MOCK_DUMP_POWER_STATUS_CHARGE)
    self.assertEqual(self.power.GetBatteryDesignCapacity(), 4670)


if __name__ == '__main__':
  unittest.main()
