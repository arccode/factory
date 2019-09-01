#!/usr/bin/env python2
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for Thermal component."""

from __future__ import print_function

import fnmatch
import os.path
import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.device import thermal
from cros.factory.device import types


_CORETEMP_PREFIX = '/sys/devices/platform/coretemp.'


class _FakeGlob(object):
  """A simple glob class for unittest."""
  def __init__(self, paths):
    self._paths = []
    for path in paths:
      assert path.startswith('/'), 'Only absolute paths are acceptable'
      splitted_path = path.split('/')[1:]
      ancestor_path = ''
      for dirname in splitted_path:
        self._paths.append(ancestor_path + '/')
        self._paths.append(ancestor_path + '/' + dirname)
        ancestor_path += '/' + dirname
    self._paths = list(set(self._paths))

  def Glob(self, pattern):
    pattern_parts = pattern.split('/')
    return [path for path in self._paths
            if self._Match(path.split('/'), pattern_parts)]

  def _Match(self, fnames, patterns):
    if (len(fnames) != len(patterns) or
        not all(fnmatch.fnmatch(fname, pattern)
                for fname, pattern in zip(fnames, patterns))):
      return False
    return True


class CoreTempSensorTest(unittest.TestCase):
  """Unittest for CoreTempSensor."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(types.DeviceBoard)
    self.board.path = os.path
    self.sensor = thermal.CoreTempSensors(self.board)
    self._glob = _FakeGlob([_CORETEMP_PREFIX + suffix for suffix in [
        '0/temp1_input',
        '0/temp1_label',
        '0/temp1_crit',
        '0/temp2_input',
        '0/temp2_label',
        '0/temp2_crit',
        '1/hwmon/hwmon0/temp1_input',
        '1/hwmon/hwmon0/temp1_label',
        '1/hwmon/hwmon0/temp1_crit']])
    self.mock_files = [
        (_CORETEMP_PREFIX + '0/temp1_label', 'Package 0'),
        (_CORETEMP_PREFIX + '0/temp2_label', 'Core 0'),
        (_CORETEMP_PREFIX + '1/hwmon/hwmon0/temp1_label', 'Core X')]
    self.board.Glob = self._glob.Glob

  def tearDown(self):
    self.mox.UnsetStubs()

  def mockProbe(self):
    for name, value in self.mock_files:
      self.board.ReadFile(name).InAnyOrder().AndReturn(value)

  def testGetSensors(self):
    self.mockProbe()
    self.mox.ReplayAll()
    self.assertEquals(self.sensor.GetSensors(), {
        'coretemp.0 Package 0': _CORETEMP_PREFIX + '0/temp1_input',
        'coretemp.0 Core 0': _CORETEMP_PREFIX + '0/temp2_input',
        'coretemp.1 Core X': _CORETEMP_PREFIX + '1/hwmon/hwmon0/temp1_input',
    })
    self.mox.VerifyAll()

  def testGetMainSensorName(self):
    self.mockProbe()
    self.mox.ReplayAll()
    self.assertEquals(self.sensor.GetMainSensorName(), 'coretemp.0 Package 0')
    self.mox.VerifyAll()

  def testGetValue(self):
    self.mockProbe()
    self.board.ReadFile(_CORETEMP_PREFIX + '0/temp2_input').AndReturn('50000')
    self.mox.ReplayAll()
    self.assertEquals(self.sensor.GetValue('coretemp.0 Core 0'), 50)
    self.mox.VerifyAll()

  def testGetAllValues(self):
    self.mockProbe()
    values = {
        '0/temp1_input': '52000',
        '0/temp2_input': '37000',
        '1/hwmon/hwmon0/temp1_input': '47000'}
    for suffix, value in values.iteritems():
      self.board.ReadFile(
          _CORETEMP_PREFIX + suffix).InAnyOrder().AndReturn(value)
    self.mox.ReplayAll()
    self.assertEquals(self.sensor.GetAllValues(), {'coretemp.0 Package 0': 52,
                                                   'coretemp.0 Core 0': 37,
                                                   'coretemp.1 Core X': 47})
    self.mox.VerifyAll()

  def testGetCriticalValue(self):
    self.mockProbe()
    self.board.ReadFile(_CORETEMP_PREFIX + '0/temp2_crit').AndReturn('97000')
    self.mox.ReplayAll()
    self.assertEquals(self.sensor.GetCriticalValue('coretemp.0 Core 0'), 97)
    self.mox.VerifyAll()

class ThermalZoneSensors(unittest.TestCase):
  """Unittest for ThermalZoneSensors."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(types.DeviceBoard)
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
    self.board = self.mox.CreateMock(types.DeviceBoard)
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

  def testGetAllValues(self):
    self.board.CallOutput('ectool tempsinfo all').AndReturn('\n'.join([
        '0: 0 TMP432_Internal',
        '1: 1 TMP432_Sensor_1',
        '2: 2 TMP432_Sensor_2']))
    self.board.CallOutput('ectool temps all').AndReturn('\n'.join([
        '0: 329 K',
        '1: 327 K',
        '2: 273 K']))
    self.mox.ReplayAll()
    self.assertEquals(self.sensor.GetSensors(), {
        'ectool TMP432_Internal': '0',
        'ectool TMP432_Sensor_1': '1',
        'ectool TMP432_Sensor_2': '2',
    })
    self.assertEquals(self.sensor.GetAllValues(), {
        'ectool TMP432_Internal': 56,
        'ectool TMP432_Sensor_1': 54,
        'ectool TMP432_Sensor_2': 0})
    self.mox.VerifyAll()

class ThermalTest(unittest.TestCase):
  """Unittest for Thermal."""

  def setUp(self):
    self.mox = mox.Mox()
    self.board = self.mox.CreateMock(types.DeviceBoard)
    self.board.path = os.path
    self.thermal = thermal.Thermal(self.board)
    self.coretemp1_path = _CORETEMP_PREFIX + '0/temp1_input'
    self.coretemp1crit_path = _CORETEMP_PREFIX + '0/temp1_crit'
    self.glob = _FakeGlob([_CORETEMP_PREFIX + suffix for suffix in [
        '0/temp1_input', '0/temp1_label', '0/temp1_crit']])

  def tearDown(self):
    self.mox.UnsetStubs()

  def mockSetup(self):
    self.board.Glob = self.glob.Glob
    self.board.ReadFile(
        _CORETEMP_PREFIX + '0/temp1_label').AndReturn('Package 0')
    self.board.CallOutput('ectool tempsinfo all').AndReturn('1: 1 ECInternal')

  def testNewDictAPIs(self):
    self.mockSetup()
    self.board.ReadFile(self.coretemp1_path).AndReturn('37000')
    self.board.ReadFile(self.coretemp1_path).AndReturn('38000')
    self.board.CallOutput('ectool temps 1').AndReturn(
        'Reading temperature...332')
    self.board.ReadFile(self.coretemp1_path).AndReturn('34000')
    self.board.CallOutput('ectool temps all').AndReturn(
        '1: 331')
    self.board.ReadFile(self.coretemp1crit_path).AndReturn('104000')
    self.mox.ReplayAll()
    self.assertEquals(self.thermal.GetMainSensorName(), 'coretemp.0 Package 0')
    self.assertItemsEqual(self.thermal.GetAllSensorNames(),
                          ['coretemp.0 Package 0', 'ectool ECInternal'])
    self.assertEquals(self.thermal.GetTemperature(), 37)
    self.assertEquals(
        self.thermal.GetTemperature(self.thermal.GetMainSensorName()), 38)
    self.assertEquals(
        self.thermal.GetTemperature('ectool ECInternal'), 59)
    self.assertItemsEqual(self.thermal.GetAllTemperatures(),
                          {'coretemp.0 Package 0': 34,
                           'ectool ECInternal': 58})
    self.assertEqual(
        self.thermal.GetCriticalTemperature('coretemp.0 Package 0'), 104)
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
