# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import array
import fcntl
import struct


def GetV4L2Data(video_idx):
  # Get information from video4linux2 (v4l2) interface.
  # See /usr/include/linux/videodev2.h for definition of these consts.
  info = {}

  # Get v4l2 capability
  V4L2_CAPABILITY_FORMAT = '<16B32B32BII4I'
  V4L2_CAPABILITY_STRUCT_SIZE = struct.calcsize(V4L2_CAPABILITY_FORMAT)
  V4L2_CAPABILITIES_OFFSET = struct.calcsize(V4L2_CAPABILITY_FORMAT[0:-3])
  # struct v4l2_capability
  # {
  #   __u8  driver[16];
  #   __u8  card[32];
  #   __u8  bus_info[32];
  #   __u32 version;
  #   __u32 capabilities;  /* V4L2_CAPABILITIES_OFFSET */
  #   __u32 reserved[4];
  # };

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

  def _TryIoctl(fileno, request, *args):
    """Try to invoke ioctl without raising an exception if it fails."""
    try:
      fcntl.ioctl(fileno, request, *args)
    except Exception:
      pass

  try:
    with open('/dev/video%d' % video_idx, 'r') as f:
      # Read V4L2 capabilities.
      buf = array.array('B', [0] * V4L2_CAPABILITY_STRUCT_SIZE)
      _TryIoctl(f.fileno(), IOCTL_VIDIOC_QUERYCAP, buf, 1)
      capabilities = struct.unpack_from('<I', buf, V4L2_CAPABILITIES_OFFSET)[0]
      if ((capabilities & V4L2_CAP_VIDEO_CAPTURE) and
          (not capabilities & V4L2_CAP_VIDEO_OUTPUT)):
        info['type'] = 'webcam'
      elif capabilities & V4L2_CAP_VIDEO_CODEC == V4L2_CAP_VIDEO_CODEC:
        info['type'] = 'video_codec'
  except Exception:
    pass
  return info
