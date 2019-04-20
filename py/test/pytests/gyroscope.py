# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for gyroscopes.

Usage examples::

    {
      "pytest_name": "gyroscope",
      "args": {
        "rotation_threshold": 1.0,
        "stop_threshold": 0.1
      }
    }
"""

import collections

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
      Arg('timeout_secs', int,
          'Timeout in seconds for gyro to return expected value.',
          default=30),
      Arg('setup_time_secs', int,
          'Seconds to wait before starting the test.',
          default=2),
      Arg('autostart', bool, 'Auto start this test.',
          default=False),
      Arg('location', str, 'Gyro is located in "base" or "lid".',
          default='base')]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.gyroscope = self.dut.gyroscope.GetController(
        location=self.args.location)
    self.ui.ToggleTemplateClass('font-large', True)

  def runTest(self):
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
    for k, v in max_values.iteritems():
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
      for sensor_name, value in data.iteritems():
        max_values[sensor_name] = max(max_values[sensor_name], abs(value))
      self._UpdateState(max_values)
      return min(max_values.values()) > self.args.rotation_threshold

    sync_utils.WaitFor(CheckSensorMaxValues, self.args.timeout_secs)
