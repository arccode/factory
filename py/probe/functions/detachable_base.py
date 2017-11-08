# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import subprocess

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils import process_utils


class DetachableBaseFunction(function.ProbeFunction):
  """Probe the detachable base information."""

  def Probe(self):
    PROGRAM = 'hammer_info.py'
    FIELDS = [
        'ro_version',
        'rw_version',
        'wp_screw',
        'touchpad_id',
        'touchpad_pid',
        'touchpad_fw_version',
        'touchpad_fw_checksum']

    ret = {}
    try:
      for field in FIELDS:
        ret[field] = process_utils.CheckOutput('%s %s' % (PROGRAM, field),
                                               shell=True, log=True).strip()
    except subprocess.CalledProcessError:
      return function.NOTHING
    return ret
