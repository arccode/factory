# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import re

from cros.factory.probe import function
from cros.factory.probe.lib import cached_probe_function
from cros.factory.test.utils import v4l2_utils


class GenericVideoFunction(cached_probe_function.GlobPathCachedProbeFunction):
  """Probe the generic video information."""

  GLOB_PATH = '/sys/class/video4linux/video*'

  _probed_dev_paths = set()

  @classmethod
  def ProbeDevice(cls, dir_path):
    logging.debug('Find the node: %s', dir_path)

    dev_path = os.path.abspath(os.path.realpath(os.path.join(dir_path,
                                                             'device')))
    if dev_path in cls._probed_dev_paths:
      return None
    cls._probed_dev_paths.add(dev_path)

    result = {}

    results = function.InterpretFunction(
        {'usb': os.path.join(dev_path, '..')})()
    assert len(results) <= 1
    if len(results) == 1:
      result.update(results[0])
    else:
      return None

    # Get video4linux2 (v4l2) result.
    video_idx = re.search(r'video(\d+)$', dir_path).group(1)
    v4l2_data = v4l2_utils.GetV4L2Data(int(video_idx))
    if v4l2_data:
      result.update(v4l2_data)

    return result
