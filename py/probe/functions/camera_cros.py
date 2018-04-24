# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import subprocess

import factory_common  # pylint: disable=unused-import
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

  and then parses and transforms the output of that command into the probed
  results.

  Examples
  --------
  Let's assume that the output of the command ``cros-command-tool modules list``
  is ::

                Name | Vendor ID
      xy11223 7-0008 | 5c
      uv44556 30-023 | 5c

  And we have the probe statement::

    {
      "eval": "camera_cros"
    }

  The the probed results will be ::

    [
      {
        "name": "xy11223 7-0008",
        "vendor": "5c"
      },
      {
        "name": "uv44556 30-023",
        "vendor": "5c"
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

    # TODO(yhong): Add a flag for `cros-camera-tool` to dump the output
    #     in a program friendly format.

    # The format of the output is:
    #      Name | Vendor ID
    #   module1 | 123
    #   module2 | 456

    results = output.strip().splitlines()[1:]

    ret = []
    for result in results:
      module, unused_sep, vendor = result.rpartition('|')
      ret.append({'name': module.strip(), 'vendor': vendor.strip()})

    return ret
