# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for gyroscopes.

Description
-----------
There are steps required to run a complete gyroscope test::
  - Motion sensor setup via `ectool motionsense odr ${gyro_id} ${freq}`
  - (optional) Calibration for tri-axis (x, y, and z) gyroscopes.
  - The main gyroscope test.

This pytest executes the motion sensor setup and main gyro test in sequence.

Test Procedure
--------------
This test supports and enables auto start by default.  In this case::
1. Put the device (base/lid) on a static plane then press space.
2. Wait for completion.

Otherwise operators will be asked to place DUT on a horizontal plane and
press space.

Dependency
----------
- Device API (``cros.factory.device.gyroscope``).

Examples
--------
To run a test on base gyroscope::

  {
    "pytest_name": "gyroscope",
    "args": {
      "rotation_threshold": 1.0,
      "stop_threshold": 0.1,
      "location": "base"
    }
  }
"""

import collections

from six import iteritems
from six.moves import xrange

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils


class Gyroscope(test_case.TestCase):

  ARGS = [
      Arg('rotation_threshold', float,
          'The expected value (rad/s) to read when dut start rotating.'),
      Arg('stop_threshold', float,
          'The expected value to read when dut stop moving.'),
      Arg('gyro_id', int,
          'Gyroscope ID.  Will read a default ID via ectool if not set.',
          default=None),
      Arg('freq', int,
          'Gyroscope sampling frequency in mHz.  Will apply the minimal '
          'frequency from ectool info if not set.',
          default=None),
      Arg('timeout_secs', int,
          'Timeout in seconds for gyro to return expected value.',
          default=30),
      Arg('setup_time_secs', int,
          'Seconds to wait before starting the test.',
          default=2),
      Arg('autostart', bool, 'Auto start this test.',
          default=False),
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
          _('Please put device on a horizontal plane then press space to '
            'start testing.'))
      self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

    for i in xrange(self.args.setup_time_secs):
      self.ui.SetState(
          _('Test will be started within {secs} seconds. '
            'Please do not move the device.',
            secs=self.args.setup_time_secs - i))
      self.Sleep(1)

    self.ui.SetInstruction(_('Please do not move the device.'))
    self._WaitForDeviceStop()

    self.ui.SetInstruction(_('Please rotate the device.'))
    self._WaitForDeviceRotate()

  def _UpdateState(self, max_values):
    html = []
    for k, v in iteritems(max_values):
      state = ('test-status-passed'
               if v > self.args.rotation_threshold else 'test-status-failed')
      html.append('<div class="%s">%s=%s</div>' % (state, test_ui.Escape(k), v))
    self.ui.SetState(''.join(html))

  def _WaitForDeviceStop(self):
    """Wait until absolute value of all sensors less than stop_threshold."""

    def CheckSensorState():
      data = self.gyroscope.GetData()
      return max(abs(v) for v in data.values()) < self.args.stop_threshold

    sync_utils.WaitFor(CheckSensorState, self.args.timeout_secs)

  def _WaitForDeviceRotate(self):
    """Wait until all sensors has absolute value > rotation_threshold."""

    max_values = collections.defaultdict(float)
    def CheckSensorMaxValues():
      data = self.gyroscope.GetData()
      for sensor_name, value in iteritems(data):
        max_values[sensor_name] = max(max_values[sensor_name], abs(value))
      self._UpdateState(max_values)
      return min(max_values.values()) > self.args.rotation_threshold

    sync_utils.WaitFor(CheckSensorMaxValues, self.args.timeout_secs)
