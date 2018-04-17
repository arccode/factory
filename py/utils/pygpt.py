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

# The PMBR has so many variants. The basic format is defined in
# https://en.wikipedia.org/wiki/Master_boot_record#Sector_layout, and our
# implementation, as derived from `cgpt`, is following syslinux as:
# https://chromium.googlesource.com/chromiumos/platform/vboot_reference/+/master/cgpt/cgpt.h#32
PMBR_DESCRIPTION = """
 424s BootCode
  16s BootGUID
    L DiskID
   2s Magic
  16s LegacyPart0
  16s LegacyPart1
  16s LegacyPart2
  16s LegacyPart3
   2s Signature
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


class GPTError(Exception):
  """All exceptions by GPT."""
  pass


class GPT(object):
  """A GPT helper class.

  To load GPT from an existing disk image file, use `LoadFromFile`.
  After modifications were made, use `WriteToFile` to commit changes.

  Attributes:
    header: a namedtuple of GPT header.
    pmbr: a namedtuple of Protective MBR.
    partitions: a list of GPT partition entry nametuple.
    block_size: integer for size of bytes in one block (sector).
  """

  DEFAULT_BLOCK_SIZE = 512
  TYPE_GUID_UNUSED = '\x00' * 16
  TYPE_NAME_CHROMEOS_KERNEL = 'ChromeOS kernel'
  TYPE_GUID_MAP = {
      '00000000-0000-0000-0000-000000000000': 'Unused',
      'EBD0A0A2-B9E5-4433-87C0-68B6B72699C7': 'Linux data',
      'FE3A2A5D-4F32-41A7-B725-ACCC3285A309': TYPE_NAME_CHROMEOS_KERNEL,
      '3CB8E202-3B7E-47DD-8A3C-7FF2A13CFCEC': 'ChromeOS rootfs',
      '2E0A753D-9E48-43B0-8337-B15192CB1B5E': 'ChromeOS reserved',
      'CAB6E88E-ABF3-4102-A07A-D4BB9BE3C1D3': 'ChromeOS firmware',
      'C12A7328-F81F-11D2-BA4B-00A0C93EC93B': 'EFI System Partition',
  }
  TYPE_GUID_LIST_BOOTABLE = [
      'FE3A2A5D-4F32-41A7-B725-ACCC3285A309',  # ChromeOS kernel
      'C12A7328-F81F-11D2-BA4B-00A0C93EC93B',  # EFI System Partition
  ]

  @GPTBlob(PMBR_DESCRIPTION)
  class ProtectiveMBR(GPTObject):
    """Protective MBR (PMBR) in GPT."""
    SIGNATURE = '\x55\xAA'
    MAGIC = '\x1d\x9a'

    CLONE_CONVERTERS = {
        'BootGUID': lambda v: v.bytes_le if isinstance(v, uuid.UUID) else v
    }

    @property
    def boot_guid(self):
      """Returns the BootGUID in decoded (uuid.UUID) format."""
      return uuid.UUID(bytes_le=self.BootGUID)

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

    @classmethod
    def Create(cls, size, block_size, pad_blocks=0,
               part_entries=DEFAULT_PARTITION_ENTRIES):
      """Creates a header with default values.

      Args:
        size: integer of expected image size.
        block_size: integer for size of each block (sector).
        pad_blocks: number of preserved sectors between header and partitions.
        part_entries: number of partitions to include in header.
      """
      part_entry_size = struct.calcsize(GPT.Partition.FORMAT)
      parts_lba = cls.DEFAULT_PARTITIONS_LBA + pad_blocks
      parts_bytes = part_entries * part_entry_size
      parts_blocks = parts_bytes / block_size
      if parts_bytes % block_size:
        parts_blocks += 1
      # PartitionsCRC32 must be updated later explicitly.
      return cls.ReadFrom(None).Clone(
          Signature=cls.SIGNATURES[0],
          Revision=cls.DEFAULT_REVISION,
          HeaderSize=struct.calcsize(cls.FORMAT),
          CurrentLBA=1,
          BackupLBA=size / block_size - 1,
          FirstUsableLBA=parts_lba + parts_blocks,
          LastUsableLBA=size / block_size - parts_blocks - parts_lba,
          DiskGUID=uuid.uuid4().get_bytes(),
          PartitionEntriesStartingLBA=parts_lba,
          PartitionEntriesNumber=part_entries,
          PartitionEntrySize=part_entry_size,
      )

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

    @classmethod
    def Create(cls, block_size, image, number):
      """Creates a new partition entry with given meta data."""
      part = cls.ReadFrom(
          None, image=image, number=number, block_size=block_size)
      return part

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
    self.pmbr = None
    self.header = None
    self.partitions = None
    self.block_size = self.DEFAULT_BLOCK_SIZE

  @classmethod
  def Create(cls, image_name, size, block_size, pad_blocks=0):
    """Creates a new GPT instance from given size and block_size.

    Args:
      image_name: a string of underlying disk image file name.
      size: expected size of disk image.
      block_size: size of each block (sector) in bytes.
      pad_blocks: number of blocks between header and partitions array.
    """
    gpt = cls()
    gpt.block_size = block_size
    gpt.header = cls.Header.Create(size, block_size, pad_blocks)
    gpt.partitions = [
        cls.Partition.Create(block_size, image_name, i + 1)
        for i in xrange(gpt.header.PartitionEntriesNumber)]
    return gpt

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
    image.seek(0)
    pmbr = gpt.ProtectiveMBR.ReadFrom(image)
    if pmbr.Signature == cls.ProtectiveMBR.SIGNATURE:
      logging.debug('Found MBR signature in %s', image.name)
      if pmbr.Magic == cls.ProtectiveMBR.MAGIC:
        logging.debug('Found PMBR in %s', image.name)
        gpt.pmbr = pmbr

    # Try DEFAULT_BLOCK_SIZE, then 4K.
    for block_size in [cls.DEFAULT_BLOCK_SIZE, 4096]:
      image.seek(block_size * 1)
      header = gpt.Header.ReadFrom(image)
      if header.Signature in cls.Header.SIGNATURES:
        gpt.block_size = block_size
        break
    else:
      raise GPTError('Invalid signature in GPT header.')

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
      raise GPTError(
          'New file size %d is not valid for image files.' % new_size)
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
        raise GPTError('Backup partition tables will overlap used partitions')

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

    Returns:
      (old_blocks, new_blocks) for size in blocks.
    """
    # Assume no partitions overlap, we need to make sure partition[i] has
    # largest LBA.
    if i < 0 or i >= len(self.GetValidPartitions()):
      raise GPTError('Partition number %d is invalid.' % (i + 1))
    p = self.partitions[i]
    max_used_lba = self.GetMaxUsedLBA()
    if max_used_lba > p.LastLBA:
      raise GPTError(
          'Cannot expand partition %d because it is not the last allocated '
          'partition.' % (i + 1))

    old_blocks = p.blocks
    p = p.Clone(LastLBA=self.header.LastUsableLBA)
    new_blocks = p.blocks
    self.partitions[i] = p
    logging.warn(
        '%s expanded, size in LBA: %d -> %d.', p, old_blocks, new_blocks)
    return (old_blocks, new_blocks)

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

  @classmethod
  def WriteProtectiveMBR(cls, image, create, bootcode=None, boot_guid=None):
    """Writes a protective MBR to given file.

    Each MBR is 512 bytes: 424 bytes for bootstrap code, 16 bytes of boot GUID,
    4 bytes of disk id, 2 bytes of bootcode magic, 4*16 for 4 partitions, and 2
    byte as signature. cgpt has hard-coded the CHS and bootstrap magic values so
    we can follow that.

    Args:
      create: True to re-create PMBR structure.
      bootcode: a blob of new boot code.
      boot_guid a blob for new boot GUID.

    Returns:
      The written PMBR structure.
    """
    if isinstance(image, basestring):
      with open(image, 'rb+') as f:
        return cls.WriteProtectiveMBR(f, create, bootcode, boot_guid)

    image.seek(0)
    assert struct.calcsize(cls.ProtectiveMBR.FORMAT) == cls.DEFAULT_BLOCK_SIZE
    pmbr = cls.ProtectiveMBR.ReadFrom(image)

    if create:
      legacy_sectors = min(
          0x100000000,
          os.path.getsize(image.name) / cls.DEFAULT_BLOCK_SIZE) - 1
      # Partition 0 must have have the fixed CHS with number of sectors
      # (calculated as legacy_sectors later).
      part0 = ('00000200eeffffff01000000'.decode('hex') +
               struct.pack('<I', legacy_sectors))
      # Partition 1~3 should be all zero.
      part1 = '\x00' * 16
      assert len(part0) == len(part1) == 16, 'MBR entry is wrong.'
      pmbr = pmbr.Clone(
          BootGUID=cls.TYPE_GUID_UNUSED,
          DiskID=0,
          Magic=cls.ProtectiveMBR.MAGIC,
          LegacyPart0=part0,
          LegacyPart1=part1,
          LegacyPart2=part1,
          LegacyPart3=part1,
          Signature=cls.ProtectiveMBR.SIGNATURE)

    if bootcode:
      if len(bootcode) > len(pmbr.BootCode):
        logging.info(
            'Bootcode is larger (%d > %d)!', len(bootcode), len(pmbr.BootCode))
        bootcode = bootcode[:len(pmbr.BootCode)]
      pmbr = pmbr.Clone(BootCode=bootcode)
    if boot_guid:
      pmbr = pmbr.Clone(BootGUID=boot_guid)

    blob = pmbr.blob
    assert len(blob) == cls.DEFAULT_BLOCK_SIZE
    image.seek(0)
    image.write(blob)
    return pmbr

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
    commands = dict(
        (command.lower(), getattr(self, command)())
        for command in dir(self)
        if (isinstance(getattr(self, command), type) and
            issubclass(getattr(self, command), self.SubCommand) and
            getattr(self, command) is not self.SubCommand)
    )
    self.commands = commands

  def DefineArgs(self, parser):
    """Defines all available commands to an argparser subparsers instance."""
    subparsers = parser.add_subparsers(help='Sub-command help.', dest='command')
    for name, instance in sorted(self.commands.iteritems()):
      parser = subparsers.add_parser(
          name, description=instance.__doc__,
          formatter_class=argparse.RawDescriptionHelpFormatter,
          help=instance.__doc__.splitlines()[0])
      instance.DefineArgs(parser)

  def Execute(self, args):
    """Execute the sub commands by given parsed arguments."""
    self.commands[args.command].Execute(args)

  class SubCommand(object):
    """A base class for sub commands to derive from."""

    def DefineArgs(self, parser):
      """Defines command line arguments to argparse parser.

      Args:
        parser: An argparse parser instance.
      """
      del parser  # Unused.
      raise NotImplementedError

    def Execute(self, args):
      """Execute the command.

      Args:
        args: An argparse parsed namespace.
      """
      del args  # Unused.
      raise NotImplementedError

  class Create(SubCommand):
    """Create or reset GPT headers and tables.

    Create or reset an empty GPT.
    """

    def DefineArgs(self, parser):
      parser.add_argument(
          '-z', '--zero', action='store_true',
          help='Zero the sectors of the GPT table and entries')
      parser.add_argument(
          '-p', '--pad_blocks', type=int, default=0,
          help=('Size (in blocks) of the disk to pad between the '
                'primary GPT header and its entries, default %(default)s'))
      parser.add_argument(
          '--block_size', type=int, default=GPT.DEFAULT_BLOCK_SIZE,
          help='Size of each block (sector) in bytes.')
      parser.add_argument(
          'image_file', type=argparse.FileType('rb+'),
          help='Disk image file to create.')

    def Execute(self, args):
      block_size = args.block_size
      gpt = GPT.Create(
          args.image_file.name, os.path.getsize(args.image_file.name),
          block_size, args.pad_blocks)
      if args.zero:
        # In theory we only need to clear LBA 1, but to make sure images already
        # initialized with different block size won't have GPT signature in
        # different locations, we should zero until first usable LBA.
        args.image_file.seek(0)
        args.image_file.write('\0' * block_size * gpt.header.FirstUsableLBA)
      gpt.WriteToFile(args.image_file)
      print('OK: Created GPT for %s' % args.image_file.name)

  class Boot(SubCommand):
    """Edit the PMBR sector for legacy BIOSes.

    With no options, it will just print the PMBR boot guid.
    """

    def DefineArgs(self, parser):
      parser.add_argument(
          '-i', '--number', type=int,
          help='Set bootable partition')
      parser.add_argument(
          '-b', '--bootloader', type=argparse.FileType('r'),
          help='Install bootloader code in the PMBR')
      parser.add_argument(
          '-p', '--pmbr', action='store_true',
          help='Create legacy PMBR partition table')
      parser.add_argument(
          'image_file', type=argparse.FileType('rb+'),
          help='Disk image file to change PMBR.')

    def Execute(self, args):
      """Rebuilds the protective MBR."""
      bootcode = args.bootloader.read() if args.bootloader else None
      boot_guid = None
      if args.number is not None:
        gpt = GPT.LoadFromFile(args.image_file)
        boot_guid = gpt.partitions[args.number - 1].UniqueGUID
      pmbr = GPT.WriteProtectiveMBR(
          args.image_file, args.pmbr, bootcode=bootcode, boot_guid=boot_guid)

      print(str(pmbr.boot_guid).upper())

  class Repair(SubCommand):
    """Repair damaged GPT headers and tables."""

    def DefineArgs(self, parser):
      parser.add_argument(
          'image_file', type=argparse.FileType('rb+'),
          help='Disk image file to repair.')

    def Execute(self, args):
      gpt = GPT.LoadFromFile(args.image_file)
      gpt.Resize(os.path.getsize(args.image_file.name))
      gpt.WriteToFile(args.image_file)
      print('Disk image file %s repaired.' % args.image_file.name)

  class Expand(SubCommand):
    """Expands a GPT partition to all available free space."""

    def DefineArgs(self, parser):
      parser.add_argument(
          '-i', '--number', type=int, required=True,
          help='The partition to expand.')
      parser.add_argument(
          'image_file', type=argparse.FileType('rb+'),
          help='Disk image file to modify.')

    def Execute(self, args):
      gpt = GPT.LoadFromFile(args.image_file)
      old_blocks, new_blocks = gpt.ExpandPartition(args.number - 1)
      gpt.WriteToFile(args.image_file)
      if old_blocks < new_blocks:
        print(
            'Partition %s on disk image file %s has been extended '
            'from %s to %s .' %
            (args.number, args.image_file.name, old_blocks * gpt.block_size,
             new_blocks * gpt.block_size))
      else:
        print('Nothing to expand for disk image %s partition %s.' %
              (args.image_file.name, args.number))

  class Show(SubCommand):
    """Show partition table and entries.

    Display the GPT table.
    """

    def DefineArgs(self, parser):
      parser.add_argument(
          '--numeric', '-n', action='store_true',
          help='Numeric output only.')
      parser.add_argument(
          '--quick', '-q', action='store_true',
          help='Quick output.')
      parser.add_argument(
          '-i', '--number', type=int,
          help='Show specified partition only, with format args.')
      for name, help_str in GPTCommands.FORMAT_ARGS:
        # TODO(hungte) Alert if multiple args were specified.
        parser.add_argument(
            '--%s' % name, '-%c' % name[0], action='store_true',
            help='[format] %s.' % help_str)
      parser.add_argument(
          'image_file', type=argparse.FileType('rb'),
          help='Disk image file to show.')

    def Execute(self, args):
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
        return p.label

      def IsBootableType(type_guid):
        return type_guid in gpt.TYPE_GUID_LIST_BOOTABLE

      def FormatAttribute(attrs, chromeos_kernel=False):
        if args.numeric:
          return '[%x]' % (attrs.raw >> 48)
        results = []
        if chromeos_kernel:
          results += [
              'priority=%d' % attrs.priority,
              'tries=%d' % attrs.tries,
              'successful=%d' % attrs.successful]
        if attrs.required:
          results += ['required=1']
        if attrs.legacy_boot:
          results += ['legacy_boot=1']
        return ' '.join(results)

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
          return FormatNames(p)
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
        return any(getattr(args, arg[0]) for arg in GPTCommands.FORMAT_ARGS)

      gpt = GPT.LoadFromFile(args.image_file)
      logging.debug('%r', gpt.header)
      fmt = '%12s %11s %7s  %s'
      fmt2 = '%32s  %s: %s'
      header = ('start', 'size', 'part', 'contents')

      if IsFormatArgsSpecified() and args.number is None:
        raise GPTError('Format arguments must be used with -i.')

      if not (args.number is None or
              0 < args.number <= gpt.header.PartitionEntriesNumber):
        raise GPTError('Invalid partition number: %d' % args.number)

      partitions = gpt.partitions
      do_print_gpt_blocks = False
      if not (args.quick or IsFormatArgsSpecified()):
        print(fmt % header)
        if args.number is None:
          do_print_gpt_blocks = True

      if do_print_gpt_blocks:
        print(fmt % (gpt.header.CurrentLBA, 1, '', 'Pri GPT header'))
        print(fmt % (gpt.header.PartitionEntriesStartingLBA,
                     gpt.GetPartitionTableBlocks(), '', 'Pri GPT table'))

      for p in partitions:
        if args.number is None:
          # Skip unused partitions.
          if p.IsUnused():
            continue
        elif p.number != args.number:
          continue

        if IsFormatArgsSpecified():
          print(ApplyFormatArgs(p))
          continue

        type_guid = FormatGUID(p.TypeGUID)
        print(fmt % (p.FirstLBA, p.blocks, p.number,
                     FormatTypeGUID(p) if args.quick else
                     'Label: "%s"' % FormatNames(p)))

        if not args.quick:
          print(fmt2 % ('', 'Type', FormatTypeGUID(p)))
          print(fmt2 % ('', 'UUID', FormatGUID(p.UniqueGUID)))
          if args.numeric or IsBootableType(type_guid):
            name = GPT.TYPE_GUID_MAP[type_guid]
            print(fmt2 % ('', 'Attr', FormatAttribute(
                p.attrs, name == GPT.TYPE_NAME_CHROMEOS_KERNEL)))

      if do_print_gpt_blocks:
        f = args.image_file
        f.seek(gpt.header.BackupLBA * gpt.block_size)
        header = gpt.Header.ReadFrom(f)
        print(fmt % (header.PartitionEntriesStartingLBA,
                     gpt.GetPartitionTableBlocks(header), '',
                     'Sec GPT table'))
        print(fmt % (header.CurrentLBA, 1, '', 'Sec GPT header'))


def main():
  commands = GPTCommands()
  parser = argparse.ArgumentParser(description='GPT Utility.')
  parser.add_argument('--verbose', '-v', action='count', default=0,
                      help='increase verbosity.')
  parser.add_argument('--debug', '-d', action='store_true',
                      help='enable debug output.')
  commands.DefineArgs(parser)

  args = parser.parse_args()
  log_level = max(logging.WARNING - args.verbose * 10, logging.DEBUG)
  if args.debug:
    log_level = logging.DEBUG
  logging.basicConfig(format='%(module)s:%(funcName)s %(message)s',
                      level=log_level)
  try:
    commands.Execute(args)
  except Exception as e:
    if args.verbose or args.debug:
      logging.exception('Failure in command [%s]', args.command)
    exit('ERROR: %s: %s' % (args.command, str(e) or 'Unknown error.'))


if __name__ == '__main__':
  main()
