#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Tools to mount partition in an image or a block device."""


import argparse
import logging
import os
import stat
import tempfile
import time
from contextlib import contextmanager

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn


class MountPartitionException(Exception):
  """Exception for MountPartition."""
  pass


def MountPartition(source_path, index=None, mount_point=None, rw=False):
  '''Mounts a partition in an image or a block device.

  Args:
    source_path: The image file or a block device.
    index: The index of the partition, or None to mount as a single
      partition. If source_path is a block device, index must be None.
    mount_point: The mount point.  If None, a temporary directory is used.
    rw: Whether to mount as read/write.

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

  options = '%s' % ('rw' if rw else 'ro')
  # source_path is a block device.
  if stat.S_ISBLK(os.stat(source_path).st_mode):
    if index:
      raise MountPartitionException('index must be None for a block device.')
  else:
    # Use loop option on image file.
    options += ',loop'
  if index:
    def RunCGPT(option):
      '''Runs cgpt and returns the integer result.'''
      return int(
          Spawn(['cgpt', 'show', '-i', str(index),
                 option, source_path],
                read_stdout=True, check_call=True).stdout_data)
    offset = RunCGPT('-b') * 512
    size = RunCGPT('-s') * 512
    options += ',offset=%d,sizelimit=%d' % (offset, size)
  Spawn(['mount', '-o', options, source_path, mount_point],
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

def main():
  logging.basicConfig(level=logging.INFO)
  parser = argparse.ArgumentParser(
      description="Mount a partition in an image file.")
  parser.add_argument('-rw', '--rw', action='store_true',
                      help='mount partition read/write')
  parser.add_argument('source_path', help='an image file or a block device')
  parser.add_argument('index', type=int, help='partition index')
  parser.add_argument('mount_point', help='mount point')
  args = parser.parse_args()

  MountPartition(args.source_path, args.index, args.mount_point, args.rw)

if __name__ == '__main__':
  main()
