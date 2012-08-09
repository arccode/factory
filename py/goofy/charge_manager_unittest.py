#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

import mox
import os
import shutil
import tempfile
import unittest

from cros.factory.goofy.charge_manager import ChargeManager

class ChargeManagerTest(unittest.TestCase):
  def setUp(self):
    self._mock_sys = tempfile.mkdtemp("mocksys")
    ChargeManager._sys = self._mock_sys

    self._ac_path = None
    self._battery_path = "%s/class/power_supply/BAT0" % self._mock_sys
    os.makedirs(self._battery_path)
    with open(os.path.join(self._battery_path, "type"), "w") as f:
      f.write("Battery")

    self._charge_manager = ChargeManager(70, 80)
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(self._charge_manager, "_Spawn")

  def SetUpAC(self):
    if self._ac_path:
      return
    self._ac_path = "%s/class/power_supply/AC" % self._mock_sys
    os.makedirs(self._ac_path)
    with open(os.path.join(self._ac_path, "type"), "w") as f:
      f.write("Mains")
    with open(os.path.join(self._ac_path, "online"), "w") as f:
      f.write("1")

  def RemoveAC(self):
    if self._ac_path:
      shutil.rmtree(self._ac_path)
      self._ac_path = None

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.VerifyAll()
    # Remove temp dir
    shutil.rmtree(self._mock_sys)

  def SetChargeLevel(self, level):
    with open("%s/charge_now" % self._battery_path, "w") as f:
      f.write("%d" % (level * 80000))
    with open("%s/charge_full" % self._battery_path, "w") as f:
      f.write("8000000")

  def testCharge(self):
    self.SetUpAC()
    self.SetChargeLevel(65)

    # pylint: disable=W0212
    self._charge_manager._Spawn(["ectool", "chargeforceidle", "0"],
                                ignore_stdout=True, log_stderr_on_error=True)
    self._charge_manager._Spawn(["ectool", "i2cwrite", "16", "0", "0x12",
                                "0x12", "0xf912"], ignore_stdout=True,
                                log_stderr_on_error=True)
    self.mox.ReplayAll()

    self._charge_manager.AdjustChargeState()


  def testDischarge(self):
    self.SetUpAC()
    self.SetChargeLevel(85)

    # pylint: disable=W0212
    self._charge_manager._Spawn(["ectool", "chargeforceidle", "1"],
                                ignore_stdout=True, log_stderr_on_error=True)
    self._charge_manager._Spawn(["ectool", "i2cwrite", "16", "0", "0x12",
                                "0x12", "0xf952"], ignore_stdout=True,
                                log_stderr_on_error=True)
    self.mox.ReplayAll()

    self._charge_manager.AdjustChargeState()

  def testStopCharge(self):
    self.SetUpAC()
    self.SetChargeLevel(75)

    # pylint: disable=W0212
    self._charge_manager._Spawn(["ectool", "chargeforceidle", "1"],
                                ignore_stdout=True, log_stderr_on_error=True)
    self._charge_manager._Spawn(["ectool", "i2cwrite", "16", "0", "0x12",
                                "0x12", "0xf912"], ignore_stdout=True,
                                log_stderr_on_error=True)
    self.mox.ReplayAll()

    self._charge_manager.AdjustChargeState()

  def testNoAC(self):
    self.RemoveAC()
    self.mox.ReplayAll()

    self._charge_manager.AdjustChargeState()


if __name__ == '__main__':
  unittest.main()
