#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
from contextlib import contextmanager
from glob import glob
import logging
from collections import namedtuple
import os
import re
import shutil
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.utils.process_utils import Spawn


# Info about a mounted partition.
#
# Properties:
#   dev: The device that was mounted or re-used.
#   mount_point: The mount point of the device.
#   temporary: Whether the device is being temporarily mounted.
MountUSBInfo = namedtuple('MountUSBInfo',
                          ['dev', 'mount_point', 'temporary'])


@contextmanager
def MountUSB(read_only=False):
  '''Mounts (or re-uses) a USB drive, returning the path.

  Acts as a context manager.  If we mount a partition, we will
  unmount it when exiting the context manager.

  First attempts to find a mounted USB drive; if one is found,
  its path is returned (and it will never be unmounted).

  Next attempts to mount partitions 1-9 on any USB drive.
  If this succeeds, the path is returned, and it will be unmounted
  when exiting the context manager.

  Returns:
    A MountUSBInfo object.

  Raises:
    IOError if no mounted or mountable partition is found.
  '''
  usb_devices = set(os.path.basename(x)
                    for x in glob('/sys/class/block/sd?')
                    if '/usb' in os.readlink(x))
  if not usb_devices:
    raise IOError('No USB devices available')

  # See if any are already mounted
  mount_output = Spawn(['mount'], read_stdout=True,
                       check_call=True, log=True).stdout_data
  matches = [x for x in re.findall(r'^(/dev/(sd[a-z])\d*) on (\S+)',
                                   mount_output, re.MULTILINE)
             if x[1] in usb_devices]
  if matches:
    dev, _, path = matches[0]
    # Already mounted: yield it and we're done
    logging.info('Using mounted USB drive %s on %s', dev, path)
    yield MountUSBInfo(dev=dev, mount_point=path, temporary=False)

    # Just to be on the safe side, sync once the caller says they're
    # done with it.
    Spawn(['sync'], call=True)
    return

  # Try to mount it (and unmount it later).  We'll try the whole
  # drive first, then each individual partition
  tried = []
  for usb_device in usb_devices:
    for suffix in [''] + [str(x) for x in xrange(1, 10)]:
      mount_dir = tempfile.mkdtemp(
          prefix='usb_mount.%s%s.' % (usb_device, suffix))
      dev = '/dev/%s%s' % (usb_device, suffix)
      tried.append(dev)
      try:
        if Spawn(['mount'] +
                 (['-o', 'ro'] if read_only else []) +
                 [dev, mount_dir],
                 ignore_stdout=True, log_stderr_on_error=True,
                 call=True).returncode == 0:
          # Success
          logging.info('Mounted %s on %s', dev, mount_dir)
          yield MountUSBInfo(dev=dev, mount_point=mount_dir, temporary=True)
          return
      finally:
        # Always try to unmount, even if we think the mount
        # failed.
        if Spawn(['umount', '-l', mount_dir],
                 ignore_stdout=True, ignore_stderr=True,
                 call=True).returncode == 0:
          logging.info('Unmounted %s', dev)
        try:
          os.rmdir(mount_dir)
        except OSError:
          logging.exception('Unable to remove %s', mount_dir)

  # Oh well
  raise IOError('Unable to mount any of %s' % tried)


@contextmanager
def DummyContext(arg):
  '''A context manager that simply yields its argument.'''
  yield arg


def SaveLogs(output_dir, archive_id=None):
  '''Saves dmesg and relevant log files to a new archive in output_dir.

  The archive will be named factory_bug.<description>.<timestamp>.tar.bz2,
  where description is the 'description' argument (if provided).

  Args:
    output_dir: The directory in which to create the file.
    archive_id: An optional short ID to put in the filename (so
      archives may be more easily differentiated).
  '''
  output_dir = os.path.realpath(output_dir)

  filename = 'factory_bug.'
  if archive_id:
    filename += archive_id.replace('/', '') + '.'
  filename += '%s.tar.bz2' % utils.TimeString(time_separator='_',
                                              milliseconds=False)

  output_file = os.path.join(output_dir, filename)

  tmp = tempfile.mkdtemp(prefix='factory_bug.')
  try:
    with open(os.path.join(tmp, 'crossystem'), 'w') as f:
      Spawn('crossystem', stdout=f, stderr=f, check_call=True)

      if not utils.in_chroot():
        print >> f, '\nectool version:'
        f.flush()
        Spawn(['ectool', 'version'], stdout=f, check_call=True)

    with open(os.path.join(tmp, 'dmesg'), 'w') as f:
      Spawn('dmesg', stdout=f, check_call=True)

    files = ['crossystem', 'dmesg'] + sum([glob(x) for x in [
        '/var/log',
        '/var/factory',
        '/usr/local/factory/MD5SUM',
        '/etc/lsb-release',
        '/usr/local/etc/lsb-*']], [])

    logging.info('Saving %s to %s...', files, output_file)
    process = Spawn(['tar', 'cfj', output_file] + files,
                    cwd=tmp, call=True,
                    ignore_stdout=True, log_stderr_on_error=True)
    # 0 = successful termination
    # 1 = "some files differ" (e.g., files changed while we were
    #     reading them, which is OK)
    if process.returncode not in [0, 1]:
      raise IOError('tar process failed with returncode %d' %
                    process.returncode)

    return output_file
  finally:
    shutil.rmtree(tmp, ignore_errors=True)


def main():
  logging.basicConfig(level=logging.INFO)
  parser = argparse.ArgumentParser(
      description='Save logs to a file or USB drive.')
  parser.add_argument('--output_dir', '-o', dest='output_dir', metavar='DIR',
                      default='/tmp',
                      help='output directory in which to save file')
  parser.add_argument('--usb', action='store_true',
                      help=('save logs to a USB stick (using any mounted '
                            'USB drive partition if available, otherwise '
                            'attempting to temporarily mount one)'))
  parser.add_argument('--id', '-i', metavar='ID',
                      help=('short ID to include in file name to help '
                            'differentiate archives'))
  args = parser.parse_args()

  with (MountUSB() if args.usb
        else DummyContext((None, args.output_dir))) as mount:
    output_file = SaveLogs(mount.mount_point, args.id)
    logging.info('Wrote %s (%d bytes)',
                 output_file, os.path.getsize(output_file))


if __name__ == '__main__':
  main()
