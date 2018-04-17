#!/usr/bin/env python
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
HEADER_DESCRIPTION = """
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
PARTITION_DESCRIPTION = """
  16s TypeGUID
  16s UniqueGUID
    Q FirstLBA
    Q LastLBA
    Q Attributes
  72s Names
"""


def BitProperty(getter, setter, shift, mask):
  """A generator for bit-field properties.

  This is used inside a class to manipulate an integer-like variable using
  properties. The getter and setter should be member functions to change the
  underlying member data.

  Args:
    getter: a function to read integer type variable (for all the bits).
    setter: a function to set the new changed integer type variable.
    shift: integer for how many bits should be shifted (right).
    mask: integer for the mask to filter out bit field.
  """
  def _getter(self):
    return (getter(self) >> shift) & mask
  def _setter(self, value):
    assert value & mask == value, (
        'Value %s out of range (mask=%s)' % (value, mask))
    setter(self, getter(self) & ~(mask << shift) | value << shift)
  return property(_getter, _setter)


class GPTBlob(object):
  """A decorator class to help accessing GPT blobs as named tuple.

  To use this, specify the blob description (struct format and named tuple field
  names) above the derived class, for example:

  @GPTBlob(description):
  class Header(GPTObject):
    pass
  """
  def __init__(self, description):
    spec = description.split()
    self.struct_format = '<' + ''.join(spec[::2])
    self.fields = spec[1::2]

  def __call__(self, cls):
    new_bases = ((
        collections.namedtuple(cls.__name__, self.fields),) + cls.__bases__)
    new_cls = type(cls.__name__, new_bases, dict(cls.__dict__))
    setattr(new_cls, 'FORMAT', self.struct_format)
    return new_cls


class GPTObject(object):
  """An object in GUID Partition Table.

  This needs to be decorated by @GPTBlob(description) and inherited by a real
  class. Properties (not member functions) in CamelCase should be reserved for
  named tuple attributes.

  To create a new object, use class method ReadFrom(), which takes a stream
  as input or None to create with all elements set to zero.  To make changes to
  named tuple elements, use member function Clone(changes).

  It is also possible to attach some additional properties to the object as meta
  data (for example path of the underlying image file). To do that, specify the
  data as keyword arguments when calling ReadFrom(). These properties will be
  preserved when you call Clone().

  A special case is "reset named tuple elements of an object but keeping all
  properties", for example changing a partition object to unused (zeroed).
  ReadFrom() is a class method so properties won't be copied. You need to
  call as cls.ReadFrom(None, **p.__dict__), or a short cut - p.CloneAndZero().
  """

  FORMAT = None
  """The struct.{pack,unpack} format string, and should be set by GPTBlob."""

  CLONE_CONVERTERS = None
  """A dict (name, cvt) to convert input arguments into named tuple data.

  `name` is a string for the name of argument to convert.
  `cvt` is a callable to convert value. The return value may be:
  - a tuple in (new_name, value): save the value as new name.
  - otherwise, save the value in original name.
  Note tuple is an invalid input for struct.unpack so it's used for the
  special value.
  """

  @classmethod
  def ReadFrom(cls, f, **kargs):
    """Reads and decode an object from stream.

    Args:
      f: a stream to read blob, or None to decode with all zero bytes.
      kargs: a dict for additional attributes in object.
    """
    if f is None:
      reader = lambda num: '\x00' * num
    else:
      reader = f.read
    data = cls(*struct.unpack(cls.FORMAT, reader(struct.calcsize(cls.FORMAT))))
    # Named tuples do not accept kargs in constructor.
    data.__dict__.update(kargs)
    return data

  def Clone(self, **dargs):
    """Clones a new instance with modifications.

    GPT objects are usually named tuples that are immutable, so the only way
    to make changes is to create a new instance with modifications.

    Args:
      dargs: a dict with all modifications.
    """
    for name, convert in (self.CLONE_CONVERTERS or {}).iteritems():
      if name not in dargs:
        continue
      result = convert(dargs.pop(name))
      if isinstance(result, tuple):
        assert len(result) == 2, 'Converted tuple must be (name, value).'
        dargs[result[0]] = result[1]
      else:
        dargs[name] = result

    cloned = self._replace(**dargs)
    cloned.__dict__.update(self.__dict__)
    return cloned

  def CloneAndZero(self, **dargs):
    """Short cut to create a zeroed object while keeping all properties.

    This is very similar to Clone except all named tuple elements will be zero.
    Also different from class method ReadFrom(None) because this keeps all
    properties from one object.
    """
    cloned = self.ReadFrom(None, **self.__dict__)
    return cloned.Clone(**dargs) if dargs else cloned

  @property
  def blob(self):
    """Returns the object in formatted bytes."""
    return struct.pack(self.FORMAT, *self)


class GPT(object):
  """A GPT helper class.

  To load GPT from an existing disk image file, use `LoadFromFile`.
  After modifications were made, use `WriteToFile` to commit changes.

  Attributes:
    header: a namedtuple of GPT header.
    partitions: a list of GPT partition entry nametuple.
    block_size: integer for size of bytes in one block (sector).
  """

  DEFAULT_BLOCK_SIZE = 512
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

  @GPTBlob(HEADER_DESCRIPTION)
  class Header(GPTObject):
    """Wrapper to Header in GPT."""
    SIGNATURES = ['EFI PART', 'CHROMEOS']
    SIGNATURE_IGNORE = 'IGNOREME'
    DEFAULT_REVISION = '\x00\x00\x01\x00'

    DEFAULT_PARTITION_ENTRIES = 128
    DEFAULT_PARTITIONS_LBA = 2  # LBA 0 = MBR, LBA 1 = GPT Header.

    def Clone(self, **dargs):
      """Creates a new instance with modifications.

      GPT objects are usually named tuples that are immutable, so the only way
      to make changes is to create a new instance with modifications.

      CRC32 is always updated but PartitionArrayCRC32 must be updated explicitly
      since we can't track changes in GPT.partitions automatically.

      Note since GPTHeader.Clone will always update CRC, we can only check and
      compute CRC by super(GPT.Header, header).Clone, or header._replace.
      """
      dargs['CRC32'] = 0
      header = super(GPT.Header, self).Clone(**dargs)
      return super(GPT.Header, header).Clone(CRC32=binascii.crc32(header.blob))

  class PartitionAttributes(object):
    """Wrapper for Partition.Attributes.

    This can be created using Partition.attrs, but the changed properties won't
    apply to underlying Partition until an explicit call with
    Partition.Clone(Attributes=new_attrs).
    """

    def __init__(self, attrs):
      self._attrs = attrs

    @property
    def raw(self):
      """Returns the raw integer type attributes."""
      return self._Get()

    def _Get(self):
      return self._attrs

    def _Set(self, value):
      self._attrs = value

    successful = BitProperty(_Get, _Set, 56, 1)
    tries = BitProperty(_Get, _Set, 52, 0xf)
    priority = BitProperty(_Get, _Set, 48, 0xf)
    legacy_boot = BitProperty(_Get, _Set, 2, 1)
    required = BitProperty(_Get, _Set, 0, 1)

  @GPTBlob(PARTITION_DESCRIPTION)
  class Partition(GPTObject):
    """The partition entry in GPT.

    Please include following properties when creating a Partition object:
    - image: a string for path to the image file the partition maps to.
    - number: the 1-based partition number.
    - block_size: an integer for size of each block (LBA, or sector).
    """
    NAMES_ENCODING = 'utf-16-le'
    NAMES_LENGTH = 72

    CLONE_CONVERTERS = {
        # TODO(hungte) check if encoded name is too long.
        'label': lambda l: (None if l is None else
                            ('Names', l.encode(GPT.Partition.NAMES_ENCODING))),
        'TypeGUID': lambda v: v.bytes_le if isinstance(v, uuid.UUID) else v,
        'UniqueGUID': lambda v: v.bytes_le if isinstance(v, uuid.UUID) else v,
        'Attributes': (
            lambda v: v.raw if isinstance(v, GPT.PartitionAttributes) else v),
    }

    def __str__(self):
      return '%s#%s' % (self.image, self.number)

    def IsUnused(self):
      """Returns if the partition is unused and can be allocated."""
      return self.TypeGUID == GPT.TYPE_GUID_UNUSED

    @property
    def blocks(self):
      """Return size of partition in blocks (see block_size)."""
      return self.LastLBA - self.FirstLBA + 1

    @property
    def offset(self):
      """Returns offset to partition in bytes."""
      return self.FirstLBA * self.block_size

    @property
    def size(self):
      """Returns size of partition in bytes."""
      return self.blocks * self.block_size

    @property
    def type_guid(self):
      return uuid.UUID(bytes_le=self.TypeGUID)

    @property
    def unique_guid(self):
      return uuid.UUID(bytes_le=self.UniqueGUID)

    @property
    def label(self):
      """Returns the Names in decoded string type."""
      return self.Names.decode(self.NAMES_ENCODING).strip('\0')

    @property
    def attrs(self):
      return GPT.PartitionAttributes(self.Attributes)

  def __init__(self):
    """GPT constructor.

    See LoadFromFile for how it's usually used.
    """
    self.header = None
    self.partitions = None
    self.block_size = self.DEFAULT_BLOCK_SIZE

  @classmethod
  def LoadFromFile(cls, image):
    """Loads a GPT table from give disk image file object.

    Args:
      image: a string as file path or a file-like object to read from.
    """
    if isinstance(image, basestring):
      with open(image, 'rb') as f:
        return cls.LoadFromFile(f)

    gpt = cls()
    # Try DEFAULT_BLOCK_SIZE, then 4K.
    for block_size in [cls.DEFAULT_BLOCK_SIZE, 4096]:
      image.seek(block_size * 1)
      header = gpt.Header.ReadFrom(image)
      if header.Signature in cls.Header.SIGNATURES:
        gpt.block_size = block_size
        break
    else:
      raise ValueError('Invalid signature in GPT header.')

    image.seek(gpt.block_size * header.PartitionEntriesStartingLBA)
    def ReadPartition(image, i):
      p = gpt.Partition.ReadFrom(
          image, image=image.name, number=i + 1, block_size=gpt.block_size)
      return p

    gpt.header = header
    gpt.partitions = [
        ReadPartition(image, i) for i in range(header.PartitionEntriesNumber)]
    return gpt

  def GetValidPartitions(self):
    """Returns the list of partitions before entry with empty type GUID.

    In partition table, the first entry with empty type GUID indicates end of
    valid partitions. In most implementations all partitions after that should
    be zeroed. However, few implementations for example cgpt, may create
    partitions in arbitrary order so use this carefully.
    """
    for i, p in enumerate(self.partitions):
      if p.IsUnused():
        return self.partitions[:i]
    return self.partitions

  def GetMaxUsedLBA(self):
    """Returns the max LastLBA from all used partitions."""
    parts = [p for p in self.partitions if not p.IsUnused()]
    return (max(p.LastLBA for p in parts)
            if parts else self.header.FirstUsableLBA - 1)

  def GetPartitionTableBlocks(self, header=None):
    """Returns the blocks (or LBA) of partition table from given header."""
    if header is None:
      header = self.header
    size = header.PartitionEntrySize * header.PartitionEntriesNumber
    blocks = size / self.block_size
    if size % self.block_size:
      blocks += 1
    return blocks

  def Resize(self, new_size):
    """Adjust GPT for a disk image in given size.

    Args:
      new_size: Integer for new size of disk image file.
    """
    old_size = self.block_size * (self.header.BackupLBA + 1)
    if new_size % self.block_size:
      raise ValueError('New file size %d is not valid for image files.' %
                       new_size)
    new_blocks = new_size / self.block_size
    if old_size != new_size:
      logging.warn('Image size (%d, LBA=%d) changed from %d (LBA=%d).',
                   new_size, new_blocks, old_size, old_size / self.block_size)
    else:
      logging.info('Image size (%d, LBA=%d) not changed.',
                   new_size, new_blocks)
      return

    # Expected location
    backup_lba = new_blocks - 1
    last_usable_lba = backup_lba - self.header.FirstUsableLBA

    if last_usable_lba < self.header.LastUsableLBA:
      max_used_lba = self.GetMaxUsedLBA()
      if last_usable_lba < max_used_lba:
        raise ValueError('Backup partition tables will overlap used partitions')

    self.header = self.header.Clone(
        BackupLBA=backup_lba, LastUsableLBA=last_usable_lba)

  def GetFreeSpace(self):
    """Returns the free (available) space left according to LastUsableLBA."""
    max_lba = self.GetMaxUsedLBA()
    assert max_lba <= self.header.LastUsableLBA, "Partitions too large."
    return self.block_size * (self.header.LastUsableLBA - max_lba)

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
      raise ValueError(
          'Cannot expand partition %d because it is not the last allocated '
          'partition.' % (i + 1))

    old_blocks = p.blocks
    p = p.Clone(LastLBA=self.header.LastUsableLBA)
    new_blocks = p.blocks
    self.partitions[i] = p
    logging.warn('Partition NR=%d expanded, size in LBA: %d -> %d.',
                 i + 1, old_blocks, new_blocks)

  def UpdateChecksum(self):
    """Updates all checksum fields in GPT objects.

    The Header.CRC32 is automatically updated in Header.Clone().
    """
    parts = ''.join(p.blob for p in self.partitions)
    self.header = self.header.Clone(
        PartitionArrayCRC32=binascii.crc32(parts))

  def GetBackupHeader(self):
    """Returns the backup header according to current header."""
    partitions_starting_lba = (
        self.header.BackupLBA - self.GetPartitionTableBlocks())
    return self.header.Clone(
        BackupLBA=self.header.CurrentLBA,
        CurrentLBA=self.header.BackupLBA,
        PartitionEntriesStartingLBA=partitions_starting_lba)

  def WriteToFile(self, image):
    """Updates partition table in a disk image file.

    Args:
      image: a string as file path or a file-like object to write into.
    """
    if isinstance(image, basestring):
      with open(image, 'rb+') as f:
        return self.WriteToFile(f)

    def WriteData(name, blob, lba):
      """Writes a blob into given location."""
      logging.info('Writing %s in LBA %d (offset %d)',
                   name, lba, lba * self.block_size)
      image.seek(lba * self.block_size)
      image.write(blob)

    self.UpdateChecksum()
    parts_blob = ''.join(p.blob for p in self.partitions)
    WriteData('GPT Header', self.header.blob, self.header.CurrentLBA)
    WriteData(
        'GPT Partitions', parts_blob, self.header.PartitionEntriesStartingLBA)
    logging.info('Usable LBA: First=%d, Last=%d',
                 self.header.FirstUsableLBA, self.header.LastUsableLBA)
    backup_header = self.GetBackupHeader()
    WriteData(
        'Backup Partitions', parts_blob,
        backup_header.PartitionEntriesStartingLBA)
    WriteData('Backup Header', backup_header.blob, backup_header.CurrentLBA)


class GPTCommands(object):
  """Collection of GPT sub commands for command line to use.

  The commands are derived from `cgpt`, but not necessary to be 100% compatible
  with cgpt.
  """

  FORMAT_ARGS = [
      ('begin', 'beginning sector'),
      ('size', 'partition size (in sectors)'),
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
                   free_space, free_space / gpt.block_size)

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

    def FormatAttribute(attrs):
      if args.numeric:
        return '[%x]' % (attrs.raw >> 48)
      if attrs.legacy_boot:
        return 'legacy_boot=1'
      return 'priority=%d tries=%d successful=%d' % (
          attrs.priority, attrs.tries, attrs.successful)

    def ApplyFormatArgs(p):
      if args.begin:
        return p.FirstLBA
      elif args.size:
        return p.blocks
      elif args.type:
        return FormatTypeGUID(p)
      elif args.unique:
        return FormatGUID(p.UniqueGUID)
      elif args.label:
        return p.label
      elif args.Successful:
        return p.attrs.successful
      elif args.Priority:
        return p.attrs.priority
      elif args.Tries:
        return p.attrs.tries
      elif args.Legacy:
        return p.attrs.legacy_boot
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
          print(fmt2 % ('', 'Attr', FormatAttribute(p.attrs)))

    if do_print_gpt_blocks:
      f = args.image_file
      f.seek(gpt.header.BackupLBA * gpt.block_size)
      backup_header = gpt.Header.ReadFrom(f)
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
