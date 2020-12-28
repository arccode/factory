# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import ctypes
import fcntl
import logging


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


def _TryIoctl(fileno, request, *args):
  """Try to invoke ioctl without raising an exception if it fails."""
  try:
    fcntl.ioctl(fileno, request, *args)
  except Exception:
    pass


def GetV4L2Data(video_idx):
  """Get information from video4linux2 (v4l2) interface."""
  IOCTL_VIDIOC_QUERYCAP = 0x80685600

  # Webcam should have CAPTURE capability but no OUTPUT capability.
  V4L2_CAP_VIDEO_CAPTURE = 0x00000001
  V4L2_CAP_VIDEO_OUTPUT = 0x00000002

  # V4L2 encode/decode device should have the following capabilities.
  V4L2_CAP_VIDEO_CAPTURE_MPLANE = 0x00001000
  V4L2_CAP_VIDEO_OUTPUT_MPLANE = 0x00002000
  V4L2_CAP_STREAMING = 0x04000000
  V4L2_CAP_VIDEO_CODEC = (
      V4L2_CAP_VIDEO_CAPTURE_MPLANE | V4L2_CAP_VIDEO_OUTPUT_MPLANE
      | V4L2_CAP_STREAMING)

  info = {}
  dev_path = '/dev/video%d' % video_idx

  try:
    with open(dev_path, 'r') as f:
      v4l2_capability = V4L2Capability()
      _TryIoctl(f.fileno(), IOCTL_VIDIOC_QUERYCAP, v4l2_capability)

      cap = v4l2_capability.capabilities
      if (cap & V4L2_CAP_VIDEO_CAPTURE) and (not cap & V4L2_CAP_VIDEO_OUTPUT):
        info['type'] = 'webcam'
      elif cap & V4L2_CAP_VIDEO_CODEC == V4L2_CAP_VIDEO_CODEC:
        info['type'] = 'video_codec'
  except Exception:
    logging.exception('Failed to get V4L2 attribute from %r', dev_path)

  return info
