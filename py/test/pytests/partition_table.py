# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Checks that the partition table extends nearly to the end of the storage
device.

Description
-----------
This test checks if the partition table allocates at least ``min_usage_pct``
percent of the storage. If not, this test expands stateful patition to the end
of the storage device by default.

This test doesn't check the actual size of the stateful partition, rather the
sector at which it ends.

This test doesn't support remote device.

Test Procedure
--------------
This is an automatic test that doesn't need any user interaction.

Dependency
----------
- `pygpt` utility.

Examples
--------
To run this pytest with default arguments, add this in test list::

  {
    "pytest_name": "partition_table"
  }

This is also predefined in ``generic_common.test_list.json`` as
``PartitionTable``.

If you can't expand stateful partition for some reason, override the argument
by::

  {
    "inherit": "PartitionTable",
    "args": {
      "expand_stateful": false
    }
  }
"""

import logging
import os

from cros.factory.device import device_utils
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import pygpt


class PartitionTableTest(test_case.TestCase):
  ARGS = [
      Arg('min_usage_pct', (int, float),
          'Percentage of the storage device that must be before the end of the '
          'stateful partition.  For example, if this is 95%, then the stateful '
          'partition must end at a sector that is >=95% of the total number of '
          'sectors on the device.',
          default=95),
      Arg('expand_stateful', bool,
          'Repair partition headers and tables and expand stateful partition '
          'to all available free space',
          default=True)
  ]

  def _ShowGPTTable(self, path):
    show_cmd = pygpt.GPTCommands.Show()
    show_cmd.ExecuteCommandLine(path)

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.gpt = None

  def runTest(self):
    self.assertTrue(self.dut.link.IsLocal(),
                    'This test only support local device')
    dev = self.dut.storage.GetMainStorageDevice()
    self.gpt = pygpt.GPT.LoadFromFile(dev)
    stateful_no = self.dut.partitions.STATEFUL.index
    stateful_part = self.gpt.GetPartition(stateful_no)
    minios_a_no = self.dut.partitions.MINIOS_A.index
    minios_a_part = self.gpt.GetPartition(minios_a_no)
    minios_b_no = self.dut.partitions.MINIOS_B.index
    start_sector = stateful_part.FirstLBA
    sector_count = stateful_part.blocks
    end_sector = start_sector + sector_count
    sector_size = self.gpt.block_size

    # Linux always considers sectors to be 512 bytes long independently of the
    # devices real block size.
    device_size = 512 * int(
        self.dut.ReadFile('/sys/class/block/%s/size' % os.path.basename(dev)))

    pct_used = end_sector * sector_size * 100 / device_size

    logging.info(
        'start_sector=%d, sector_count=%d, end_sector=%d, device_size=%d',
        start_sector, sector_count, end_sector, device_size)
    logging.info('Stateful partition extends to %.3f%% of storage',
                 pct_used)
    if pct_used < self.args.min_usage_pct:
      if not self.args.expand_stateful:
        self.FailTask('Stateful partition does not cover enough of storage '
                      'device')

      # Repair partition headers and tables
      self.gpt.Resize(pygpt.GPT.GetImageSize(dev))

      # In disk_layout_v3, minios_b is the last partition.
      # We have to remove it or we cannot expand the stateful partition.
      has_minios_b = self.gpt.IsLastPartition(minios_b_no)
      # Calculate the size of minios_a and reserve space when expanding
      # stateful partition.
      reserved_blocks = minios_a_part.blocks if has_minios_b else 0

      if has_minios_b:
        self.gpt.WriteToFile(dev)
        pygpt.RemovePartition(dev, minios_b_no)
        # Reload gpt table if we remove partition minios_b.
        self.gpt = pygpt.GPT.LoadFromFile(dev)

      _, new_blocks = self.gpt.ExpandPartition(stateful_no, reserved_blocks)
      # Write back GPT table.
      self.gpt.WriteToFile(dev)

      if not has_minios_b:
        self._ShowGPTTable(dev)
        return

      # Add back partition minios_b.
      add_cmd = pygpt.GPTCommands.Add()
      add_cmd.ExecuteCommandLine('-i', str(minios_b_no), '-t', 'minios', '-b',
                                 str(start_sector + new_blocks), '-s',
                                 str(reserved_blocks), '-l', 'MINIOS-B', dev)

      # Write the content of minios_a to minios_b_part.
      src = '%sp%d' % (dev, minios_a_no)
      dst = '%sp%d' % (dev, minios_b_no)
      self.dut.CheckCall([
          'dd', 'bs=1048576',
          'if=%s' % src,
          'of=%s' % dst, 'iflag=fullblock', 'oflag=dsync'
      ], log=True)
      self._ShowGPTTable(dev)
