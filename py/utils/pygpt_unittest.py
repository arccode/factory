#!/usr/bin/env python2
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import argparse
import binascii
import os
import subprocess
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import file_utils
from cros.factory.utils import pygpt


def CheckCall(command):
  return subprocess.check_call(command, shell=True)


class GPTCommand(object):
  """Wrapper for pygpt.GPTCommand."""

  def __init__(self):
    self._runner = pygpt.GPTCommands()
    self._parser = argparse.ArgumentParser()
    self._runner.DefineArgs(self._parser)

  def RunPyGPT(self, *params):
    args = self._parser.parse_args(params)
    return self._runner.Execute(args)

  def RunCGPT(self, *params):
    return CheckCall('cgpt ' + ' '.join(params))


class GPTTest(unittest.TestCase):
  """Unit tests for pygpt.GPT."""

  def setUp(self):
    self.gpt_command = GPTCommand()
    self.temp_bin = file_utils.CreateTemporaryFile()
    CheckCall('truncate -s %s %s' % (50 * 1048576, self.temp_bin))
    self.init_commands = [
        ['create', self.temp_bin],
        ['add', '-i', '2', '-b', '34', '-s', '16384', '-t', 'kernel',
         self.temp_bin, '-S', '1', '-T', '2', '-P', '3'],
        ['add', '-i', '3', '-b', '16418', '-s', '32768', '-t', 'rootfs',
         self.temp_bin],
        ['add', '-i', '4', '-b', '49186', '-s', '1', '-t', 'kernel',
         '-P', '2', self.temp_bin],
        ['add', '-i', '5', '-b', '49187', '-s', '1', '-t', 'kernel',
         '-P', '1', self.temp_bin],
        ['add', '-i', '6', '-b', '49188', '-s', '1', '-t', 'kernel',
         '-P', '2', self.temp_bin],
        ['add', '-i', '7', '-b', '49189', '-s', '1', '-t', 'kernel',
         '-P', '0', self.temp_bin],
        ['add', '-i', '1', '-b', '49190', '-s', '32768', '-t', 'data',
         '-l', 'STATE', self.temp_bin]]

  def CheckPartitions(self, partitions):
    expected_values = [
        (49190, 81957, 'Linux data'),
        (34, 16417, 'ChromeOS kernel'),
        (16418, 49185, 'ChromeOS rootfs'),
        (49186, 49186, 'ChromeOS kernel'),
        (49187, 49187, 'ChromeOS kernel'),
        (49188, 49188, 'ChromeOS kernel'),
        (49189, 49189, 'ChromeOS kernel'),
        (0, 0, 'Unused')
    ]

    for i, v in enumerate(expected_values):
      self.assertEqual(v[0], partitions[i].FirstLBA)
      self.assertEqual(v[1], partitions[i].LastLBA)
      blocks = v[1] - v[0] + 1
      self.assertEqual(blocks, partitions[i].blocks)
      self.assertEqual(blocks * 512, partitions[i].size)
      self.assertEqual(
          v[2], pygpt.GPT.TYPE_GUID_MAP[partitions[i].TypeGUID])

    # More checks in individual partitions
    p = partitions[0]
    self.assertEqual(p.Names, 'STATE')
    p = partitions[1]
    self.assertEqual(p.Attributes.raw, 81909218222800896)
    self.assertEqual(p.Attributes.successful, 1)
    self.assertEqual(p.Attributes.tries, 2)
    self.assertEqual(p.Attributes.priority, 3)

  def tearDown(self):
    if os.path.exists(self.temp_bin):
      os.remove(self.temp_bin)

  def testLoad(self):
    for cmd in self.init_commands:
      self.gpt_command.RunCGPT(*cmd)

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

    self.CheckPartitions(gpt.partitions)
    # TODO(hungte) Add test for CheckIntegrity.

  def testRepair(self):
    for cmd in self.init_commands:
      self.gpt_command.RunCGPT(*cmd)

    with open(self.temp_bin, 'r+b') as f:
      gpt = pygpt.GPT.LoadFromFile(f)
      gpt.Resize(os.path.getsize(self.temp_bin))
      free_space = gpt.GetFreeSpace()
      self.assertEqual(free_space, 10449408)
      gpt.ExpandPartition(1)
      gpt.WriteToFile(f)

    with os.popen("cgpt show -i 1 -s %s" % self.temp_bin) as f:
      stateful_size = f.read().strip()
      self.assertEqual(int(stateful_size), 53177)

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
    self.assertEqual(gpt.GetUsedPartitions(), [])
    self.assertEqual(gpt.header.PartitionArrayCRC32,
                     binascii.crc32(''.join(p.blob for p in gpt.partitions)))

    # It is possible to check if a disk with both GPT header at block size = 512
    # and 4096 will load from 512 first, but then integrity check and partition
    # (especially decoding UTF16 for Names) would fail, so let's skip that test.
    with open(bin_file, 'r+') as f:
      f.write('\x00' * 34 * 512)

    gpt = pygpt.GPT.Create(bin_file, os.path.getsize(bin_file), 4096, 1)
    gpt.WriteToFile(bin_file)

    self.assertEqual(gpt.header.PartitionEntriesStartingLBA, 3)
    self.assertEqual(gpt.header.FirstUsableLBA, 7)
    self.assertEqual(gpt.GetUsedPartitions(), [])

  def testBoot(self):
    for cmd in self.init_commands:
      self.gpt_command.RunCGPT(*cmd)

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
    for cmd in self.init_commands:
      self.gpt_command.RunCGPT(*cmd)

    bin_file = self.temp_bin
    gpt = pygpt.GPT.LoadFromFile(bin_file)
    gpt.header.Update(Signature=gpt.header.SIGNATURES[1])
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

  def testAdd(self):
    for cmd in self.init_commands:
      self.gpt_command.RunPyGPT(*cmd)

    gpt = pygpt.GPT.LoadFromFile(self.temp_bin)
    self.CheckPartitions(gpt.partitions)

  def testPrioritize(self):
    def VerifyPriorities(values):
      gpt = pygpt.GPT.LoadFromFile(self.temp_bin)
      parts = [gpt.partitions[i] for i in [1, 3, 4, 5, 6]]
      prios = [p.Attributes.priority for p in parts]
      self.assertListEqual(prios, values)

    for cmd in self.init_commands:
      self.gpt_command.RunPyGPT(*cmd)

    VerifyPriorities([3, 2, 1, 2, 0])
    self.gpt_command.RunPyGPT('prioritize', '-P', '10', self.temp_bin)
    VerifyPriorities([10, 9, 8, 9, 0])
    self.gpt_command.RunPyGPT('prioritize', '-i', '5', self.temp_bin)
    VerifyPriorities([2, 1, 3, 1, 0])
    self.gpt_command.RunPyGPT('prioritize', '-i', '2', '-P', '5', self.temp_bin)
    VerifyPriorities([5, 3, 4, 3, 0])
    self.gpt_command.RunPyGPT('prioritize', self.temp_bin)
    VerifyPriorities([3, 1, 2, 1, 0])
    self.gpt_command.RunPyGPT('prioritize', '-i', '4', '-f', self.temp_bin)
    VerifyPriorities([2, 3, 1, 3, 0])
    self.gpt_command.RunPyGPT('prioritize', '-i', '7', self.temp_bin)
    VerifyPriorities([2, 3, 1, 3, 4])
    self.gpt_command.RunPyGPT('add', '-i', '4', '-P', '0', self.temp_bin)
    self.gpt_command.RunPyGPT('add', '-i', '5', '-P', '0', self.temp_bin)
    self.gpt_command.RunPyGPT('add', '-i', '6', '-P', '0', self.temp_bin)
    self.gpt_command.RunPyGPT('prioritize', '-i', '4', self.temp_bin)
    VerifyPriorities([1, 3, 0, 0, 2])

  def testFind(self):
    for cmd in self.init_commands:
      self.gpt_command.RunPyGPT(*cmd)

    self.assertEqual(
        0, self.gpt_command.RunPyGPT('find', '-t', 'kernel', self.temp_bin))
    self.assertEqual(
        1, self.gpt_command.RunPyGPT('find', '-t', 'efi', self.temp_bin))
    self.assertEqual(
        0, self.gpt_command.RunPyGPT('find', '-t', 'rootfs', self.temp_bin))
    self.assertEqual(0, self.gpt_command.RunPyGPT(
        'find', '-1', '-t', 'rootfs', self.temp_bin))
    self.assertEqual(1, self.gpt_command.RunPyGPT(
        'find', '-1', '-t', 'kernel', self.temp_bin))


if __name__ == '__main__':
  unittest.main()
