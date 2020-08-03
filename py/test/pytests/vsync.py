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
    "pytest_name": "vsync"
  }
"""


import os
import stat

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


DEFAULT_CAPTURE_NUMBER = 10


class SpatialSensorCalibration(test_case.TestCase):
  ARGS = [
      Arg('capture_number', int, 'The number of capture frames.',
          default=DEFAULT_CAPTURE_NUMBER),
      Arg('camera_facing', type_utils.Enum(['front', 'rear']),
          ('Direction the camera faces relative to device screen. Only allow '
           '"front", "rear" or None. None is automatically searching one.'),
          default=None),
      Arg('timeout_secs', int, 'Timeout in seconds when waiting for device.',
          default=60),
      Arg('repeat_times', int, 'Number of cycles to test.', default=5)
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._vsync = self._dut.vsync_sensor.GetController()

    self.ui.ToggleTemplateClass('font-large', True)

    self.assertIsNotNone(self._vsync, 'VSync controller not found')

  def runTest(self):
    camera_path = self.GetDevicePath()
    self.WaitForDevice()
    # The "frequency" entry of a VSync sensor is actually being used as an
    # on/off switch, so this turns on the sensor.
    self._vsync.SetFrequency(1)
    start_count = 0
    for idx in range(self.args.repeat_times):
      self.ui.SetState(
          _('Verifying VSync pin... ({count}/{total})',
            count=idx, total=self.args.repeat_times))
      self._dut.CheckCall(
          ['yavta', '--capture=%d' % self.args.capture_number, camera_path])
      end_count = self._vsync.GetCount()
      session.console.info('VSync device in_count_raw (%d/%d): %d',
                           idx, self.args.repeat_times, end_count)
      if not start_count + self.args.capture_number <= end_count:
        self.fail('in_count_raw is not growing')
      start_count = end_count
    # Turning off the sensor.
    self._vsync.SetFrequency(0)

  def GetDevicePath(self):
    device_index = self._dut.camera.GetDeviceIndex(self.args.camera_facing)
    camera_path = '/dev/video%d' % device_index
    if not stat.S_ISCHR(os.stat(camera_path)[stat.ST_MODE]):
      self.fail('%s is not a character special file' % camera_path)
    return camera_path

  def WaitForDevice(self):
    self.ui.SetState(_('Waiting for device...'))
    try:
      sync_utils.WaitFor(self._dut.IsReady, self.args.timeout_secs)
    except type_utils.TimeoutError:
      self.fail('failed to find deivce')
