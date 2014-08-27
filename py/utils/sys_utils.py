# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A collective of system-related functions."""

import grp
import logging
import os
import pwd
import re
import stat
import struct
import tempfile
import time
from contextlib import contextmanager

import factory_common   # pylint: disable=W0611
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn


class MountPartitionException(Exception):
  """Exception for MountPartition."""
  pass


def MountPartition(source_path, index=None, mount_point=None, rw=False,
                   is_omaha_channel=False, options=None):
  '''Mounts a partition in an image or a block device.

  Args:
    source_path: The image file or a block device.
    index: The index of the partition, or None to mount as a single
      partition. If source_path is a block device, index must be None.
      Note that if is_omaha_channel is set, it is ignored.
    mount_point: The mount point.  If None, a temporary directory is used.
    rw: Whether to mount as read/write.
    is_omaha_channel: if it is True and source_path is a file, treats
      source_path as a mini-Omaha channel file (kernel+rootfs) and mounts the
      rootfs. rootfs offset bytes: 8 + BigEndian(first-8-bytes).
    options: A list of options to add to the -o argument when mounting, e.g.,
        ['offset=8192', 'sizelimit=1048576'].

  Raises:
    OSError: if image file or mount point doesn't exist.
    subprocess.CalledProcessError: if mount fails.
    MountPartitionException: if index is given while source_path is a block
      device.
  '''
  if not mount_point:
    mount_point = tempfile.mkdtemp(prefix='mount_partition.')
    remove_mount_point = True
  else:
    remove_mount_point = False

  if not os.path.exists(source_path):
    raise OSError('Image file %s does not exist' % source_path)
  if not os.path.isdir(mount_point):
    raise OSError('Mount point %s does not exist', mount_point)

  for line in open('/etc/mtab').readlines():
    if line.split()[1] == mount_point:
      raise OSError('Mount point %s is already mounted' % mount_point)

  all_options = ['rw' if rw else 'ro']
  # source_path is a block device.
  if stat.S_ISBLK(os.stat(source_path).st_mode):
    if index:
      raise MountPartitionException('index must be None for a block device.')
    if is_omaha_channel:
      raise MountPartitionException(
          'is_omaha_channel must be False for a block device.')
  else:
    # Use loop option on image file.
    all_options.append('loop')

  if is_omaha_channel:
    with open(source_path, 'rb') as f:
      first_8_bytes = f.read(8)
      offset = struct.unpack('>Q', first_8_bytes)[0] + 8
    all_options.append('offset=%d' % offset)
  elif index:
    def RunCGPT(option):
      '''Runs cgpt and returns the integer result.'''
      return int(
          Spawn(['cgpt', 'show', '-i', str(index),
                 option, source_path],
                read_stdout=True, check_call=True).stdout_data)
    offset = RunCGPT('-b') * 512
    all_options.append('offset=%d' % offset)
    sizelimit = RunCGPT('-s') * 512
    all_options.append('sizelimit=%d' % sizelimit)

  if options:
    all_options.extend(options)

  Spawn(['mount', '-o', ','.join(all_options), source_path, mount_point],
        log=True, check_call=True, sudo=True)

  @contextmanager
  def Unmounter():
    try:
      yield mount_point
    finally:
      logging.info('Unmounting %s', mount_point)
      for _ in range(5):
        if Spawn(['umount', mount_point], call=True, sudo=True,
                 ignore_stderr=True).returncode == 0:
          break
        time.sleep(1)  # And retry
      else:
        logging.warn('Unable to umount %s', mount_point)

      if remove_mount_point:
        try:
          os.rmdir(mount_point)
        except OSError:
          pass

  return Unmounter()


def MountDeviceAndReadFile(device, path):
  """Mounts a device and reads a file on it.

  Args:
    device: The device like '/dev/mmcblk0p5'.
    path: The file path like '/etc/lsb-release'. The file to read is then
      'mount_point/etc/lsb-release'.

  Returns:
    The content of the file.

  Raises:
    Exception if mount or umount fails.
    IOError if the file can not be read.
  """
  # Remove the starting / of the path.
  path = re.sub('^/', '', path)
  with MountPartition(device) as mount_point:
    logging.debug('Mounted at %s.', mount_point)
    content = open(
        os.path.join(mount_point, path)).read()
  return content


def GetInterrupts():
  """Gets the list of interrupt names and its count.

  Returns:
    A dict of interrupt names to their interrupt counts.  The interrupt names
    are all strings even if some of the names are numbers, e.g. the name for
    interrupt 88 is "88" instead of 88.
  """
  interrupt_count = {}

  lines = file_utils.ReadLines('/proc/interrupts')
  if not lines:
    raise OSError('Unable to read /proc/interrupts')

  # First line indicates CPUs in system
  num_cpus = len(lines.pop(0).split())

  for line_num, line in enumerate(lines, start=1):
    fields = line.split()
    if len(fields) < num_cpus + 1:
      logging.error('Parse error at line %d: %s', line_num, line)
      continue
    interrupt = fields[0].strip().split(':')[0]
    count = sum(map(int, fields[1:1 + num_cpus]))
    interrupt_count[interrupt] = count
    logging.debug('interrupt[%s] = %d', interrupt, count)

  return interrupt_count


def GetI2CBus(device_names):
  """Lookup I2C Bus by device name(s).

  Args:
    device_names: List of allowed device name.
                  (Ex: we can list second-source components here)

  Returns:
    I2C bus index. None if not found
  """
  blankline = re.compile(r'\n\n', flags=re.MULTILINE)
  blocks = blankline.split(file_utils.Read('/proc/bus/input/devices'))
  matched_blocks = [b for b in blocks if any(d in b for d in device_names)]
  if len(matched_blocks) == 0:
    logging.error('GetI2CBus(%r): Device is not found', device_names)
    return None
  elif len(matched_blocks) > 1:
    logging.error('GetI2CBus(%r): Multiple devices are found', device_names)
    return None
  found = re.search(r'^S: *Sysfs=.*/i2c-([0-9]+)/', matched_blocks[0],
                    flags=re.MULTILINE)
  if not found:
    logging.error('GetI2CBus(%r): Invalid format', device_names)
    return None
  return int(found.group(1))


class PartitionInfo(object):
  """A class that holds the info of a partition."""
  def __init__(self, major, minor, blocks, name):
    self.major = major
    self.minor = minor
    self.blocks = blocks
    self.name = name

  def __str__(self):
    return ('%5s %5s %10s %-20s' %
            (self.major, self.minor, self.blocks, self.name))


def GetPartitions():
  """Gets a list of partition info.

  Example content of /proc/partitions:

    major minor  #blocks  name

       8        0  976762584 sda
       8        1     248832 sda1
       8        2          1 sda2
       8        5  976510976 sda5
       8       16  175825944 sdb
       8       17  175825943 sdb1
     252        0   39059456 dm-0
     252        1  870367232 dm-1
     252        2   67031040 dm-2

  Returns:
    A list of PartitionInfo objects parsed from /proc/partitions.
  """
  line_format = re.compile(
      r'^\s*(\d+)'  # major
      r'\s*(\d+)'   # minor
      r'\s*(\d+)'   # number of blocks
      r'\s*(\w+)$'  # name
  )
  results = []
  lines = file_utils.ReadLines('/proc/partitions')
  for line in lines:
    match_obj = line_format.match(line)
    if match_obj:
      results.append(PartitionInfo(*match_obj.groups()))
  return results


def GetUidGid(user, group):
  """Gets user ID and group ID.

  Args:
    user: user name.
    group: group name.

  Returns:
    (uid, gid)

  Raises:
    KeyError if user or group is not found.
  """
  try:
    uid = pwd.getpwnam(user).pw_uid
  except KeyError:
    raise KeyError('User %r not found. Please create it.' % user)
  try:
    gid = grp.getgrnam(group).gr_gid
  except KeyError:
    raise KeyError('Group %r not found. Please create it.' % group)
  return (uid, gid)
