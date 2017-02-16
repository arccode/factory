# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils


class GenericDRAMFunction(function.ProbeFunction):
  """Probe the generic DRAM information.

  The function is ported from `py/gooftool/probe.py` module.
  """

  def Probe(self):
    """Combine mosys memory timing and geometry information."""
    # TODO(tammo): Document why mosys cannot load i2c_dev itself.
    sys_utils.LoadKernelModule('i2c_dev', error_on_fail=False)
    part_data = process_utils.CheckOutput(
        'mosys -k memory spd print id', shell=True, log=True)
    timing_data = process_utils.CheckOutput(
        'mosys -k memory spd print timings', shell=True, log=True)
    size_data = process_utils.CheckOutput(
        'mosys -k memory spd print geometry', shell=True, log=True)
    parts = dict(re.findall('dimm="([^"]*)".*part_number="([^"]*)"', part_data))
    timings = dict(re.findall('dimm="([^"]*)".*speeds="([^"]*)"', timing_data))
    sizes = dict(re.findall('dimm="([^"]*)".*size_mb="([^"]*)"', size_data))

    results = []
    for slot in sorted(parts):
      part = parts[slot]
      size = sizes[slot]
      timing = timings[slot].replace(' ', '')
      results.append({
          'slot': slot,
          'part': part,
          'size': size,
          'timing': timing})
    return results
