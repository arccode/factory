# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Camera device controller.

This module provides accessing camera devices.
"""

import factory_common  # pylint: disable=unused-import
from cros.factory.device import types
from cros.factory.test.utils.camera_utils import CameraDevice
from cros.factory.test.utils.camera_utils import CVCameraReader


class Camera(types.DeviceComponent):
  """System module for camera device.

    The default implementation contains only one camera device, which is the
    default camera opened by OpenCV.

    Subclass should override GetCameraDevice(index).
  """

  def __init__(self, dut):
    """System module for camera devices."""
    super(Camera, self).__init__(dut)
    self._devices = {}

  def GetCameraDevice(self, index):
    """Get the camera device of the given index.

    Args:
      index: index of the camera device.

    Returns:
      Camera device object that implements
      cros.factory.test.utils.camera_utils.CameraDevice.
    """
    return self._devices.setdefault(index, CameraDevice(
        dut=self._device, sn_format=None,
        reader=CVCameraReader(index, self._device)))
