# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for gyroscopes calibration.

Description
-----------
This is a calibration test for tri-axis (x, y, and z) gyroscopes.

Test Procedure
--------------
1. Put the device (base/lid) on a static plane then press space.
2. Wait for completion.

Dependency
----------
- Device API (``cros.factory.device.gyroscope``).

Examples
--------
To run calibration on base gyroscope::

  {
    "pytest_name": "gyroscope_calibration",
    "args": {
      "location": "base"
    }
  }
"""

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg


class Gyroscope(test_case.TestCase):

  ARGS = [
      Arg('capture_count', int,
          'Number of records to read to compute the average.',
          default=100),
      Arg('gyro_id', int,
          'Gyroscope ID.  Will read a default ID via ectool if not set.',
          default=None),
      Arg('freq', int,
          'Gyroscope sampling frequency in mHz.  Will apply the minimal '
          'frequency from ectool info if not set.',
          default=None),
      Arg('sample_rate', int,
          'Sample rate in Hz to read data from the gyroscope sensor.',
          default=20),
      Arg('setup_time_secs', int,
          'Seconds to wait before starting the test.',
          default=2),
      Arg('autostart', bool, 'Auto start this test.',
          default=True),
      Arg('setup_sensor', bool, 'Setup gyro sensor via ectool',
          default=True),
      Arg('location', str, 'Gyro is located in "base" or "lid".',
          default='base')]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.gyroscope = self.dut.gyroscope.GetController(
        location=self.args.location,
        gyro_id=self.args.gyro_id,
        freq=self.args.freq)
    self.ui.ToggleTemplateClass('font-large', True)

  def runTest(self):
    if self.args.setup_sensor:
      self.gyroscope.SetupMotionSensor()

    if not self.args.autostart:
      self.ui.SetState(
          _('Please put device on a static plane then press space to '
            'start calibration.'))
      self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

    for i in range(self.args.setup_time_secs):
      self.ui.SetState(
          _('Calibration will be started within {secs} seconds.'
            'Please do not move the device.',
            secs=self.args.setup_time_secs - i))
      self.Sleep(1)

    self.ui.SetState(_('Please do not move the device.'))
    self.gyroscope.CleanUpCalibrationValues()
    raw_data = self.gyroscope.GetData(self.args.capture_count,
                                      self.args.sample_rate)
    calib_bias = self.gyroscope.CalculateCalibrationBias(raw_data)
    self.gyroscope.UpdateCalibrationBias(calib_bias)
