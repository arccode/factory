#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for Thermal component."""

from __future__ import print_function

import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import thermal
from cros.factory.test.dut import board


class ThermalTest(unittest.TestCase):
  """Unittest for Thermal."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(board.DUTBoard)
    self.thermal = thermal.Thermal(self.board)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testGetTemperatures(self):
    _MOCK_TEMPS = '\n'.join([
        '0: 273',
        '1: 283',
        '2: 293',
        '3: 303',
        '4: 313',
        '5: 323'])
    self.board.CallOutput(['ectool', 'temps', 'all']).AndReturn(_MOCK_TEMPS)
    self.mox.ReplayAll()
    self.assertEquals(self.thermal.GetTemperatures(), [0, 10, 20, 30, 40, 50])
    self.mox.VerifyAll()

  def testGetTemperaturesNotCalibrated(self):
    _MOCK_TEMPS = '\n'.join([
        '0: 273',
        '1: 283',
        'Sensor 2 not calibrated',
        '3: 303',
        '4: 313',
        '5: 323'])
    self.board.CallOutput(['ectool', 'temps', 'all']).AndReturn(_MOCK_TEMPS)
    self.mox.ReplayAll()
    self.assertEquals(self.thermal.GetTemperatures(), [0, 10, None, 30, 40, 50])
    self.mox.VerifyAll()

  def testGetTemperatureMainIndex(self):
    _MOCK_TEMPS_INFO = '\n'.join([
        '0: 0 I2C_CPU-Die',
        '1: 255 I2C_CPU-Object',
        '2: 1 I2C_PCH-Die',
        '3: 2 I2C_PCH-Object',
        '4: 1 I2C_DDR-Die',
        '5: 2 I2C_DDR-Object',
        '6: 1 I2C_Charger-Die',
        '7: 2 I2C_Charger-Object',
        '8: 1 ECInternal',
        '9: 0 PECI'
    ])
    self.board.CallOutput(
        ['ectool', 'tempsinfo', 'all']).AndReturn(_MOCK_TEMPS_INFO)
    self.mox.ReplayAll()
    self.assertEquals(self.thermal.GetMainTemperatureIndex(), 9)
    # The second call should return the cached data
    self.assertEquals(self.thermal.GetMainTemperatureIndex(), 9)
    # Sensor names should also be cached
    self.thermal.GetTemperatureSensorNames()
    self.mox.VerifyAll()

  def testGetTemperatureSensorNamesReturnLocalCache(self):
    _MOCK_TEMPS_INFO = '\n'.join([
        '0: 0 I2C_CPU-Die',
        '1: 255 I2C_CPU-Object',
        '2: 1 I2C_PCH-Die',
        '3: 2 I2C_PCH-Object',
        '4: 1 I2C_DDR-Die',
        '5: 2 I2C_DDR-Object',
        '6: 1 I2C_Charger-Die',
        '7: 2 I2C_Charger-Object',
        '8: 1 ECInternal',
        '9: 0 PECI'
    ])
    self.board.CallOutput(
        ['ectool', 'tempsinfo', 'all']).AndReturn(_MOCK_TEMPS_INFO)
    self.mox.ReplayAll()

    names = self.thermal.GetTemperatureSensorNames()
    # Modify the cached data and it shouldn't affect the following calls.
    names.append('CPU')

    # The second call should return the original local cached data
    # without 'CPU'.
    self.assertTrue('CPU' not in self.thermal.GetTemperatureSensorNames())
    self.mox.VerifyAll()

  def testGetFanRPM(self):
    _MOCK_FAN_RPM = 'Fan 0 RPM: 2974\n'
    self.board.CallOutput(['ectool', 'pwmgetfanrpm']).AndReturn(_MOCK_FAN_RPM)
    self.mox.ReplayAll()
    self.assertEquals(self.thermal.GetFanRPM(), [2974])
    self.mox.VerifyAll()

  def testSetFanRPM(self):
    self.board.CheckCall(['ectool', 'pwmsetfanrpm', '12345'])
    self.board.CheckCall(['ectool', 'pwmsetfanrpm', '1', '12345'])
    self.mox.ReplayAll()
    self.thermal.SetFanRPM(12345)
    self.thermal.SetFanRPM(12345, fan_id=1)
    self.mox.VerifyAll()

  def testSetFanRPMAuto(self):
    self.board.CheckCall(['ectool', 'autofanctrl'])
    self.board.CheckCall(['ectool', 'autofanctrl', '1'])
    self.mox.ReplayAll()
    self.thermal.SetFanRPM(self.thermal.AUTO)
    self.thermal.SetFanRPM(self.thermal.AUTO, fan_id=1)
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
