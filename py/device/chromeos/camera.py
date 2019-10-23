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
from cros.factory.utils import type_utils


CAMERA_CONFIG_PATH = '/etc/camera/camera_characteristics.conf'
GLOB_CAMERA_PATH = '/sys/class/video4linux/video*'
ALLOWED_FACING = type_utils.Enum(['front', 'rear', None])


class ChromeOSCamera(camera.Camera):
  """System module for camera device.

    The default implementation contains only one camera device, which is the
    default camera opened by OpenCV.

    Subclass should override GetCameraDevice(index).
  """

  _index_mapping = {}

  def GetDeviceIndex(self, facing):
    """Search the video device index from the camera characteristics file.

    Args:
      facing: Direction the camera faces relative to device screen. Only allow
              'front', 'rear' or None. None is automatically searching one.

    Since the video device index may change after device reboot/suspend resume,
    we search the video device index from the camera characteristics file.
    """
    if facing not in ALLOWED_FACING:
      raise CameraError('The facing (%s) is not in ALLOWED_FACING (%s)' %
                        (facing, ALLOWED_FACING))

    if facing in self._index_mapping:
      return self._index_mapping[facing]

    camera_paths = self._device.Glob(GLOB_CAMERA_PATH)
    index_to_vid_pid = {}
    for path in camera_paths:
      index = int(self._device.ReadFile(os.path.join(path, 'index')))
      vid = self._device.ReadFile(
          os.path.join(path, 'device', '..', 'idVendor')).strip()
      pid = self._device.ReadFile(
          os.path.join(path, 'device', '..', 'idProduct')).strip()
      index_to_vid_pid[index] = '%s:%s' % (vid, pid)

    camera_config = self._device.ReadFile(CAMERA_CONFIG_PATH)
    index_to_camera_id = {}
    for index, vid_pid in index_to_vid_pid.iteritems():
      camera_id = re.findall(
          r'^camera(\d+)\.module\d+\.usb_vid_pid=%s$' % vid_pid,
          camera_config, re.MULTILINE)
      if len(set(camera_id)) > 1:
        raise CameraError(
            'Multiple cameras have the same usb_vid_pid (%s)' % vid_pid)
      elif not camera_id:
        raise CameraError('No camera has the usb_vid_pid (%s)' % vid_pid)
      else:
        camera_id = int(camera_id[0])
      index_to_camera_id[index] = camera_id

    for index, camera_id in index_to_camera_id.iteritems():
      camera_facing = int(re.search(
          r'^camera%d\.lens_facing=(\d+)$' % camera_id,
          camera_config, re.MULTILINE).group(1))
      camera_facing = {
          0: 'front',
          1: 'rear'
      }[camera_facing]
      self._index_mapping[camera_facing] = index

    if facing is None:
      if len(self._index_mapping) > 1:
        raise CameraError('Multiple cameras are found')
      elif not self._index_mapping:
        raise CameraError('No camera is found')
      return next(iter(self._index_mapping.values()))

    if facing not in self._index_mapping:
      raise CameraError('No %s camera is found' % facing)
    return self._index_mapping[facing]

  def GetCameraDevice(self, facing):
    """Get the camera device of the given direction the camera faces.

    Args:
      facing: Direction the camera faces relative to device screen. Only allowed
              'front', 'rear' or None. None is automatically searching one.

    Returns:
      Camera device object that implements
      cros.factory.test.utils.camera_utils.CameraDevice.
    """
    device_index = self.GetDeviceIndex(facing)
    return self._devices.setdefault(facing, CameraDevice(
        dut=self._device, sn_format=None,
        reader=CVCameraReader(device_index, self._device)))
