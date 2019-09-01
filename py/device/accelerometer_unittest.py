#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittest for accelerometer module."""

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.device import accelerometer


def MockControllerInit(self, device, unused_name, location):
  # pylint: disable=protected-access
  self._device = device
  self.location = location
  self.signal_names = ['in_accel_x', 'in_accel_y', 'in_accel_z']


class AccelerometerTest(unittest.TestCase):
  # pylint: disable=protected-access

  def testScanType(self):
    scan_type = accelerometer._ParseIIOBufferScanType('le:s12/16>>4')
    self.assertEqual(scan_type.sign, 's')
    self.assertEqual(scan_type.realbits, 12)
    self.assertEqual(scan_type.storagebits, 16)
    self.assertEqual(scan_type.shift, 4)
    self.assertEqual(scan_type.repeat, None)
    self.assertEqual(scan_type.endianness, 'le')

  def testScanTypeWithRepeat(self):
    scan_type = accelerometer._ParseIIOBufferScanType('le:s12/16X2>>4')
    self.assertEqual(scan_type.sign, 's')
    self.assertEqual(scan_type.realbits, 12)
    self.assertEqual(scan_type.storagebits, 16)
    self.assertEqual(scan_type.shift, 4)
    self.assertEqual(scan_type.repeat, 2)
    self.assertEqual(scan_type.endianness, 'le')

  def testIsWithinOffsetRange(self):
    is_within_offset_range = (
        accelerometer.AccelerometerController.IsWithinOffsetRange)
    self.assertTrue(is_within_offset_range(
        {'x': 0.1, 'y': -0.1, 'z': -10.0},
        {'x': 0, 'y': 0, 'z': -1},
        (0.3, 0.3)))

    # y out of range
    self.assertFalse(is_within_offset_range(
        {'x': 0.1, 'y': -0.4, 'z': -10.0},
        {'x': 0, 'y': 0, 'z': -1},
        (0.3, 0.3)))

  @mock.patch.multiple(accelerometer.AccelerometerController,
                       __init__=MockControllerInit,
                       _GetSysfsValue=lambda self, path: '0')
  def testCalculateCalibrationBias(self):
    controller = accelerometer.AccelerometerController(
        None, 'cros-ec-accel', 'base')
    calib_bias = controller.CalculateCalibrationBias(
        {'x': 0.1, 'y': -0.1, 'z': -10.0},
        {'x': 0, 'y': 0, 'z': -1})
    self.assertAlmostEqual(calib_bias['x_base_calibbias'], -0.1)
    self.assertAlmostEqual(calib_bias['y_base_calibbias'], 0.1)
    self.assertAlmostEqual(calib_bias['z_base_calibbias'], 0.19335)

  @mock.patch.multiple(accelerometer.AccelerometerController,
                       __init__=MockControllerInit,
                       _GetSysfsValue=lambda self, path: '512')
  def testCalculateCalibrationBiasWithExistingCalibbias(self):
    # Old bias is set to 512 = 0.5G = 4.803325 for all axises, and calibrated
    # data is (0.1, -0.1, -10).
    # => raw data = (0.1 - 4.803325, -0.1 - 4.803325, -10 - 4.803325)
    #             = (-4.803325, 5.003325, -14.803325)
    # => bias = (4.803325, 5.003325, 5.096675).
    controller = accelerometer.AccelerometerController(
        None, 'cros-ec-accel', 'base')
    calib_bias = controller.CalculateCalibrationBias(
        {'x': 0.1, 'y': -0.1, 'z': -10.0},
        {'x': 0, 'y': 0, 'z': -1})
    self.assertAlmostEqual(calib_bias['x_base_calibbias'], 4.803325)
    self.assertAlmostEqual(calib_bias['y_base_calibbias'], 5.003325)
    self.assertAlmostEqual(calib_bias['z_base_calibbias'], 5.096675)

  @mock.patch.multiple(accelerometer.AccelerometerController,
                       __init__=MockControllerInit,
                       _SetSysfsValue=mock.DEFAULT)
  def testUpdateCalibrationBias(self, **mocks):
    mock_dut = mock.Mock()
    controller = accelerometer.AccelerometerController(
        mock_dut, 'cros-ec-accel', 'base')
    controller.UpdateCalibrationBias({
        'in_accel_x_base_calibbias': 0.1,
        'in_accel_y_base_calibbias': -0.2,
        'in_accel_z_base_calibbias': 0.3})
    mock_dut.vpd.ro.Update.assert_called_once_with({
        'in_accel_x_base_calibbias': '10',
        'in_accel_y_base_calibbias': '-20',
        'in_accel_z_base_calibbias': '31'})
    mocks['_SetSysfsValue'].assert_any_call(
        'in_accel_x_calibbias', '10')
    mocks['_SetSysfsValue'].assert_any_call(
        'in_accel_y_calibbias', '-20')
    mocks['_SetSysfsValue'].assert_any_call(
        'in_accel_z_calibbias', '31')


if __name__ == '__main__':
  unittest.main()
