# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re

from cros.factory.probe.lib import cached_probe_function
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils


class GenericDRAMFunction(cached_probe_function.CachedProbeFunction):
  """Probe the generic DRAM information."""

  def GetCategoryFromArgs(self):
    return None

  @classmethod
  def ProbeAllDevices(cls):
    """Combine mosys memory timing and geometry information."""
    # TODO(tammo): Document why mosys cannot load i2c_dev itself.
    sys_utils.LoadKernelModule('i2c_dev', error_on_fail=False)
    part_data = process_utils.CheckOutput(
        'mosys -k memory spd print id', shell=True, log=True)
    size_data = process_utils.CheckOutput(
        'mosys -k memory spd print geometry', shell=True, log=True)
    parts = dict(re.findall('dimm="([^"]*)".*part_number="([^"]*)"', part_data))
    sizes = dict(re.findall('dimm="([^"]*)".*size_mb="([^"]*)"', size_data))

    results = []
    for dimm in sorted(parts):
      slot = dimm.strip()
      part = parts[dimm].strip()
      size = sizes[dimm].strip()
      results.append({
          'slot': slot,
          'part': part,
          'size': size
      })
    return results
