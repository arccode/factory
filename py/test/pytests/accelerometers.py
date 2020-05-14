# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""A factory test for reading accelerometers

Description
-----------
This is a test to check if values read back from accelerometers are within a
certain range.  If we put it on a flat table we can get (x, y, z) = (0, 0, 9.8)
at an ideal case. For upside down we'll have (x, y, z) = (0, 0, -9.8).

Since accelerometer is very sensitive, the digital output will be different
for each query. For example, (0.325, -0.278, 9.55).
In addition, temperature or the assembly quality may impact the accuracy
of the accelerometer during manufacturing (ex, position is tilt). To mitigate
this kind of errors, we'll sample several records of raw data and compute
its average value under an ideal environment.

Test Procedure
--------------
1. The test will auto start unless argument `autostart` is false, otherwise, it
   will wait for operators to press `SPACE`.
2. Check if values are within the threashold, pass / fail automatically.

Dependency
----------
- Device API (``cros.factory.device.accelerometer``)

Examples
--------
If the device is expected to be place horizontally on desk, this test can be
added as simple as::

  {
    "pytest_name": "accelerometers"
  }

You can also change the limits of each axis to loose the criteria::

  {
    "pytest_name": "accelerometers"
    "args": {
      "limits": {
        "x": [-1.0, 1.0],
        "y": [-1.0, 1.0],
        "z": [8.0, 11.0]
      }
    }
  }

"""

from cros.factory.device import accelerometer
from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.testlog import testlog


DEFAULT_LIMITS = {
    'x': [-0.5, 0.5],
    'y': [-0.5, 0.5],
    'z': [8.8, 10.8],
}


class AccelerometersTest(test_case.TestCase):
  ARGS = [
      Arg('autostart', bool,
          'If this is false, this test will not start until operators press '
          'space', default=True),
      Arg('limits', dict,
          'A dictionary of expected range for x, y, z values.  For example, '
          '{"x": [-0.5, 0.5], "y": [-0.5, 0.5], "z": [8.8, 10.8]}',
          default=None),
      Arg('sample_rate_hz', int,
          'The sample rate in Hz to get raw data from '
          'accelerometers.', default=20),
      Arg('capture_count', int,
          'How many times to capture the raw data to '
          'calculate the average value.', default=100),
      Arg('setup_time_secs', int,
          'How many seconds to wait before starting '
          'to calibration.', default=2),
      Arg('location', str,
          'The location for the accelerometer', default='base'),
  ]

  def setUp(self):
    self.ui.ToggleTemplateClass('font-large', True)

    if self.args.limits is None:
      self.args.limits = DEFAULT_LIMITS
    assert self.args.limits.keys() == {'x', 'y', 'z'}, (
        'Limits should be a dictionary with keys "x", "y" and "z"')
    for unused_axis, [limit_min, limit_max] in self.args.limits.items():
      assert limit_min <= limit_max

    self.dut = device_utils.CreateDUTInterface()
    self.accelerometer_controller = (
        self.dut.accelerometer.GetController(self.args.location))

  def runTest(self):
    if not self.args.autostart:
      self.ui.SetState(_('Press SPACE to continue'))
      self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

    # Waits for a few seconds to let machine become stable.
    for i in range(self.args.setup_time_secs):
      self.ui.SetState(
          _('Test will be started within {secs} seconds. '
            'Please do not move the device.',
            secs=self.args.setup_time_secs - i))
      self.Sleep(1)

    self.ui.SetState(_('Test is in progress, please do not move the device.'))

    try:
      raw_data = self.accelerometer_controller.GetData(self.args.capture_count)
    except accelerometer.AccelerometerException:
      self.FailTask('Read raw data failed.')

    passed = True
    for axis, [limit_min, limit_max] in self.args.limits.items():
      key = 'in_accel_' + axis  # in_accel_(x|y|z)
      passed &= testlog.CheckNumericParam(
          name=key, value=raw_data[key], min=limit_min, max=limit_max)
    if not passed:
      self.FailTask('Sensor value out of limit %r' % raw_data)
