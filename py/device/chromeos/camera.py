# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Camera device controller for Chrome OS.

This module provides accessing camera devices.
"""

import os
import re

import factory_common  # pylint: disable=unused-import
from cros.factory.device import camera
from cros.factory.test.utils.camera_utils import CameraDevice
from cros.factory.test.utils.camera_utils import CameraError
from cros.factory.test.utils.camera_utils import CVCameraReader


class ChromeOSCamera(camera.Camera):
  """System module for camera device.

    The default implementation contains only one camera device, which is the
    default camera opened by OpenCV.

    Subclass should override GetCameraDevice(index).
  """

  def _GetRealDeviceIndex(self, camera_index):
    """Get the real video device index from camera-internal index."""
    # If index is None, camera_utils will search the unique device.
    if camera_index is None:
      return None
    camera_device_path = '/dev/camera-internal%d' % camera_index
    if not os.path.islink(camera_device_path):
      raise CameraError('Camera symlink not found')
    real_device_path = os.path.realpath(
        '/dev/camera-internal%d' % camera_index)
    real_device_index = int(
        re.search(r'/dev/video([0-9]+)$', real_device_path).group(1))
    return real_device_index

  def GetCameraDevice(self, index):
    """Get the camera device of the given index.

    Since the video device index may change after device reboot, we use
    camera-internal index instead.

    Args:
      index: index of the camera-internal device.

    Returns:
      Camera device object that implements
      cros.factory.test.utils.camera_utils.CameraDevice.
    """
    real_index = self._GetRealDeviceIndex(index)
    return self._devices.setdefault(index, CameraDevice(
        dut=self._device, sn_format=None,
        reader=CVCameraReader(real_index, self._device)))
