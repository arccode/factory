#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for Power."""

from __future__ import print_function

import mox
import textwrap
import unittest

from subprocess import CalledProcessError

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import board
from cros.factory.test.dut import power


class PowerTest(unittest.TestCase):
  """Unittest for power.Power."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(board.DUTBoard)
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
    self.board = self.mox.CreateMock(board.DUTBoard)
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
    self.assertItemsEqual(['0x03', 'AC_PRESENT', 'BATT_PRESENT', 'CHARGING'],
                          self.power._GetECToolBatteryFlags())
    self.mox.VerifyAll()

  def testGetECToolBatteryAttribute(self):
    self.board.CallOutput(['ectool', 'battery']).MultipleTimes().AndReturn(
        self._MOCK_EC_BATTERY_READ)
    self.mox.ReplayAll()
    self.assertEqual(3220,
                     self.power._GetECToolBatteryAttribute('Design capacity:'))
    self.assertEqual(4,
                     self.power._GetECToolBatteryAttribute('Cycle count'))
    self.assertEqual(128,
                     self.power._GetECToolBatteryAttribute('Present current'))
    self.mox.VerifyAll()

  def testUSBPDPowerInfo(self):
    _USB_PD_POWER_INFO = textwrap.dedent("""
        Port 0: Disconnected
        Port 1: SNK Charger PD 22mV / 33mA, max 44mV / 55mA / 66mW
        Port 2: SRC
        """)

    self.board.CheckOutput(['ectool', '--name=cros_pd',
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
    self.board.CheckOutput(['ectool', '--name=cros_pd',
                            'usbpdpower']).AndRaise(exception)
    self.mox.ReplayAll()

    try:
      self.power.GetUSBPDPowerInfo()
    except CalledProcessError as e:
      self.assertEqual(e, exception)
    self.mox.VerifyAll()

  def testUSBPDPowerInfoEmptyString(self):
    _USB_PD_POWER_INFO = ""
    self.board.CheckOutput(['ectool', '--name=cros_pd',
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

    self.board.CheckOutput(['ectool', '--name=cros_pd',
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

    self.board.CheckOutput(['ectool', '--name=cros_pd',
                            'usbpdpower']).AndReturn(_USB_PD_POWER_INFO)
    self.mox.ReplayAll()
    self.assertRaisesRegexp(self.power.Error, 'unexpected output for SNK',
                            self.power.GetUSBPDPowerInfo)
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
