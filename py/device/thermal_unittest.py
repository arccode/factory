#!/usr/bin/python
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for Thermal component."""

from __future__ import print_function

import mox
import os.path
import subprocess
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.device import thermal
from cros.factory.device import board


class ECToolThermalTest(unittest.TestCase):
  """Unittest for ECToolThermal."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(board.DeviceBoard)
    self.thermal = thermal.ECToolThermal(self.board)

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


class SysFSThermalTest(unittest.TestCase):
  """Unittest for SysFSThermal."""

  _MOCK_ZONES = [
      '/sys/class/thermal/thermal_zone0',
      '/sys/class/thermal/thermal_zone1']

  _FANS_INFO = [{'fan_id': None, 'path': '/sys/fan'}]

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(board.DeviceBoard)
    self.board.path = os.path

  def tearDown(self):
    self.mox.UnsetStubs()

  def testGetTemperatures(self):
    thermal_obj = thermal.SysFSThermal(self.board, 'cpu')

    self.board.Glob('/sys/class/thermal/thermal_zone*').AndReturn(
        self._MOCK_ZONES)
    self.board.ReadFile('/sys/class/thermal/thermal_zone0/temp').AndReturn(
        55000)
    self.board.ReadFile('/sys/class/thermal/thermal_zone1/temp').AndReturn(
        66000)

    self.mox.ReplayAll()
    self.assertEquals(thermal_obj.GetTemperatures(), [55, 66])
    self.mox.VerifyAll()

  def testGetTemperaturesFail(self):
    thermal_obj = thermal.SysFSThermal(self.board, 'cpu')

    self.board.Glob('/sys/class/thermal/thermal_zone*').AndReturn(
        self._MOCK_ZONES)
    self.board.ReadFile('/sys/class/thermal/thermal_zone0/temp').AndReturn(
        55000)
    self.board.ReadFile('/sys/class/thermal/thermal_zone1/temp').AndRaise(
        subprocess.CalledProcessError(1, '', ''))

    self.mox.ReplayAll()
    self.assertEquals(thermal_obj.GetTemperatures(), [55, None])
    self.mox.VerifyAll()

  def testGetTemperatureSensorNames(self):
    thermal_obj = thermal.SysFSThermal(self.board, 'cpu')

    self.board.Glob('/sys/class/thermal/thermal_zone*').AndReturn(
        self._MOCK_ZONES)
    self.board.ReadFile('/sys/class/thermal/thermal_zone0/type').AndReturn(
        'cpu')
    self.board.ReadFile('/sys/class/thermal/thermal_zone1/type').AndReturn(
        'emmc_therm')

    self.mox.ReplayAll()
    self.assertEquals(thermal_obj.GetTemperatureSensorNames(),
                      ['cpu', 'emmc_therm'])
    self.mox.VerifyAll()

  def testGetTemperatureSensorNamesFail(self):
    thermal_obj = thermal.SysFSThermal(self.board, 'cpu')

    self.board.Glob('/sys/class/thermal/thermal_zone*').AndReturn(
        self._MOCK_ZONES)
    self.board.ReadFile('/sys/class/thermal/thermal_zone0/type').AndRaise(
        subprocess.CalledProcessError(1, '', ''))

    self.mox.ReplayAll()
    self.assertRaises(thermal.SysFSThermal.Error,
                      thermal_obj.GetTemperatureSensorNames)
    self.mox.VerifyAll()

  def testGetMainTemperatureIndex(self):
    thermal_obj = thermal.SysFSThermal(self.board, 'cpu')

    self.board.Glob('/sys/class/thermal/thermal_zone*').AndReturn(
        self._MOCK_ZONES)
    self.board.ReadFile('/sys/class/thermal/thermal_zone0/type').AndReturn(
        'cpu')
    self.board.ReadFile('/sys/class/thermal/thermal_zone1/type').AndReturn(
        'emmc_therm')

    self.mox.ReplayAll()
    self.assertEquals(thermal_obj.GetMainTemperatureIndex(), 0)
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
