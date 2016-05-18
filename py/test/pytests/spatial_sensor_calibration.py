# -*- coding: utf-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Perform calibration on spatial sensors

Spatial sensors are sensors with X, Y, Z values such as accelerometer or
gyroscope.

The step for calibration is as follows:
1) Put the device on a flat table, facing up.

2) Issue a command to calibrate them:

  - echo 1 > /sys/bus/iio/devices/iio:deviceX/calibrate
  - X being the ids of the accel and gyro.

3) Retrieve the calibration offsets

  - cat /sys/bus/iio/devices/iio:deviceX/in_(accel|gyro)_(x|y|z)_calibbias

4) Save them in VPD.
"""

import threading
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils import sync_utils
from cros.factory.utils.arg_utils import Arg


DEFAULT_NAME = ('Accelerometer', u'加速度计')
DEFAULT_SYSPATH = '/sys/bus/iio/devices/iio:device0/'
DEFAULT_ENTRY_TEMPLATE = 'in_accel_%s_calibbias'

CSS = """
body { font-size: 2em; }
.error { color: red; }
"""


class InvalidPositionError(Exception):
  pass


class SpatialSensorCalibration(unittest.TestCase):
  ARGS = [
      Arg('timeout_secs', int, 'Timeout in seconds when waiting for device.',
          default=60),
      Arg('name', tuple, 'Name of the device to calibrate.',
          default=DEFAULT_NAME),
      Arg('device_path', str, 'Path to the device IIO sysfs entry.',
          default=DEFAULT_SYSPATH),
      Arg('raw_entry_template', str,
          'Template for the sysfs raw value entry.',
          default=DEFAULT_ENTRY_TEMPLATE),
      Arg('calibbias_entry_template', str,
          'Template for the sysfs calibbias value entry.',
          default=DEFAULT_ENTRY_TEMPLATE),
      Arg('stabilize_time', int, 'Time to wait until calibbias stabilize.',
          default=1),
      Arg('prompt', bool, 'Prompt user to put the device in correct facing',
          default=True),
      Arg('placement_range', list, 'A list of tuple asserting the range of '
          'X, Y, Z. Each element is a tuple (min, max) or None if it\'s a '
          'don\'t care.', default=[None, None, None])
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._ui = test_ui.UI(css=CSS)
    self._template = ui_templates.OneSection(self._ui)
    self._start_event = threading.Event()

  def runTest(self):
    previous_fail = False
    while True:
      try:
        if self.args.prompt:
          self.Prompt(previous_fail)
          self._ui.Run(blocking=False)
          self._start_event.wait()

        self.RunCalibration()
      except InvalidPositionError:
        previous_fail = True
        self._start_event.clear()
      else:
        break

  def RunCalibration(self):
    self.WaitForDevice()
    self.VerifyDevicePosition()

    self._template.SetState(test_ui.MakeLabel(
        'Calibrating %s...' % self.args.name[0],
        u'正在校正 %s...' % self.args.name[1]))

    self.EnableAutoCalibration(self.args.device_path)
    self.RetrieveCalibbiasAndWriteVPD()
    self._ui.Pass()

  def Prompt(self, prev_fail=False):
    prompt_en = '<div class="error">%s</div><br/>%s' % (
        'Device not in position' if prev_fail else '',
        'Please put the device in face-up position (press Enter to continue)')
    prompt_zh = '<div class="error">%s</div><br/>%s' % (
        u'装置位置不正确' if prev_fail else '',
        u'请将装置面向上(按 Enter 继续)')

    self._template.SetState(test_ui.MakeLabel(prompt_en, prompt_zh))
    self._ui.BindKey(test_ui.ENTER_KEY, lambda _: self._start_event.set())

  def WaitForDevice(self):
    self._template.SetState(test_ui.MakeLabel('Waiting for device...',
                                              u'正在等待装置...'))
    sync_utils.WaitFor(self._dut.IsReady, self.args.timeout_secs)
    if not self._dut.IsReady():
      self.fail('failed to find deivce')

  def VerifyDevicePosition(self):
    for i, axis in enumerate(['x', 'y', 'z']):
      _range = self.args.placement_range[i]
      if _range is None:
        continue

      key = self.args.raw_entry_template % axis
      value = int(self._dut.Read(self._dut.path.join(self.args.device_path,
                                                     key)))
      if value <= _range[0] or value >= _range[1]:
        factory.console.error(
            'Device not in correct position: %s-axis value: %d. '
            'Valid range (%d, %d)', axis, value, _range[0], _range[1])
        raise InvalidPositionError

  def EnableAutoCalibration(self, path):
    RETRIES = 5
    for unused_i in range(RETRIES):
      try:
        self._dut.Write(self._dut.path.join(path, 'calibrate'), '1')
      except Exception:
        factory.console.info('calibrate activation failed, retrying')
        time.sleep(1)
      else:
        break
    else:
      raise RuntimeError('calibrate activation failed')
    time.sleep(self.args.stabilize_time)

  def RetrieveCalibbiasAndWriteVPD(self):
    cmd = ['vpd']

    for axis in ['x', 'y', 'z']:
      self._template.SetState(test_ui.MakeLabel('Writing calibration data...',
                                                u'正在写入校正结果...'))
      key = self.args.calibbias_entry_template % axis
      value = self._dut.Read(self._dut.path.join(self.args.device_path, key))
      cmd.extend(['-s', '%s=%s' % (key, value.strip())])

    self._dut.CheckCall(cmd)
