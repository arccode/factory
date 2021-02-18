# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import subprocess

from cros.factory.probe import function
from cros.factory.probe.lib import cached_probe_function
from cros.factory.utils import process_utils


# TODO(yhong): Deprecate other camera related functions once
#     `cros-camera-tool` becomes a generic tool to output identities for
#     all kind of cameras.

class CameraCrosFunction(cached_probe_function.CachedProbeFunction):
  """Execute ``cros-camera-tool`` to list all MIPI camers.

  Description
  -----------
  This function is the interface between the command `cros-camera-tool` in the
  test image and the Probe Framework.  This function simply executes the
  command ::

    cros-camera-tool modules list

  which outputs the list of camera probe results in JSON format.

  For example, if we have the probe statement::

    {
      "eval": "camera_cros"
    }

  The probed results will look like ::

    [
      {
        "name": "uv44556 30-023",
        "module_id": "AB0001",     # Identifier data read from the camera
        "sensor_id": "CD0002"      # module's EERPOM.
      },
      {
        "name": "xy11223 7-0008",
        "vendor": "5c"             # Legacy information queried from V4L2.
      }
    ]
  """

  ARGS = []

  def GetCategoryFromArgs(self):
    return None

  @classmethod
  def ProbeAllDevices(cls):
    try:
      output = process_utils.CheckOutput(
          ['cros-camera-tool', 'modules', 'list'])
    except subprocess.CalledProcessError:
      return function.NOTHING

    results = json.loads(output)

    ret = []
    for result in results:
      # Add field ('type': 'webcam') to align with generic_video probe function.
      ret.append(
          dict({k: v.strip()
                for k, v in result.items()}, type='webcam'))

    return ret
