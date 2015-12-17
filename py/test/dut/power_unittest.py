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

  def testGetBatteryCurrent(self):
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
    self.board.CheckOutput(['ectool', 'battery']).AndReturn(
        _MOCK_EC_BATTERY_READ)
    self.mox.ReplayAll()
    self.assertEquals(self.power.GetBatteryCurrent(), 128)
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

  def testProbeBattery(self):
    _BATTERY_INFO = textwrap.dedent("""
        Battery info:
          OEM name:          FOO
          Design capacity:   8000 mAh
        """)
    self.board.CheckOutput(['ectool', 'battery']).AndReturn(_BATTERY_INFO)
    self.mox.ReplayAll()
    self.assertEqual(8000, self.power.GetBatteryDesignCapacity())
    self.mox.VerifyAll()

  def testProbeBatteryFail(self):
    _BATTERY_INFO = textwrap.dedent("""
        Battery info:
          OEM name:          FOO
        """)
    self.board.CheckOutput(['ectool', 'battery']).AndReturn(_BATTERY_INFO)
    self.mox.ReplayAll()
    self.assertRaises(self.power.Error, self.power.GetBatteryDesignCapacity)
    self.mox.VerifyAll()

  def testProbeBatteryFailZeroBatteryCapacity(self):
    _BATTERY_INFO = textwrap.dedent("""
        Battery info:
          OEM name:          FOO
          Design capacity:   0 mAh
        """)
    self.board.CheckOutput(['ectool', 'battery']).AndReturn(_BATTERY_INFO)
    self.mox.ReplayAll()
    self.assertRaises(self.power.Error, self.power.GetBatteryDesignCapacity)
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
