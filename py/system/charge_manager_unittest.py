#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=W0212

import factory_common  # pylint: disable=W0611

import logging
import mox
import unittest

from cros.factory.test.dut.power import Power
from cros.factory.system.charge_manager import ChargeManager


class ChargeManagerTest(unittest.TestCase):

  def setUp(self):
    self.mox = mox.Mox()
    self._power = self.mox.CreateMock(Power)
    self._charge_manager = ChargeManager(70, 80, self._power)

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
