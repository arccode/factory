# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for accelerometers calibration.

Description
-----------
This is a calibration test for tri-axis (x, y, and z) accelerometers.

From one accelerometer, we can obtain digital output proportional to the linear
acceleration in each axis. If we put it on a flat table we can get
(x, y, z) = (0, 0, 9.8) at an ideal case. For upside down we'll have
(x, y, z) = (0, 0, -9.8).

Since accelerometer is very sensitive, the digital output will be different
for each query. For example, (0.325, -0.278, 9.55).
In addition, temperature or the assembly quality may impact the accuracy
of the accelerometer during manufacturing (ex, position is tilt). To mitigate
this kind of errors, we'll sample several records of raw data and compute
its average value under an ideal environment. Then store the offset as
a calibrated value for future calculation.

In a horizontal calibration, we'll put accelerometers on a flat position then
sample 100 records of raw data. In this position, two axes are under 0g and
one axis is under 1g. Then we'll update the calibration bias using the
difference between the ideal value (0 and +/-9.8 in the example above) and
the average value of 100 samples.

Test Procedure
--------------
1. Put the device (base/lid) on a horizontal plane then press space.
2. Wait for completion.

Dependency
----------
- Device API (``cros.factory.device.accelerometer``).

Examples
--------
To run horizontal calibration on base accelerometer::

  {
    "pytest_name": "accelerometers_calibration",
    "args": {
      "orientation": {
        "in_accel_z": 1,
        "in_accel_y": 0,
        "in_accel_x": 0
      },
      "spec_offset": [0.5, 0.5],
      "location": "base"
    }
  }
"""

from cros.factory.device import accelerometer
from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import type_utils


class AccelerometersCalibration(test_case.TestCase):

  ARGS = [
      # TODO(bowgotsai): add six-sided calibration.
      Arg(
          'calibration_method', type_utils.Enum(['horizontal']),
          'Currently there is only one calibration method available: '
          'horizontal calibration.', default='horizontal'),
      Arg(
          'orientation', dict,
          'Keys: the name of the accelerometer signal. For example, '
          '"in_accel_x_base" or "in_accel_x_lid". The possible keys are '
          '"in_accel_(x|y|z)_(base|lid)".'
          'Values: an int or a list of [orientation-1, orientation-2, ...].'
          'Each orientation is 0, 1 or -1 representing the ideal '
          'value for gravity under such orientation. For example, 1 or '
          '[0, 0, 1, 0, 0, -1].'
          'An example of orientation for horizontal calibration: {'
          '    "in_accel_x_base": 0,'
          '    "in_accel_y_base": 0,'
          '    "in_accel_z_base": 1,'
          '    "in_accel_x_lid": 0,'
          '    "in_accel_y_lid": 0,'
          '    "in_accel_z_lid": -1}.'
          'Another example of orientation_gravity for six-sided calibration: {'
          '    "in_accel_x_base": [0, 0, 1, -1, 0, 0],'
          '    "in_accel_y_base": [0, 0, 0, 0, 1, -1],'
          '    "in_accel_z_base": [1, -1, 0, 0, 0, 0],'
          '    "in_accel_x_lid": [0, 0, 1, -1, 0, 0],'
          '    "in_accel_y_lid": [0, 0, 0, 0, 1, -1],'
          '    "in_accel_z_lid": [1, -1, 0, 0, 0, 0]}.'),
      Arg('sample_rate_hz', int, 'The sample rate in Hz to get raw data from '
          'accelerometers.', default=20),
      Arg(
          'capture_count', int, 'How many times to capture the raw data to '
          'calculate the average value.', default=100),
      Arg('setup_time_secs', int, 'How many seconds to wait before starting '
          'to calibration.', default=2),
      Arg(
          'spec_offset', list,
          'Two numbers, ex: [0.5, 0.5] indicating the tolerance in m/s^2 for '
          'the digital output of sensors under 0 and 1G.'),
      Arg('autostart', bool, 'Starts the test automatically without prompting.',
          default=False),
      Arg('location', str, 'The location for the accelerometer',
          default='base'),
  ]

  def setUp(self):
    self.ui.ToggleTemplateClass('font-large', True)

    self.dut = device_utils.CreateDUTInterface()
    # Checks arguments.
    self.assertEqual(2, len(self.args.spec_offset))

    self.accelerometer_controller = (
        self.dut.accelerometer.GetController(self.args.location))

  def runTest(self):
    if self.args.calibration_method == 'horizontal':
      self.HorizontalCalibration()
    else:
      raise NotImplementedError

  def HorizontalCalibration(self):
    """Prompt for space, waits a period of time and then starts calibration."""
    if not self.args.autostart:
      self.ui.SetState(
          _('Please put device on a horizontal plane then press space to '
            'start calibration.'))
      self.ui.WaitKeysOnce(test_ui.SPACE_KEY)
    else:
      self.ui.SetState(_('Please put device on a horizontal plane.'))
      self.Sleep(1)

    # Waits for a few seconds to let machine become stable.
    for i in range(self.args.setup_time_secs):
      self.ui.SetState(
          _('Calibration will be started within {time} seconds.'
            'Please do not move device.',
            time=self.args.setup_time_secs - i))
      self.Sleep(1)

    # Cleanup offsets before calibration
    self.accelerometer_controller.CleanUpCalibrationValues()

    # Starts calibration.
    self.ui.SetState(
        _('Calibration is in progress, please do not move device.'))
    try:
      raw_data = self.accelerometer_controller.GetData(self.args.capture_count)
    except accelerometer.AccelerometerException:
      self.FailTask('Read raw data failed.')

    # Checks accelerometer is normal or not before calibration.
    if not self.accelerometer_controller.IsWithinOffsetRange(
        raw_data, self.args.orientation, self.args.spec_offset):
      self.FailTask('Raw data out of range, the accelerometers may be damaged.')

    calib_bias = self.accelerometer_controller.CalculateCalibrationBias(
        raw_data, self.args.orientation)
    self.accelerometer_controller.UpdateCalibrationBias(calib_bias)
