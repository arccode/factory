# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""VSync pin test.

Description
-----------
This pytest test if VSync pin is connected to EC and camera can receive VSync
signal.

Test Procedure
--------------
This is an automatic test that doesn't need any user interaction.

Dependency
----------
- Yet Another V4L2 Test Application (``yavta``)

Examples
--------
To run a VSync pin test, add this in test list::

  {
    "pytest_name": "vsync",
    "args": {
      "camera_path": "/dev/camera-internal0"
    }
  }
"""


import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


DEFAULT_DEVICE_NAME = 'cros-ec-sync'
DEFAULT_DEVICE_LOCATION = 'camera'
DEFAULT_CAPTURE_NUMBER = 10
DEFAULT_CAMERA_PATH = '/dev/camera-internal0'


class SpatialSensorCalibration(test_case.TestCase):
  ARGS = [
      Arg('device_name', str, 'The "name" atribute of the sensor.',
          default=DEFAULT_DEVICE_NAME),
      Arg('device_location', str, 'The "location" atribute of the sensor.',
          default=DEFAULT_DEVICE_LOCATION),
      Arg('capture_number', int, 'The number of capture frames.',
          default=DEFAULT_CAPTURE_NUMBER),
      Arg('camera_path', str, 'The path of camera.',
          default=DEFAULT_CAMERA_PATH),
      Arg('timeout_secs', int, 'Timeout in seconds when waiting for device.',
          default=60),
      Arg('repeat_times', int, 'Number of cycles to test.',
          default=5)
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
        if self._device_path is None:
          self._device_path = path
        else:
          self.fail('failed to find a specified VSync device')

    self.assertIsNotNone(self._device_path, '%s at %s not found' %
                         (self.args.device_name, self.args.device_location))

  def runTest(self):
    self.WaitForDevice()
    self.SetFrequency(1)
    start_count = 0
    for idx in xrange(self.args.repeat_times):
      self.ui.SetState(
          _('Verifying VSync pin... ({count}/{total})',
            count=idx, total=self.args.repeat_times))
      self._dut.CheckCall(
          ['yavta', '--capture=%d' % self.args.capture_number,
           self.args.camera_path])
      end_count = self.GetInCount()
      session.console.info('VSync device in_count_raw (%d/%d): %d',
                           idx, self.args.repeat_times, end_count)
      if not start_count + self.args.capture_number <= end_count:
        self.fail('in_count_raw is not growing')
      start_count = end_count
    self.SetFrequency(0)

  def WaitForDevice(self):
    self.ui.SetState(_('Waiting for device...'))
    try:
      sync_utils.WaitFor(self._dut.IsReady, self.args.timeout_secs)
    except type_utils.TimeoutError:
      self.fail('failed to find deivce')

  def GetInCount(self):
    return int(self._dut.ReadFile(
        self._dut.path.join(self._device_path, 'in_count_raw')))

  def SetFrequency(self, freq):
    self._dut.WriteFile(
        self._dut.path.join(self._device_path, 'frequency'),
        str(freq))
