#!/usr/bin/python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Camera device controller.

This module provides accessing camera devices.
"""

import factory_common  # pylint: disable=W0611
from cros.factory.device import component
from cros.factory.test.utils.camera_utils import CVCameraDevice


class Camera(component.DeviceComponent):
  """System module for camera device.

    The default implementation contains only one camera device, which is the
    defualt camera opened by OpenCV.

    Subclass should override GetCameraDevice(index).
    """

  def __init__(self, dut):
    super(Camera, self).__init__(dut)
    self._devices = {}

  def GetCameraDevice(self, index):
    """Get the camera device of the given index.

    Args:
      index: index of the camera device.

    Returns:
      Camera device object that implements
      cros.factory.test.utils.camera_utils.CameraDeviceBase.
    """
    return self._devices.setdefault(index, CVCameraDevice(index))
