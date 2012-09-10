#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''Support for x86 model-specific registers.'''

import struct
import time


class MSRSnapshot(object):
  '''Snapshot of MSRs.

  Properties:
    time: The time created.
    pkg_energy_j: Joules used so far by the package.  RAPL (Running
      Average Power Limit) is used to measure this.  'pkg' refers
      to the whole CPU package.
    pkg_power_w: Power used by the package since the last snapshot.
  '''
  # MSR location for energy status.  See <http://lwn.net/Articles/444887/>.
  MSR_PKG_ENERGY_STATUS = 0x611

  # Factor to use to convert energy readings to Joules.
  ENERGY_UNIT_FACTOR = 1.53e-5

  @staticmethod
  def Read64(f, offset):
    f.seek(offset)
    return struct.unpack('Q', f.read(8))[0]

  def __init__(self, last=None):
    '''Reads MSR values.

    Args:
      last: The last snapshot read.  Deltas will be available only
        if a last snapshot is available.

    Raises:
      Exception if unable to read MSR values.
    '''
    self.time = time.time()
    with open('/dev/cpu/0/msr', 'r', 0) as f:
      self.pkg_energy_j = (
          self.Read64(f, self.MSR_PKG_ENERGY_STATUS) * self.ENERGY_UNIT_FACTOR)

    if last:
      time_delta = self.time - last.time
      self.pkg_power_w = (self.pkg_energy_j - last.pkg_energy_j) / time_delta
    else:
      self.pkg_power_w = None
