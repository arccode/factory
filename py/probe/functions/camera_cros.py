# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import subprocess

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils import process_utils


# TODO(yhong): Deprecate other camera related functions once
#     `cros-camera-tool` becomes a generic tool to output identities for
#     all kind of cameras.

class CameraCrosFunction(function.ProbeFunction):
  """Execute `cros-camera-tool` to list all MIPI camers."""

  ARGS = []

  def Probe(self):
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
