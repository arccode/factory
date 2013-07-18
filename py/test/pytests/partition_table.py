#!/usr/bin/python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Checks that the partition table extends nearly to the end of the storage
device.

This ensures that the device was not accidentally pre-imaged with a image for
a smaller storage device.

Note that:

- We do *not* check the actual size of the stateful partition, rather
  the sector at which it ends. If the stateful partition is not at the end,
  consider adding a mode to this test to check its size rather than its
  end sector.

- We check the entry in the partition table, not the size of the
  filesystem itself, which may be significant smaller.
"""


import logging
import os
import re
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg
from cros.factory.utils.process_utils import CheckOutput
from cros.factory.utils import file_utils


class PartitionTableTest(unittest.TestCase):
  ARGS = [
      Arg('min_usage_pct', (int, float),
          'Percentage of the storage device that must be before the end of the '
          'stateful partition.  For example, if this is 95%, then the stateful '
          'partition must end at a sector that is >=95% of the total number of '
          'sectors on the device.',
          default=95),
      ]

  longMessage = True

  def runTest(self):
    dev = file_utils.GetMainStorageDevice()
    stateful = CheckOutput(['cgpt', 'find', '-l', 'STATE', dev], log=True)

    match = re.search(r'(\d+)$', stateful)
    self.assertTrue(match,
                    'Unable to determine partition number from %r' % stateful)
    stateful_no = int(match.group(1))

    def CgptShow(flag):
      """Returns the value for 'cgpt show' with the given flag."""
      return CheckOutput(['cgpt', 'show', '-i', str(stateful_no), dev, flag]
                         ).strip()

    start_sector = int(CgptShow('-b'))
    size_sectors = int(CgptShow('-s'))
    end_sector = start_sector + size_sectors

    with open('/sys/class/block/%s/size' % os.path.basename(dev)) as f:
      device_size = int(f.read().strip())

    pct_used = end_sector * 100.0 / device_size

    logging.info(
        'start_sector=%d, size_sectors=%d, end_sector=%d, device_size=%d',
        start_sector, size_sectors, end_sector, device_size)
    logging.info('Stateful partition extends to %.3f%% of storage',
                 pct_used)
    self.assertGreaterEqual(
        pct_used, self.args.min_usage_pct,
        'Stateful partition does not cover enough of storage device')
