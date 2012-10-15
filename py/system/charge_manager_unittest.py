#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

import logging
import mox
import unittest

from cros.factory.system.ec import EC
from cros.factory.system.power import Power
from cros.factory.system.charge_manager import ChargeManager

class ChargeManagerTest(unittest.TestCase):
  def setUp(self):
    self._charge_manager = ChargeManager(70, 80)
    self.mox = mox.Mox()
    self._charge_manager._power = self.mox.CreateMock(Power)
    self._charge_manager._ec = self.mox.CreateMock(EC)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testCharge(self):
    self._charge_manager._power.CheckBatteryPresent().AndReturn(True)
    self._charge_manager._power.CheckACPresent().AndReturn(True)
    self._charge_manager._power.GetChargePct().AndReturn(65)
    self._charge_manager._ec.SetChargeState(EC.ChargeState.CHARGE)
    self.mox.ReplayAll()

    self._charge_manager.AdjustChargeState()

    self.mox.VerifyAll()

  def testDischarge(self):
    self._charge_manager._power.CheckBatteryPresent().AndReturn(True)
    self._charge_manager._power.CheckACPresent().AndReturn(True)
    self._charge_manager._power.GetChargePct().AndReturn(85)
    self._charge_manager._ec.SetChargeState(EC.ChargeState.DISCHARGE)
    self.mox.ReplayAll()

    self._charge_manager.AdjustChargeState()

    self.mox.VerifyAll()

  def testStopCharge(self):
    self._charge_manager._power.CheckBatteryPresent().AndReturn(True)
    self._charge_manager._power.CheckACPresent().AndReturn(True)
    self._charge_manager._power.GetChargePct().AndReturn(75)
    self._charge_manager._ec.SetChargeState(EC.ChargeState.IDLE)
    self.mox.ReplayAll()

    self._charge_manager.AdjustChargeState()

    self.mox.VerifyAll()

  def testNoAC(self):
    self._charge_manager._power.CheckBatteryPresent().AndReturn(True)
    self._charge_manager._power.CheckACPresent().AndReturn(False)
    self.mox.ReplayAll()

    self._charge_manager.AdjustChargeState()

    self.mox.VerifyAll()


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
