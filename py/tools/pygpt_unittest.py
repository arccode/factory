#!/usr/bin/env python
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import os
import subprocess
import tempfile
import unittest
import uuid

import factory_common  # pylint: disable=W0611
from cros.factory.tools import pygpt


class GPTTest(unittest.TestCase):
  """Unit tests for pygpt.GPT."""

  def CheckCall(self, command):
    return subprocess.check_call(command, shell=True)

  def setUp(self):
    fd, self.temp_bin = tempfile.mkstemp()
    os.close(fd)

    self.CheckCall('truncate -s %s %s' % (50 * 1048576, self.temp_bin))
    self.CheckCall('cgpt create %s 2>/dev/null' % self.temp_bin)
    self.CheckCall('cgpt add -i 2 -b 34 -s 16384 -t kernel %s -S 1 -T 2 -P 3' %
                   self.temp_bin)
    self.CheckCall('cgpt add -i 3 -b 16418 -s 32768 -t rootfs %s' %
                   self.temp_bin)
    self.CheckCall('cgpt add -i 1 -b 49186 -s 32768 -t data -l STATE %s' %
                   self.temp_bin)

  def tearDown(self):
    os.remove(self.temp_bin)

  def testLoad(self):
    with open(self.temp_bin, 'rb') as f:
      gpt = pygpt.GPT.LoadFromFile(f)
    header = gpt.header
    self.assertEqual(header.Signature, 'EFI PART')
    self.assertEqual(header.CurrentLBA, 1)
    self.assertEqual(header.BackupLBA, 102399)
    self.assertEqual(header.FirstUsableLBA, 34)
    self.assertEqual(header.LastUsableLBA, 102366)
    self.assertEqual(header.PartitionEntriesStartingLBA, 2)
    self.assertEqual(header.PartitionEntriesNumber, 128)
    self.assertEqual(header.PartitionEntrySize, 128)

    partitions = gpt.partitions
    expected_values = [
        (49186, 81953, 'Linux data'),
        (34, 16417, 'ChromeOS kernel'),
        (16418, 49185, 'ChromeOS rootfs'),
        (0, 0, 'Unused')
    ]

    for i, v in enumerate(expected_values):
      self.assertEqual(v[0], partitions[i].FirstLBA)
      self.assertEqual(v[1], partitions[i].LastLBA)
      self.assertEqual(v[2], pygpt.GPT.TYPE_GUID_MAP[
          str(uuid.UUID(bytes_le=partitions[i].TypeGUID)).upper()])

    # More checks in individual partitions
    p = partitions[0]
    self.assertEqual(p.Names.decode('utf-16').strip(u'\x00'), 'STATE')
    p = partitions[1]
    self.assertEqual(gpt.GetAttributeSuccess(p.Attributes), 1)
    self.assertEqual(gpt.GetAttributeTries(p.Attributes), 2)
    self.assertEqual(gpt.GetAttributePriority(p.Attributes), 3)

  def testRepair(self):
    with open(self.temp_bin, 'r+b') as f:
      gpt = pygpt.GPT.LoadFromFile(f)
      gpt.Resize(os.path.getsize(self.temp_bin))
      free_space = gpt.GetFreeSpace()
      self.assertEqual(free_space, 10451456)
      gpt.ExpandPartition(0)
      gpt.WriteToFile(f)

    with os.popen("cgpt show -i 1 -s %s" % self.temp_bin) as f:
      stateful_size = f.read().strip()
      self.assertEqual(int(stateful_size), 53181)


if __name__ == '__main__':
  unittest.main()
