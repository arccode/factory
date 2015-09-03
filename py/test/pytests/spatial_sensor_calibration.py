# -*- coding: utf-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Perform calibration on spatial sensors

Spatial sensors are sensors with X, Y, Z values such as accelerometer or
gyroscope.

The step for calibration is as follows:
1 - Put the device on a flat table, facing up.
2 - Issue a command to calibrate them:
  echo 1 > /sys/bus/iio/devices/iio:deviceX/calibrate
  X being the ids of the accel and gyro.
3 - Retrieve the calibration offsets
  cat /sys/bus/iio/devices/iio:deviceX/in_(accel|gyro)_(x|y|z)_calibbias
4 - Save them in VPD.
"""

import os
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.utils import sync_utils


DEFAULT_NAME = ('Accelerometer', u'加速度计')
DEFAULT_SYSPATH = '/sys/bus/iio/devices/iio:device0/'
DEFAULT_ENTRY_TEMPLATE = 'in_accel_%s_calibbias'


class SpatialSensorCalibration(unittest.TestCase):
  ARGS = [
      Arg('timeout_secs', int, 'Timeout in seconds when waiting for device.',
          default=60),
      Arg('name', tuple, 'Name of the device to calibrate.',
          default=DEFAULT_NAME),
      Arg('device_path', str, 'Path to the device IIO sysfs entry.',
          default=DEFAULT_SYSPATH),
      Arg('calibbias_entry_template', str,
          'Template for the sysfs calibbias value entry.',
          default=DEFAULT_ENTRY_TEMPLATE),
      Arg('stabilize_time', int, 'Time to wait until calibbias stabilize.',
          default=1),
  ]

  def setUp(self):
    ui = test_ui.UI()
    self._template = ui_templates.OneSection(ui)

  def runTest(self):
    self.WaitForDevice()

    self._template.SetState(test_ui.MakeLabel(
        'Calibrating %s...' % self.args.name[0],
        u'正在校正 %s...' % self.args.name[1]))

    self.EnableAutoCalibration(self.args.device_path)
    self.RetrieveCalibbias()

  def WaitForDevice(self):
    self._template.SetState(test_ui.MakeLabel('Waiting for device...',
                                              u'正在等待装置...'))
    sync_utils.WaitFor(self.dut.IsReady, self.args.timeout_secs)
    if not self.dut.IsReady():
      self.fail('failed to find deivce')

  def EnableAutoCalibration(self, path):
    RETRIES = 5
    for i in range(RETRIES):
      try:
        self.dut.Write(self.dut.path.join(path, 'calibrate'), '1')
      except Exception:
        factory.console.info('calibrate activation failed, retrying')
        time.sleep(1)
      else:
        break
    else:
        raise RuntimeError('calibrate activation failed')
    time.sleep(self.args.stabilize_time)

  def ReadCalibbiasAndWriteVPD(self, axis):
    self._template.SetState(test_ui.MakeLabel('Writing calibration data...',
                                              u'正在写入校正结果...'))
    key = self.args.calibbias_entry_template % axis
    value = self.dut.Read(self.dut.path.join(self.args.device_path, key))

    self.dut.CheckCall('vpd -s %s=%s' % (key, value))

  def RetrieveCalibbias(self):
    for axis in ['x', 'y', 'z']:
      self.ReadCalibbiasAndWriteVPD(axis)
