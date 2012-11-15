#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import logging
import os
import tempfile
import time
from contextlib import contextmanager

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn

def MountPartition(image_file, index=None, mount_point=None, rw=False):
  '''Mounts a partition in an image file.

  Args:
    image_file: The image file.
    index: The index of the partition, or None to mount as a single
      partition.
    mount_point: The mount point for the loopback mount.  If None,
      a temporary directory is used.
    rw: Whether to mount as read/write.

  Raises:
    OSError: if image file or mount point doesn't exist.
    subprocess.CalledProcessError: if mount fails.
  '''
  if not mount_point:
    mount_point = tempfile.mkdtemp(prefix='mount_partition.')
    remove_mount_point = True
  else:
    remove_mount_point = False

  if not os.path.exists(image_file):
    raise OSError('Image file %s does not exist' % image_file)
  if not os.path.isdir(mount_point):
    raise OSError('Mount point %s does not exist', mount_point)

  for line in open('/etc/mtab').readlines():
    if line.split()[1] == mount_point:
      raise OSError('Mount point %s is already mounted' % mount_point)

  options = '%s,loop' % ('rw' if rw else 'ro')
  if index:
    def RunCGPT(option):
      '''Runs cgpt and returns the integer result.'''
      return int(
          Spawn(['cgpt', 'show', '-i', str(index),
                 option, image_file],
                read_stdout=True, check_call=True).stdout_data)
    offset = RunCGPT('-b') * 512
    size = RunCGPT('-s') * 512
    options += ',offset=%d,sizelimit=%d' % (offset, size)
  Spawn(['mount', '-o', options, image_file, mount_point],
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
  parser.add_argument('image_file', help='image file')
  parser.add_argument('index', type=int, help='partition index')
  parser.add_argument('mount_point', help='mount point')
  args = parser.parse_args()

  MountPartition(args.image_file, args.index, args.mount_point, args.rw)

if __name__ == '__main__':
  main()
