#!/usr/bin/env python
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import binascii
import os
import subprocess
import unittest
import uuid

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import file_utils
from cros.factory.utils import pygpt


class GPTTest(unittest.TestCase):
  """Unit tests for pygpt.GPT."""

  def CheckCall(self, command):
    return subprocess.check_call(command, shell=True)

  def setUp(self):
    self.temp_bin = file_utils.CreateTemporaryFile()

    self.CheckCall('truncate -s %s %s' % (50 * 1048576, self.temp_bin))
    self.CheckCall('cgpt create %s 2>/dev/null' % self.temp_bin)
    self.CheckCall('cgpt add -i 2 -b 34 -s 16384 -t kernel %s -S 1 -T 2 -P 3' %
                   self.temp_bin)
    self.CheckCall('cgpt add -i 3 -b 16418 -s 32768 -t rootfs %s' %
                   self.temp_bin)
    self.CheckCall('cgpt add -i 1 -b 49186 -s 32768 -t data -l STATE %s' %
                   self.temp_bin)

  def tearDown(self):
    if os.path.exists(self.temp_bin):
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

    self.assertEqual(gpt.header.PartitionArrayCRC32,
                     binascii.crc32(''.join(p.blob for p in gpt.partitions)))

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
      blocks = v[1] - v[0] + 1
      self.assertEqual(blocks, partitions[i].blocks)
      self.assertEqual(blocks * 512, partitions[i].size)
      self.assertEqual(v[2], pygpt.GPT.TYPE_GUID_MAP[
          str(uuid.UUID(bytes_le=partitions[i].TypeGUID)).upper()])

    # More checks in individual partitions
    p = partitions[0]
    self.assertEqual(p.Names.decode('utf-16').strip(u'\x00'), 'STATE')
    self.assertEqual(p.label, 'STATE')
    p = partitions[1]
    self.assertEqual(p.Attributes, 81909218222800896)
    self.assertEqual(p.attrs.successful, 1)
    self.assertEqual(p.attrs.tries, 2)
    self.assertEqual(p.attrs.priority, 3)

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

  def testCreate(self):
    bin_file = self.temp_bin
    gpt = pygpt.GPT.Create(bin_file, os.path.getsize(bin_file), 512, 0)
    gpt.WriteToFile(bin_file)

    gpt = pygpt.GPT.LoadFromFile(bin_file)
    self.assertEqual(gpt.header.CurrentLBA, 1)
    self.assertEqual(gpt.header.PartitionEntriesStartingLBA, 2)
    self.assertEqual(gpt.header.FirstUsableLBA, 34)
    self.assertEqual(gpt.header.LastUsableLBA, 102366)
    self.assertEqual(gpt.header.BackupLBA, 102399)
    self.assertEqual(gpt.GetValidPartitions(), [])
    self.assertEqual(gpt.header.PartitionArrayCRC32,
                     binascii.crc32(''.join(p.blob for p in gpt.partitions)))

    gpt = pygpt.GPT.Create(bin_file, os.path.getsize(bin_file), 4096, 1)
    gpt.WriteToFile(bin_file)

    # Since the GPT on 512 was not zeroed, the loaded part should be bs=512.
    gpt = pygpt.GPT.LoadFromFile(bin_file)
    self.assertEqual(gpt.header.CurrentLBA, 1)
    self.assertEqual(gpt.block_size, 512)
    self.assertEqual(gpt.GetValidPartitions(), [])

    with open(bin_file, 'r+') as f:
      f.write('\x00' * 34 * 512)

    gpt = pygpt.GPT.Create(bin_file, os.path.getsize(bin_file), 4096, 1)
    gpt.WriteToFile(bin_file)

    self.assertEqual(gpt.header.PartitionEntriesStartingLBA, 3)
    self.assertEqual(gpt.header.FirstUsableLBA, 7)

  def testBoot(self):
    bin_file = self.temp_bin
    boot_guid = pygpt.GPT.LoadFromFile(bin_file).partitions[1].UniqueGUID
    pygpt.GPT.WriteProtectiveMBR(
        bin_file, True, bootcode='TEST', boot_guid=boot_guid)
    gpt = pygpt.GPT.LoadFromFile(bin_file)
    self.assertEqual(gpt.pmbr.BootGUID, boot_guid)
    self.assertEqual(gpt.pmbr.BootCode.strip('\0'), 'TEST')
    self.assertEqual(gpt.pmbr.Magic, gpt.ProtectiveMBR.MAGIC)
    self.assertEqual(gpt.pmbr.Signature, gpt.ProtectiveMBR.SIGNATURE)

  def testLegacy(self):
    bin_file = self.temp_bin
    gpt = pygpt.GPT.LoadFromFile(bin_file)
    gpt.header = gpt.header.Clone(Signature=gpt.header.SIGNATURES[1])
    gpt.WriteToFile(bin_file)

    gpt = pygpt.GPT.LoadFromFile(bin_file)
    self.assertEquals(gpt.header.Signature, gpt.header.SIGNATURES[1])

    with open(bin_file, 'r+') as f:
      f.seek(512)
      f.write(gpt.header.SIGNATURE_IGNORE)

    gpt = pygpt.GPT.LoadFromFile(bin_file)
    self.assertEquals(gpt.is_secondary, True)
    self.assertEquals(gpt.header.CurrentLBA, 102399)
    self.assertEquals(gpt.header.BackupLBA, 1)


if __name__ == '__main__':
  unittest.main()
