# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import subprocess

from cros.factory.probe.lib import cached_probe_function
from cros.factory.utils import process_utils


class DetachableBaseFunction(cached_probe_function.CachedProbeFunction):
  """Probe the detachable base information."""

  PROGRAM = 'hammer_info.py'
  FIELDS = [
      'ro_version',
      'rw_version',
      'wp_screw',
      'wp_all',
      'touchpad_id',
      'touchpad_pid',
      'touchpad_fw_version',
      'touchpad_fw_checksum',
      'key_version',
      'challenge_status']

  def GetCategoryFromArgs(self):
    return None

  @classmethod
  def ProbeAllDevices(cls):
    try:
      ret = {}
      for field in cls.FIELDS:
        ret[field] = process_utils.CheckOutput('%s %s' % (cls.PROGRAM, field),
                                               shell=True, log=True).strip()
      return [ret]

    except subprocess.CalledProcessError:
      return []
