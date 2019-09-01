#!/usr/bin/env python2
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=protected-access

import logging
import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.device.power import Power
from cros.factory.test.utils import charge_manager


class ChargeManagerTest(unittest.TestCase):

  def setUp(self):
    self.mox = mox.Mox()
    self._power = self.mox.CreateMock(Power)
    # Patch in the ChargeState Enum.
    self._power.ChargeState = Power.ChargeState
    self._charge_manager = charge_manager.ChargeManager(70, 80, self._power)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testCharge(self):
    self._power.CheckBatteryPresent().AndReturn(True)
    self._power.CheckACPresent().AndReturn(True)
    self._power.GetChargePct().AndReturn(65)
    self._power.SetChargeState(self._power.ChargeState.CHARGE)
    self.mox.ReplayAll()

    self._charge_manager.AdjustChargeState()

    self.mox.VerifyAll()

  def testDischarge(self):
    self._power.CheckBatteryPresent().AndReturn(True)
    self._power.CheckACPresent().AndReturn(True)
    self._power.GetChargePct().AndReturn(85)
    self._power.SetChargeState(self._power.ChargeState.DISCHARGE)
    self.mox.ReplayAll()

    self._charge_manager.AdjustChargeState()

    self.mox.VerifyAll()

  def testStopCharge(self):
    self._power.CheckBatteryPresent().AndReturn(True)
    self._power.CheckACPresent().AndReturn(True)
    self._power.GetChargePct().AndReturn(75)
    self._power.SetChargeState(self._power.ChargeState.IDLE)
    self.mox.ReplayAll()

    self._charge_manager.AdjustChargeState()

    self.mox.VerifyAll()

  def testNoAC(self):
    self._power.CheckBatteryPresent().AndReturn(True)
    self._power.CheckACPresent().AndReturn(False)
    self.mox.ReplayAll()

    self._charge_manager.AdjustChargeState()

    self.mox.VerifyAll()


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
