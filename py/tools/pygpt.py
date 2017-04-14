#!/usr/bin/python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""An utility to manipulate GPT on a disk image.

Chromium OS factory software usually needs to access partitions from disk
images. However, there is no good, lightweight, and portable GPT utility.
Most Chromium OS systems use `cgpt`, but that's not by default installed on
Ubuntu. Most systems have parted (GNU) or partx (util-linux-ng) but they have
their own problems.

For example, when a disk image is resized (usually enlarged for putting more
resources on stateful partition), GPT table must be updated. However,
 - `parted` can't repair partition without interactive console in exception
    handler.
 - `partx` cannot fix headers nor make changes to partition table.
 - `cgpt repair` does not fix `LastUsableLBA` so we cannot enlarge partition.
 - `gdisk` is not installed on most systems.

As a result, we need a dedicated tool to help processing GPT.

This pygpt.py provides a simple and customized implementation for processing
GPT, as a replacement for `cgpt`.
"""


from __future__ import print_function

import argparse
import binascii
import collections
import logging
import os
import struct
import uuid


# The binascii.crc32 returns signed integer, so CRC32 in in struct must be
# declared as 'signed' (l) instead of 'unsigned' (L).
# http://en.wikipedia.org/wiki/GUID_Partition_Table#Partition_table_header_.28LBA_1.29
HEADER_FORMAT = """
   8s Signature
   4s Revision
    L HeaderSize
    l CRC32
   4s Reserved
    Q CurrentLBA
    Q BackupLBA
    Q FirstUsableLBA
    Q LastUsableLBA
  16s DiskGUID
    Q PartitionEntriesStartingLBA
    L PartitionEntriesNumber
    L PartitionEntrySize
    l PartitionArrayCRC32
"""

# http://en.wikipedia.org/wiki/GUID_Partition_Table#Partition_entries
PARTITION_FORMAT = """
  16s TypeGUID
  16s UniqueGUID
    Q FirstLBA
    Q LastLBA
    Q Attributes
  72s Names
"""


def BuildStructFormatAndNamedTuple(name, description):
  """Builds the format string for struct and create corresponding namedtuple.

  Args:
    name: A string for name of the named tuple.
    description: A string with struct descriptor and attribute name.

  Returns:
    A pair of (struct_format, namedtuple_class).
  """
  elements = description.split()
  struct_format = '<' + ''.join(elements[::2])
  tuple_class = collections.namedtuple(name, elements[1::2])
  return (struct_format, tuple_class)


class GPT(object):
  """A GPT helper class.

  To load GPT from an existing disk image file, use `LoadFromFile`.
  After modifications were made, use `WriteToFile` to commit changes.

  Attributes:
    header: A namedtuple of GPT header.
    partitions: A list of GPT partition entry nametuple.
  """

  HEADER_FORMAT, HEADER_CLASS = BuildStructFormatAndNamedTuple(
      'Header', HEADER_FORMAT)
  PARTITION_FORMAT, PARTITION_CLASS = BuildStructFormatAndNamedTuple(
      'Partition', PARTITION_FORMAT)
  BLOCK_SIZE = 512
  HEADER_SIGNATURE = 'EFI PART'
  TYPE_GUID_UNUSED = '\x00' * 16
  TYPE_GUID_MAP = {
      '00000000-0000-0000-0000-000000000000': 'Unused',
      'EBD0A0A2-B9E5-4433-87C0-68B6B72699C7': 'Linux data',
      'FE3A2A5D-4F32-41A7-B725-ACCC3285A309': 'ChromeOS kernel',
      '3CB8E202-3B7E-47DD-8A3C-7FF2A13CFCEC': 'ChromeOS rootfs',
      '2E0A753D-9E48-43B0-8337-B15192CB1B5E': 'ChromeOS reserved',
      'CAB6E88E-ABF3-4102-A07A-D4BB9BE3C1D3': 'ChromeOS firmware',
      'C12A7328-F81F-11D2-BA4B-00A0C93EC93B': 'EFI System Partition',
  }
  TYPE_GUID_LIST_BOOTABLE = [
      'FE3A2A5D-4F32-41A7-B725-ACCC3285A309',  # ChromeOS kernel
      'C12A7328-F81F-11D2-BA4B-00A0C93EC93B',  # EFI System Partition
  ]

  def __init__(self):
    self.header = None
    self.partitions = None

  @staticmethod
  def GetAttributeSuccess(attrs):
    return (attrs >> 56) & 1

  @staticmethod
  def GetAttributeTries(attrs):
    return (attrs >> 52) & 0xf

  @staticmethod
  def GetAttributePriority(attrs):
    return (attrs >> 48) & 0xf

  @staticmethod
  def NewNamedTuple(base, **dargs):
    """Builds a new named tuple based on dargs."""
    # pylint: disable=protected-access
    return base._replace(**dargs)

  @classmethod
  def ReadHeader(cls, f):
    return cls.HEADER_CLASS(*struct.unpack(
        cls.HEADER_FORMAT, f.read(struct.calcsize(cls.HEADER_FORMAT))))

  @classmethod
  def ReadPartitionEntry(cls, f):
    return cls.PARTITION_CLASS(*struct.unpack(
        cls.PARTITION_FORMAT, f.read(struct.calcsize(cls.PARTITION_FORMAT))))

  @classmethod
  def GetHeaderBlob(cls, header):
    return struct.pack(cls.HEADER_FORMAT, *header)

  @classmethod
  def GetHeaderCRC32(cls, header):
    return binascii.crc32(cls.GetHeaderBlob(cls.NewNamedTuple(header, CRC32=0)))

  @classmethod
  def GetPartitionsBlob(cls, partitions):
    return ''.join(struct.pack(cls.PARTITION_FORMAT, *partition)
                   for partition in partitions)

  @classmethod
  def GetPartitionsCRC32(cls, partitions):
    return binascii.crc32(cls.GetPartitionsBlob(partitions))

  @classmethod
  def LoadFromFile(cls, f):
    """Loads a GPT table from give disk image file object."""
    gpt = GPT()
    f.seek(gpt.BLOCK_SIZE * 1)
    header = gpt.ReadHeader(f)
    if header.Signature != cls.HEADER_SIGNATURE:
      raise ValueError('Invalid signature in GPT header.')
    f.seek(gpt.BLOCK_SIZE * header.PartitionEntriesStartingLBA)
    partitions = [gpt.ReadPartitionEntry(f)
                  for unused_i in range(header.PartitionEntriesNumber)]
    gpt.header = header
    gpt.partitions = partitions
    return gpt

  def GetValidPartitions(self):
    """Returns the list of partitions before entry with empty type GUID.

    In partition table, the first entry with empty type GUID indicates end of
    valid partitions. In most implementations all partitions after that should
    be zeroed.
    """
    for i, p in enumerate(self.partitions):
      if p.TypeGUID == self.TYPE_GUID_UNUSED:
        return self.partitions[:i]
    return self.partitions

  def GetMaxUsedLBA(self):
    """Returns the max LastLBA from all valid partitions."""
    return max(p.LastLBA for p in self.GetValidPartitions())

  def GetMinUsedLBA(self):
    """Returns the min FirstLBA from all valid partitions."""
    return min(p.FirstLBA for p in self.GetValidPartitions())

  def GetPartitionTableBlocks(self, header=None):
    """Returns the blocks (or LBA) of partition table from given header."""
    if header is None:
      header = self.header
    size = header.PartitionEntrySize * header.PartitionEntriesNumber
    blocks = size / self.BLOCK_SIZE
    if size % self.BLOCK_SIZE:
      blocks += 1
    return blocks

  def Resize(self, new_size):
    """Adjust GPT for a disk image in given size.

    Args:
      new_size: Integer for new size of disk image file.
    """
    old_size = self.BLOCK_SIZE * (self.header.BackupLBA + 1)
    if new_size % self.BLOCK_SIZE:
      raise ValueError('New file size %d is not valid for image files.' %
                       new_size)
    new_blocks = new_size / self.BLOCK_SIZE
    if old_size != new_size:
      logging.warn('Image size (%d, LBA=%d) changed from %d (LBA=%d).',
                   new_size, new_blocks, old_size, old_size / self.BLOCK_SIZE)
    else:
      logging.info('Image size (%d, LBA=%d) not changed.',
                   new_size, new_blocks)

    # Re-calculate all related fields.
    backup_lba = new_blocks - 1
    partitions_blocks = self.GetPartitionTableBlocks()

    # To add allow adding more blocks for partition table, we should reserve
    # same space between primary and backup partition tables and real
    # partitions.
    min_used_lba = self.GetMinUsedLBA()
    max_used_lba = self.GetMaxUsedLBA()
    primary_reserved = min_used_lba - self.header.PartitionEntriesStartingLBA
    primary_last_lba = (self.header.PartitionEntriesStartingLBA +
                        partitions_blocks - 1)

    if primary_last_lba >= min_used_lba:
      raise ValueError('Partition table overlaps partitions.')
    if max_used_lba + partitions_blocks >= backup_lba:
      raise ValueError('Partitions overlaps backup partition table.')

    last_usable_lba = backup_lba - primary_reserved - 1
    if last_usable_lba < max_used_lba:
      last_usable_lba = max_used_lba

    self.header = self.NewNamedTuple(
        self.header,
        BackupLBA=backup_lba,
        LastUsableLBA=last_usable_lba)

  def GetFreeSpace(self):
    """Returns the free (available) space left according to LastUsableLBA."""
    max_lba = self.GetMaxUsedLBA()
    assert max_lba <= self.header.LastUsableLBA, "Partitions too large."
    return self.BLOCK_SIZE * (self.header.LastUsableLBA - max_lba)

  def ExpandPartition(self, i):
    """Expands a given partition to last usable LBA.

    Args:
      i: Index (0-based) of target partition.
    """
    # Assume no partitions overlap, we need to make sure partition[i] has
    # largest LBA.
    if i < 0 or i >= len(self.GetValidPartitions()):
      raise ValueError('Partition index %d is invalid.' % (i + 1))
    p = self.partitions[i]
    max_used_lba = self.GetMaxUsedLBA()
    if max_used_lba > p.LastLBA:
      raise ValueError('Cannot expand partition %d because it is not the last '
                       'allocated partition.' % (i + 1))

    old_blocks = p.LastLBA - p.FirstLBA + 1
    p = self.NewNamedTuple(p, LastLBA=self.header.LastUsableLBA)
    new_blocks = p.LastLBA - p.FirstLBA + 1
    self.partitions[i] = p
    logging.warn('Partition NR=%d expanded, size in LBA: %d -> %d.',
                 i + 1, old_blocks, new_blocks)

  def UpdateChecksum(self):
    """Updates all checksum values in GPT header."""
    header = self.NewNamedTuple(
        self.header,
        CRC32=0,
        PartitionArrayCRC32=self.GetPartitionsCRC32(self.partitions))
    self.header = self.NewNamedTuple(
        header,
        CRC32=self.GetHeaderCRC32(header))

  def GetBackupHeader(self):
    """Returns the backup header according to current header."""
    partitions_starting_lba = (
        self.header.BackupLBA - self.GetPartitionTableBlocks())
    header = self.NewNamedTuple(
        self.header,
        CRC32=0,
        BackupLBA=self.header.CurrentLBA,
        CurrentLBA=self.header.BackupLBA,
        PartitionEntriesStartingLBA=partitions_starting_lba)
    return self.NewNamedTuple(
        header,
        CRC32=self.GetHeaderCRC32(header))

  def WriteToFile(self, f):
    """Updates partition table in a disk image file."""

    def WriteData(name, blob, lba):
      """Writes a blob into given location."""
      logging.info('Writing %s in LBA %d (offset %d)',
                   name, lba, lba * self.BLOCK_SIZE)
      f.seek(lba * self.BLOCK_SIZE)
      f.write(blob)

    self.UpdateChecksum()
    WriteData('GPT Header', self.GetHeaderBlob(self.header),
              self.header.CurrentLBA)
    WriteData('GPT Partitions', self.GetPartitionsBlob(self.partitions),
              self.header.PartitionEntriesStartingLBA)
    logging.info('Usable LBA: First=%d, Last=%d',
                 self.header.FirstUsableLBA, self.header.LastUsableLBA)
    backup_header = self.GetBackupHeader()
    WriteData('Backup Partitions', self.GetPartitionsBlob(self.partitions),
              backup_header.PartitionEntriesStartingLBA)
    WriteData('Backup Header', self.GetHeaderBlob(backup_header),
              backup_header.CurrentLBA)


class GPTCommands(object):
  """Collection of GPT sub commands for command line to use.

  The commands are derived from `cgpt`, but not necessary to be 100% compatible
  with cgpt.
  """

  FORMAT_ARGS = [
     ('begin', 'beginning sector'),
     ('size', 'partition size'),
     ('type', 'type guid'),
     ('unique', 'unique guid'),
     ('label', 'label'),
     ('Successful', 'Successful flag'),
     ('Tries', 'Tries flag'),
     ('Priority', 'Priority flag'),
     ('Legacy', 'Legacy Boot flag'),
     ('Attribute', 'raw 16-bit attribute value (bits 48-63)')]

  def __init__(self):
    pass

  @classmethod
  def RegisterRepair(cls, p):
    """Registers the repair command to argparser.

    Args:
      p: An argparse parser instance.
    """
    p.add_argument(
        '--expand', action='store_true', default=False,
        help='Expands stateful partition to full disk.')
    p.add_argument('image_file', type=argparse.FileType('rb+'),
                   help='Disk image file to repair.')

  def Repair(self, args):
    """Repair damaged GPT headers and tables."""
    gpt = GPT.LoadFromFile(args.image_file)
    gpt.Resize(os.path.getsize(args.image_file.name))

    free_space = gpt.GetFreeSpace()
    if args.expand:
      if free_space:
        gpt.ExpandPartition(0)
      else:
        logging.warn('- No extra space to expand.')
    elif free_space:
      logging.warn('Extra space found (%d, LBA=%d), '
            'use --expand to expand partitions.',
            free_space, free_space / gpt.BLOCK_SIZE)

    gpt.WriteToFile(args.image_file)
    print('Disk image file %s repaired.' % args.image_file.name)

  @classmethod
  def RegisterShow(cls, p):
    """Registers the repair command to argparser.

    Args:
      p: An argparse parser instance.
    """
    p.add_argument('--numeric', '-n', action='store_true',
                   help='Numeric output only.')
    p.add_argument('--quick', '-q', action='store_true',
                   help='Quick output.')
    p.add_argument('--index', '-i', type=int, default=None,
                   help='Show specified partition only, with format args.')
    for name, help_str in cls.FORMAT_ARGS:
      # TODO(hungte) Alert if multiple args were specified.
      p.add_argument('--%s' % name, '-%c' % name[0], action='store_true',
                     help='[format] %s.' % help_str)
    p.add_argument('image_file', type=argparse.FileType('rb'),
                   help='Disk image file to show.')


  def Show(self, args):
    """Show partition table and entries."""

    def FormatGUID(bytes_le):
      return str(uuid.UUID(bytes_le=bytes_le)).upper()

    def FormatTypeGUID(p):
      guid_str = FormatGUID(p.TypeGUID)
      if not args.numeric:
        names = gpt.TYPE_GUID_MAP.get(guid_str)
        if names:
          return names
      return guid_str

    def FormatNames(p):
      return p.Names.decode('utf-16-le').strip('\0')

    def IsBootableType(type_guid):
      return type_guid in gpt.TYPE_GUID_LIST_BOOTABLE

    def FormatAttribute(attr):
      if args.numeric:
        return '[%x]' % (attr >> 48)
      if attr & 4:
        return 'legacy_boot=1'
      return 'priority=%d tries=%d successful=%d' % (
          gpt.GetAttributePriority(attr),
          gpt.GetAttributeTries(attr),
          gpt.GetAttributeSuccess(attr))

    def ApplyFormatArgs(p):
      if args.begin:
        return p.FirstLBA
      elif args.size:
        return p.LastLBA - p.FirstLBA + 1
      elif args.type:
        return FormatTypeGUID(p)
      elif args.unique:
        return FormatGUID(p.UniqueGUID)
      elif args.label:
        return FormatNames(p)
      elif args.Successful:
        return gpt.GetAttributeSuccess(p.Attributes)
      elif args.Priority:
        return gpt.GetAttributePriority(p.Attributes)
      elif args.Tries:
        return gpt.GetAttributeTries(p.Attributes)
      elif args.Legacy:
        raise NotImplementedError
      elif args.Attribute:
        return '[%x]' % (p.Attributes >> 48)
      else:
        return None

    def IsFormatArgsSpecified():
      return any(getattr(args, arg[0]) for arg in self.FORMAT_ARGS)

    gpt = GPT.LoadFromFile(args.image_file)
    fmt = '%12s %11s %7s  %s'
    fmt2 = '%32s  %s: %s'
    header = ('start', 'size', 'part', 'contents')

    if IsFormatArgsSpecified() and args.index is None:
      raise ValueError('Format arguments must be used with -i.')

    partitions = gpt.GetValidPartitions()
    if not (args.index is None or 0 < args.index <= len(partitions)):
      raise ValueError('Invalid partition index: %d' % args.index)

    do_print_gpt_blocks = False
    if not (args.quick or IsFormatArgsSpecified()):
      print(fmt % header)
      if args.index is None:
        do_print_gpt_blocks = True

    if do_print_gpt_blocks:
      print(fmt % (gpt.header.CurrentLBA, 1, '', 'Pri GPT header'))
      print(fmt % (gpt.header.PartitionEntriesStartingLBA,
                   gpt.GetPartitionTableBlocks(), '', 'Pri GPT table'))

    for i, p in enumerate(partitions):
      if args.index is not None and i != args.index - 1:
        continue

      if IsFormatArgsSpecified():
        print(ApplyFormatArgs(p))
        continue

      type_guid = FormatGUID(p.TypeGUID)
      print(fmt % (p.FirstLBA, p.LastLBA - p.FirstLBA + 1, i + 1,
                   FormatTypeGUID(p) if args.quick else
                   'Label: "%s"' % FormatNames(p)))

      if not args.quick:
        print(fmt2 % ('', 'Type', FormatTypeGUID(p)))
        print(fmt2 % ('', 'UUID', FormatGUID(p.UniqueGUID)))
        if args.numeric or IsBootableType(type_guid):
          print(fmt2 % ('', 'Attr', FormatAttribute(p.Attributes)))

    if do_print_gpt_blocks:
      f = args.image_file
      f.seek(gpt.header.BackupLBA * gpt.BLOCK_SIZE)
      backup_header = gpt.ReadHeader(f)
      print(fmt % (backup_header.PartitionEntriesStartingLBA,
                   gpt.GetPartitionTableBlocks(backup_header), '',
                   'Sec GPT table'))
      print(fmt % (gpt.header.BackupLBA, 1, '', 'Sec GPT header'))

  def Create(self, args):
    """Create or reset GPT headers and tables."""
    del args  # Not used yet.
    raise NotImplementedError

  def Add(self, args):
    """Add, edit or remove a partition entry."""
    del args  # Not used yet.
    raise NotImplementedError

  def Boot(self, args):
    """Edit the PMBR sector for legacy BIOSes."""
    del args  # Not used yet.
    raise NotImplementedError

  def Find(self, args):
    """Locate a partition by its GUID."""
    del args  # Not used yet.
    raise NotImplementedError

  def Prioritize(self, args):
    """Reorder the priority of all kernel partitions."""
    del args  # Not used yet.
    raise NotImplementedError

  def Legacy(self, args):
    """Switch between GPT and Legacy GPT."""
    del args  # Not used yet.
    raise NotImplementedError

  @classmethod
  def RegisterAllCommands(cls, subparsers):
    """Registers all available commands to an argparser subparsers instance."""
    subcommands = [('show', cls.Show, cls.RegisterShow),
                   ('repair', cls.Repair, cls.RegisterRepair)]
    for name, invocation, register_command in subcommands:
      register_command(subparsers.add_parser(name, help=invocation.__doc__))


def main():
  parser = argparse.ArgumentParser(description='GPT Utility.')
  parser.add_argument('--verbose', '-v', action='count', default=0,
                      help='increase verbosity.')
  parser.add_argument('--debug', '-d', action='store_true',
                      help='enable debug output.')
  subparsers = parser.add_subparsers(help='Sub-command help.', dest='command')
  GPTCommands.RegisterAllCommands(subparsers)

  args = parser.parse_args()
  log_level = max(logging.WARNING - args.verbose * 10, logging.DEBUG)
  if args.debug:
    log_level = logging.DEBUG
  logging.basicConfig(format='%(module)s:%(funcName)s %(message)s',
                      level=log_level)
  commands = GPTCommands()
  try:
    getattr(commands, args.command.capitalize())(args)
  except Exception as e:
    if args.verbose or args.debug:
      logging.exception('Failure in command [%s]', args.command)
    exit('ERROR: %s' % e)


if __name__ == '__main__':
  main()
