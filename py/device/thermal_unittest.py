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


class CoreTempSensorTest(unittest.TestCase):
  """Unittest for CoreTempSensor."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(board.DeviceBoard)
    self.board.path = os.path
    self.sensor = thermal.CoreTempSensors(self.board)
    self.glob_input = '/sys/devices/platform/coretemp.*/temp*_input'
    self.mock_glob = [
        '/sys/devices/platform/coretemp.0/temp1_input',
        '/sys/devices/platform/coretemp.0/temp2_input']
    self.mock_files = [
        ('/sys/devices/platform/coretemp.0/temp1_label', 'Package 0'),
        ('/sys/devices/platform/coretemp.0/temp2_label', 'Core 0')]

  def tearDown(self):
    self.mox.UnsetStubs()

  def mockProbe(self):
    self.board.Glob(self.glob_input).AndReturn(self.mock_glob)
    for name, value in self.mock_files:
      self.board.ReadFile(name).InAnyOrder().AndReturn(value)

  def testGetSensors(self):
    self.mockProbe()
    self.mox.ReplayAll()
    self.assertEquals(self.sensor.GetSensors(), {
        'coretemp.0 Package 0': '/sys/devices/platform/coretemp.0/temp1_input',
        'coretemp.0 Core 0': '/sys/devices/platform/coretemp.0/temp2_input',
    })
    self.mox.VerifyAll()

  def testGetMainSensorName(self):
    self.mockProbe()
    self.mox.ReplayAll()
    self.assertEquals(self.sensor.GetMainSensorName(), 'coretemp.0 Package 0')
    self.mox.VerifyAll()

  def testGetValue(self):
    self.mockProbe()
    self.board.ReadFile(
        '/sys/devices/platform/coretemp.0/temp2_input').AndReturn('50000')
    self.mox.ReplayAll()
    self.assertEquals(self.sensor.GetValue('coretemp.0 Core 0'), 50)
    self.mox.VerifyAll()

  def testGetAllValues(self):
    self.mockProbe()
    values = ['52000', '37000']
    for i, value in enumerate(values):
      self.board.ReadFile(self.mock_glob[i]).InAnyOrder().AndReturn(value)
    self.mox.ReplayAll()
    self.assertEquals(self.sensor.GetAllValues(), {
        'coretemp.0 Package 0': 52,
        'coretemp.0 Core 0': 37})
    self.mox.VerifyAll()


class ThermalZoneSensors(unittest.TestCase):
  """Unittest for ThermalZoneSensors."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(board.DeviceBoard)
    self.board.path = os.path
    self.sensor = thermal.ThermalZoneSensors(self.board)
    self.glob_input = '/sys/class/thermal/thermal_zone*'
    self.mock_glob = ['/sys/class/thermal/thermal_zone0']
    self.mock_files = [('/sys/class/thermal/thermal_zone0/type', 'CPU')]

  def tearDown(self):
    self.mox.UnsetStubs()

  def testAll(self):
    self.board.Glob(self.glob_input).AndReturn(self.mock_glob)
    for name, value in self.mock_files:
      self.board.ReadFile(name).AndReturn(value)
    self.board.ReadFile('/sys/class/thermal/thermal_zone0/temp').AndReturn(
        '37000')
    self.board.ReadFile('/sys/class/thermal/thermal_zone0/temp').AndReturn(
        '38000')
    self.mox.ReplayAll()
    self.assertEquals(self.sensor.GetMainSensorName(), 'thermal_zone0 CPU')
    self.assertEquals(self.sensor.GetValue('thermal_zone0 CPU'), 37)
    self.assertEquals(self.sensor.GetAllValues(), {'thermal_zone0 CPU': 38})
    self.mox.VerifyAll()


class ECToolTemperatureSensors(unittest.TestCase):
  """Unittest for ECToolTemperatureSensors."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(board.DeviceBoard)
    self.board.path = os.path
    self.sensor = thermal.ECToolTemperatureSensors(self.board)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testAll(self):
    self.board.CallOutput('ectool tempsinfo all').AndReturn('\n'.join([
        '0: 0 I2C_CPU-Die',
        '1: 1 ECInternal',
        '2: 0 PECI']))
    self.board.CallOutput('ectool temps 2').AndReturn('323')
    self.board.CallOutput('ectool temps all').AndReturn('\n'.join([
        '0: 273',
        '1: 283',
        '2: 293']))

    self.mox.ReplayAll()
    self.assertEquals(self.sensor.GetMainSensorName(), None)
    self.assertEquals(self.sensor.GetSensors(), {
        'ectool I2C_CPU-Die': '0',
        'ectool ECInternal': '1',
        'ectool PECI': '2',
    })
    self.assertEquals(self.sensor.GetValue('ectool PECI'), 50)
    self.assertEquals(self.sensor.GetAllValues(), {
        'ectool I2C_CPU-Die': 0,
        'ectool ECInternal': 10,
        'ectool PECI': 20})
    self.mox.VerifyAll()


class ThermalTest(unittest.TestCase):
  """Unittest for Thermal."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(board.DeviceBoard)
    self.board.path = os.path
    self.thermal = thermal.Thermal(self.board)
    self.coretemp1_path = '/sys/devices/platform/coretemp.0/temp1_input'

  def tearDown(self):
    self.mox.UnsetStubs()

  def mockSetup(self):
    self.board.Glob('/sys/devices/platform/coretemp.*/temp*_input').AndReturn([
        self.coretemp1_path])
    self.board.ReadFile(
        '/sys/devices/platform/coretemp.0/temp1_label').AndReturn('Package 0')
    self.board.CallOutput('ectool tempsinfo all').AndReturn('1: 1 ECInternal')

  def testNewDictAPIs(self):
    self.mockSetup()
    self.board.ReadFile(self.coretemp1_path).AndReturn('37000')
    self.board.ReadFile(self.coretemp1_path).AndReturn('38000')
    self.board.CallOutput('ectool temps 1').AndReturn(
        'Reading temperature...332')
    self.mox.ReplayAll()
    self.assertEquals(self.thermal.GetMainSensorName(), 'coretemp.0 Package 0')
    self.assertEquals(self.thermal.GetMainTemperature(), 37)
    self.assertEquals(
        self.thermal.GetTemperature(self.thermal.GetMainSensorName()), 38)
    self.assertEquals(
        self.thermal.GetTemperature('ectool ECInternal'), 59)
    self.mox.VerifyAll()

  def testOldListAPIs(self):
    self.mockSetup()
    self.board.ReadFile(self.coretemp1_path).InAnyOrder().AndReturn('37000')
    self.board.CallOutput('ectool temps all').InAnyOrder().AndReturn('1: 331')
    self.board.ReadFile(self.coretemp1_path).InAnyOrder().AndReturn('69000')
    self.board.CallOutput('ectool temps all').InAnyOrder().AndReturn(
        '1: broken')
    self.mox.ReplayAll()
    self.assertEquals(self.thermal.GetTemperatureSensorNames(),
                      ['ectool ECInternal', 'coretemp.0 Package 0'])
    self.assertEquals(self.thermal.GetMainTemperatureIndex(), 1)
    self.assertEquals(self.thermal.GetTemperatures(), [58, 37])
    self.assertEquals(self.thermal.GetTemperatures(), [None, 69])
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
