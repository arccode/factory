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

  - cat /sys/bus/iio/devices/iio:deviceX/in_(accel|anglvel)_(x|y|z)_calibbias

4) Save them in VPD.
"""

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


DEFAULT_NAME = _('Accelerometer')
DEFAULT_RAW_ENTRY_TEMPLATE = 'in_accel_%s_raw'
DEFAULT_CALIBBIAS_ENTRY_TEMPLATE = 'in_accel_%s_calibbias'
DEFAULT_VPD_ENTRY_TEMPLATE = 'in_accel_%s_base_calibbias'



class InvalidPositionError(Exception):
  pass


class SpatialSensorCalibration(test_case.TestCase):
  ARGS = [
      Arg('timeout_secs', int, 'Timeout in seconds when waiting for device.',
          default=60),
      i18n_arg_utils.I18nArg('sensor_name', 'name of the sensor to calibrate.',
                             default=DEFAULT_NAME),
      Arg('device_name', str, 'The "name" atribute of the sensor'),
      Arg('device_location', str, 'The "location" atribute of the sensor'),
      Arg('raw_entry_template', str,
          'Template for the sysfs raw value entry.',
          default=DEFAULT_RAW_ENTRY_TEMPLATE),
      Arg('calibbias_entry_template', str,
          'Template for the sysfs calibbias value entry.',
          default=DEFAULT_CALIBBIAS_ENTRY_TEMPLATE),
      Arg('vpd_entry_template', str,
          'Template for the sysfs calibbias value entry.',
          default=DEFAULT_VPD_ENTRY_TEMPLATE),
      Arg('stabilize_time', int, 'Time to wait until calibbias stabilize.',
          default=1),
      Arg('prompt', bool, 'Prompt user to put the device in correct facing',
          default=True),
      Arg('placement_range', list, 'A list of sequences asserting the range of '
          "X, Y, Z. Each element is [min, max] or None if it's a "
          "don't care.", default=[None, None, None])
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._device_path = None

    self.ui.ToggleTemplateClass('font-large', True)

    for path in self._dut.Glob('/sys/bus/iio/devices/iio:device*'):
      try:
        name = self._dut.ReadFile(self._dut.path.join(path, 'name')).strip()
        location = self._dut.ReadFile(
            self._dut.path.join(path, 'location')).strip()
      except Exception:
        continue
      if (name == self.args.device_name and
          location == self.args.device_location):
        self._device_path = path

    self.assertIsNotNone(self._device_path, '%s at %s not found' %
                         (self.args.device_name, self.args.device_location))

  def runTest(self):
    previous_fail = False
    while True:
      try:
        if self.args.prompt:
          self.Prompt(previous_fail)
          self.ui.WaitKeysOnce(test_ui.ENTER_KEY)

        self.RunCalibration()
      except InvalidPositionError:
        previous_fail = True
      else:
        break

  def RunCalibration(self):
    self.WaitForDevice()
    self.VerifyDevicePosition()

    self.ui.SetState(
        _('Calibrating {sensor_name}...', sensor_name=self.args.sensor_name))

    self.EnableAutoCalibration(self._device_path)
    self.RetrieveCalibbiasAndWriteVPD()

  def Prompt(self, prev_fail=False):
    self.ui.SetState([
        '<div class="test-error">',
        _('Device not in position') if prev_fail else '', '</div><br>',
        _('Please put the device in face-up position'
          ' (press Enter to continue)')
    ])

  def WaitForDevice(self):
    self.ui.SetState(_('Waiting for device...'))
    try:
      sync_utils.WaitFor(self._dut.IsReady, self.args.timeout_secs)
    except type_utils.TimeoutError:
      self.fail('failed to find deivce')

  def VerifyDevicePosition(self):
    for i, axis in enumerate(['x', 'y', 'z']):
      _range = self.args.placement_range[i]
      if _range is None:
        continue

      key = self.args.raw_entry_template % axis
      value = int(self._dut.ReadFile(self._dut.path.join(self._device_path,
                                                         key)))
      if value <= _range[0] or value >= _range[1]:
        session.console.error(
            'Device not in correct position: %s-axis value: %d. '
            'Valid range (%d, %d)', axis, value, _range[0], _range[1])
        raise InvalidPositionError

  def EnableAutoCalibration(self, path):
    RETRIES = 20
    for unused_i in range(RETRIES):
      try:
        self._dut.WriteFile(self._dut.path.join(path, 'calibrate'), '1')
      except Exception:
        session.console.info('calibrate activation failed, retrying')
        self.Sleep(1)
      else:
        break
    else:
      raise RuntimeError('calibrate activation failed')
    self.Sleep(self.args.stabilize_time)

  def RetrieveCalibbiasAndWriteVPD(self):
    cmd = ['vpd']

    for axis in ['x', 'y', 'z']:
      self.ui.SetState(_('Writing calibration data...'))
      calibbias_key = self.args.calibbias_entry_template % axis
      vpd_key = self.args.vpd_entry_template % axis
      value = self._dut.ReadFile(
          self._dut.path.join(self._device_path, calibbias_key))
      cmd.extend(['-s', '%s=%s' % (vpd_key, value.strip())])

    self._dut.CheckCall(cmd)
