#!/usr/bin/env python3
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for Thermal component."""

import fnmatch
import os.path
import unittest
from unittest import mock

from cros.factory.device import device_types
from cros.factory.device import thermal


_CORETEMP_PREFIX = '/sys/devices/platform/coretemp.'


class _FakeGlob:
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
    self.board = mock.Mock(device_types.DeviceBoard)
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
    self.mock_files = {
        _CORETEMP_PREFIX + '0/temp1_label': 'Package 0',
        _CORETEMP_PREFIX + '0/temp2_label': 'Core 0',
        _CORETEMP_PREFIX + '1/hwmon/hwmon0/temp1_label': 'Core X'}
    self.board.Glob = self._glob.Glob

  def mockProbe(self):
    def ReadFileSideEffect(*args, **unused_kwargs):
      return self.mock_files[args[0]]

    self.board.ReadFile.side_effect = ReadFileSideEffect

  def testGetSensors(self):
    self.mockProbe()
    self.assertEqual(self.sensor.GetSensors(), {
        'coretemp.0 Package 0': _CORETEMP_PREFIX + '0/temp1_input',
        'coretemp.0 Core 0': _CORETEMP_PREFIX + '0/temp2_input',
        'coretemp.1 Core X': _CORETEMP_PREFIX + '1/hwmon/hwmon0/temp1_input',
    })

  def testGetMainSensorName(self):
    self.mockProbe()
    self.assertEqual(self.sensor.GetMainSensorName(), 'coretemp.0 Package 0')

  def testGetValue(self):
    self.mock_files[_CORETEMP_PREFIX + '0/temp2_input'] = '50000'
    self.mockProbe()
    self.assertEqual(self.sensor.GetValue('coretemp.0 Core 0'), 50)

  def testGetAllValues(self):
    values = {
        '0/temp1_input': '52000',
        '0/temp2_input': '37000',
        '1/hwmon/hwmon0/temp1_input': '47000'}
    for suffix, value in values.items():
      self.mock_files[_CORETEMP_PREFIX + suffix] = value
    self.mockProbe()
    self.assertEqual(self.sensor.GetAllValues(), {'coretemp.0 Package 0': 52,
                                                  'coretemp.0 Core 0': 37,
                                                  'coretemp.1 Core X': 47})

  def testGetCriticalValue(self):
    self.mock_files[_CORETEMP_PREFIX + '0/temp2_crit'] = '97000'
    self.mockProbe()
    self.assertEqual(self.sensor.GetCriticalValue('coretemp.0 Core 0'), 97)


class ThermalZoneSensors(unittest.TestCase):
  """Unittest for ThermalZoneSensors."""

  def setUp(self):
    self.board = mock.Mock(device_types.DeviceBoard)
    self.board.path = os.path
    self.sensor = thermal.ThermalZoneSensors(self.board)
    self.glob_input = '/sys/class/thermal/thermal_zone*'
    self.mock_glob = ['/sys/class/thermal/thermal_zone0']

  def testAll(self):
    self.board.ReadFile.side_effect = ['CPU', '37000', '38000']
    self.board.Glob.return_value = self.mock_glob

    self.assertEqual(self.sensor.GetMainSensorName(), 'thermal_zone0 CPU')
    self.board.ReadFile.assert_called_with(
        '/sys/class/thermal/thermal_zone0/type')

    self.assertEqual(self.sensor.GetValue('thermal_zone0 CPU'), 37)
    self.board.ReadFile.assert_called_with(
        '/sys/class/thermal/thermal_zone0/temp')
    self.board.ReadFile.reset_mock()

    self.assertEqual(self.sensor.GetAllValues(), {'thermal_zone0 CPU': 38})
    self.board.ReadFile.assert_called_with(
        '/sys/class/thermal/thermal_zone0/temp')

    self.board.Glob.assert_called_once_with(self.glob_input)


class ECToolTemperatureSensors(unittest.TestCase):
  """Unittest for ECToolTemperatureSensors."""

  def setUp(self):
    self.board = mock.Mock(device_types.DeviceBoard)
    self.board.path = os.path
    self.sensor = thermal.ECToolTemperatureSensors(self.board)

  def testAll(self):
    call_output_mapping = {
        'ectool tempsinfo all':
            '\n'.join(['0: 0 I2C_CPU-Die', '1: 1 ECInternal', '2: 0 PECI']),
        'ectool temps 1':
            '313 K',
        'ectool temps 2':
            '323',
        'ectool temps all':
            '\n'.join(['0: 273', '1: 283', '2: 293'])
    }

    def CallOutputSideEffect(*args, **unused_kwargs):
      return call_output_mapping[args[0]]

    self.board.CallOutput.side_effect = CallOutputSideEffect

    self.assertEqual(self.sensor.GetMainSensorName(), None)
    self.assertEqual(self.sensor.GetSensors(), {
        'ectool I2C_CPU-Die': '0',
        'ectool ECInternal': '1',
        'ectool PECI': '2',
    })
    self.assertEqual(self.sensor.GetValue('ectool PECI'), 50)
    self.assertEqual(self.sensor.GetAllValues(), {
        'ectool I2C_CPU-Die': 0,
        'ectool ECInternal': 10,
        'ectool PECI': 20})

  def testGetAllValues(self):
    call_output_mapping = {
        'ectool tempsinfo all': '\n'.join([
            '0: 0 TMP432_Internal',
            '1: 1 TMP432_Sensor_1',
            '2: 2 TMP432_Sensor_2']),
        'ectool temps all': '\n'.join(['0: 329 K', '1: 327 K', '2: 273 K'])}

    def CallOutputSideEffect(*args, **unused_kwargs):
      return call_output_mapping[args[0]]

    self.board.CallOutput.side_effect = CallOutputSideEffect

    self.assertEqual(self.sensor.GetSensors(), {
        'ectool TMP432_Internal': '0',
        'ectool TMP432_Sensor_1': '1',
        'ectool TMP432_Sensor_2': '2',
    })
    self.assertEqual(self.sensor.GetAllValues(), {
        'ectool TMP432_Internal': 56,
        'ectool TMP432_Sensor_1': 54,
        'ectool TMP432_Sensor_2': 0})

class ThermalTest(unittest.TestCase):
  """Unittest for Thermal."""

  def setUp(self):
    self.board = mock.Mock(device_types.DeviceBoard)
    self.board.path = os.path
    self.thermal = thermal.Thermal(self.board)
    self.coretemp1_path = _CORETEMP_PREFIX + '0/temp1_input'
    self.coretemp1crit_path = _CORETEMP_PREFIX + '0/temp1_crit'
    self.glob = _FakeGlob([_CORETEMP_PREFIX + suffix for suffix in [
        '0/temp1_input', '0/temp1_label', '0/temp1_crit']])

  def mockSetup(self):
    self.board.Glob = self.glob.Glob

  def testNewDictAPIs(self):
    self.mockSetup()

    call_output_mapping = {
        'ectool tempsinfo all': '1: 1 ECInternal',
        'ectool temps 1': 'Reading temperature...332',
        'ectool temps all': '1: 331'}

    def CallOutputSideEffect(*args, **unused_kwargs):
      return call_output_mapping[args[0]]

    self.board.CallOutput.side_effect = CallOutputSideEffect
    self.board.ReadFile.side_effect = [
        'Package 0', '37000', '38000', '34000', '104000']

    self.assertEqual(self.thermal.GetMainSensorName(), 'coretemp.0 Package 0')
    self.assertCountEqual(
        self.thermal.GetAllSensorNames(),
        ['coretemp.0 Package 0', 'ectool ECInternal'])
    self.board.ReadFile.assert_called_once_with(
        _CORETEMP_PREFIX + '0/temp1_label')
    self.board.ReadFile.reset_mock()

    self.assertEqual(self.thermal.GetTemperature(), 37)
    self.board.ReadFile.assert_called_once_with(self.coretemp1_path)
    self.board.ReadFile.reset_mock()

    self.assertEqual(
        self.thermal.GetTemperature(self.thermal.GetMainSensorName()), 38)
    self.board.ReadFile.assert_called_once_with(self.coretemp1_path)
    self.board.ReadFile.reset_mock()

    self.assertEqual(
        self.thermal.GetTemperature('ectool ECInternal'), 59)
    self.assertCountEqual(
        self.thermal.GetAllTemperatures(),
        {'coretemp.0 Package 0': 34,
         'ectool ECInternal': 58})
    self.board.ReadFile.assert_called_once_with(self.coretemp1_path)
    self.board.ReadFile.reset_mock()

    self.assertEqual(
        self.thermal.GetCriticalTemperature('coretemp.0 Package 0'), 104)
    self.board.ReadFile.assert_called_once_with(self.coretemp1crit_path)


if __name__ == '__main__':
  unittest.main()
