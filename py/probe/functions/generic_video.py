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

  _probed_dev_paths = {}

  @classmethod
  def ProbeDevice(cls, dir_path):
    logging.debug('Find the node: %s', dir_path)

    dev_path = os.path.abspath(os.path.realpath(os.path.join(dir_path,
                                                             'device')))
    if dev_path not in cls._probed_dev_paths:
      # We don't know if this is an USB device or not, let's check.
      results = function.InterpretFunction(
          {'usb': os.path.join(dev_path, '..')})()
      assert len(results) <= 1

      if len(results) == 0:
        # This is not an USB component, therefore, not a USB webcam.
        # We might need to deal with this case when we have discrete GPU in the
        # future.
        cls._probed_dev_paths[dev_path] = (None, None)
      else:
        cls._probed_dev_paths[dev_path] = (results[0], [])

    result, comp_types = cls._probed_dev_paths[dev_path]
    if result is None:
      # This is not an USB component, skip.
      return None

    # Get video4linux2 (v4l2) result.
    video_idx = re.search(r'video(\d+)$', dir_path).group(1)
    comp_type = v4l2_utils.GuessComponentType(int(video_idx))
    if comp_type is not None and comp_type not in comp_types:
      assert len(comp_types) == 0, (f'A component cannot be both {comp_types} '
                                    'at the same time.')
      comp_types.append(comp_type)
      result['type'] = comp_type
      return result
    # Either comp_type is None, or we already returned probe result with this
    # type before, don't return anything in this round.
    return None
