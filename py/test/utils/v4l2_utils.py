# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import ctypes
import fcntl
import logging

from cros.factory.utils import type_utils

# Bitmask for video capture capability.  Please check
# Documentation/media/uapi/v4l/vidioc-querycap.rst under kernel source tree and
# https://chromium.googlesource.com/chromiumos/platform2/+/05b743f8c37bd63e49844eff806f0e5daf8c3352/camera/hal/usb/v4l2_test/media_v4l2_test.cc#78
V4L2_CAP_VIDEO_CAPTURE = 0x00000001
V4L2_CAP_VIDEO_CAPTURE_MPLANE = 0x00001000
V4L2_CAP_VIDEO_OUTPUT = 0x00000002
V4L2_CAP_VIDEO_OUTPUT_MPLANE = 0x00002000
V4L2_CAP_VIDEO_M2M = 0x00008000
V4L2_CAP_VIDEO_M2M_MPLANE = 0x00004000
V4L2_CAP_DEVICE_CAPS = 0x80000000
V4L2_CAP_STREAMING = 0x04000000

# V4L2 encode/decode device should have the following capabilities.
V4L2_CAP_VIDEO_CODEC = (
    V4L2_CAP_VIDEO_CAPTURE_MPLANE | V4L2_CAP_VIDEO_OUTPUT_MPLANE
    | V4L2_CAP_STREAMING)


class V4L2Capability(ctypes.Structure):
  """struct v4l2_capability: the output of VIDIOC_QUERYCAP ioctl call.

  Reference:
  https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/vidioc-querycap.html#c.V4L.v4l2_capability
  """
  _fields_ = [
      ('driver', ctypes.c_ubyte * 16),
      ('card', ctypes.c_ubyte * 32),
      ('bus_info', ctypes.c_ubyte * 32),
      ('version', ctypes.c_uint32),
      ('capabilities', ctypes.c_uint32),
      ('device_caps', ctypes.c_uint32),
      ('reserved', ctypes.c_uint32 * 3),
  ]


COMPONENT_TYPE = type_utils.Enum(['webcam', 'video_codec'])


def GuessComponentType(video_idx):
  """Guess what kind of v4l2 device it is.

  Returns: an element of COMPONENT_TYPE, or None for unknown types.
  """
  v4l2_capability = QueryV4L2Capability(video_idx)
  if IsCaptureDevice(v4l2_capability):
    return COMPONENT_TYPE.webcam
  if IsVideoCodec(v4l2_capability):
    return COMPONENT_TYPE.video_codec
  return None


def QueryV4L2Capability(video_idx):
  """Query V4L2 capability via IOCTL API.

  Returns:
    This function always returns a V4L2Capability instance.  On failure, the
    instance will be zeroized.
  """
  IOCTL_VIDIOC_QUERYCAP = 0x80685600
  dev_path = '/dev/video%d' % video_idx
  try:
    with open(dev_path, 'r') as f:
      v4l2_capability = V4L2Capability()
      fcntl.ioctl(f.fileno(), IOCTL_VIDIOC_QUERYCAP, v4l2_capability)
      return v4l2_capability
  except Exception:
    logging.exception('Failed to query capabilities of %r', dev_path)
    return V4L2Capability()


def IsCaptureDevice(v4l2_capability):
  """Determine if this is a capture device (camera) by capabilities.

  Args:
    v4l2_capability: a V4L2Capability instance.

  Returns:
    True if this looks like a capture device, otherwise False.
  """
  caps = v4l2_capability.capabilities
  if caps & V4L2_CAP_DEVICE_CAPS:
    # The driver fills the device_caps field, use it instead.
    caps = v4l2_capability.device_caps

  # Webcam should have CAPTURE capability but no OUTPUT capability.
  if not caps & (V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_VIDEO_CAPTURE_MPLANE):
    return False
  if caps & (V4L2_CAP_VIDEO_OUTPUT | V4L2_CAP_VIDEO_OUTPUT_MPLANE):
    return False
  if caps & (V4L2_CAP_VIDEO_M2M | V4L2_CAP_VIDEO_M2M_MPLANE):
    return False
  return True


def IsVideoCodec(v4l2_capability):
  caps = v4l2_capability.capabilities
  return caps & V4L2_CAP_VIDEO_CODEC == V4L2_CAP_VIDEO_CODEC
