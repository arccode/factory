# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''File-related utilities...'''


from contextlib import contextmanager

import errno
import logging
import os
import re
import shutil
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.utils.process_utils import Spawn


@contextmanager
def UnopenedTemporaryFile(**args):
  '''Yields an unopened temporary file.

  The file is not opened, and it is deleted when the context manager
  is closed.

  Args:
    Any allowable arguments to tempfile.mkstemp (e.g., prefix,
      suffix, dir).
  '''
  f, path = tempfile.mkstemp(**args)
  os.close(f)
  try:
    yield path
  finally:
    os.unlink(path)


@contextmanager
def TempDirectory(**args):
  '''Yields an temporary directory.

  The directory is deleted when the context manager is closed.

  Args:
    Any allowable arguments to tempfile.mkdtemp (e.g., prefix,
      suffix, dir).
  '''
  path = tempfile.mkdtemp(**args)
  try:
    yield path
  finally:
    shutil.rmtree(path)


def ReadLines(filename):
  """Returns a file as list of lines.

  It is used to facilitate unittest.

  Args:
    filename: file name.

  Returns:
    List of lines of the file content. None if IOError.
  """
  try:
    with open(filename) as f:
      return f.readlines()
  except IOError as e:
    logging.error('Cannot read file "%s": %s', filename, e)
    return None


def TryUnlink(path):
  '''Unlinks a file only if it exists.

  Args:
    path: File to attempt to unlink.

  Raises:
    Any OSError thrown by unlink (except ENOENT, which means that the file
    simply didn't exist).
  '''
  try:
    os.unlink(path)
  except OSError as e:
    if e.errno != errno.ENOENT:
      raise


def WriteFile(path, data, log=False):
  """Writes a value to a file.

  Args:
    path: The path to write to.
    data: The value to write.  This may be any type and is stringified with
        str().
    log: Whether to log path and data.
  """
  data = str(data)
  if log:
    logging.info('Writing %r to %s', data, path)
  with open(path, 'w') as f:
    f.write(data)


def CopyFileSkipBytes(in_file_name, out_file_name, skip_size):
  """Copies a file and skips the first N bytes.

  Args:
    in_file_name: input file_name.
    out_file_name: output file_name.
    skip_size: number of head bytes to skip. Should be smaller than
        in_file size.

  Raises:
    ValueError if skip_size >= input file size.
  """
  in_file_size = os.path.getsize(in_file_name)
  if in_file_size <= skip_size:
    raise ValueError('skip_size: %d should be smaller than input file: %s '
                     '(size: %d)' % (skip_size, in_file_name, in_file_size))

  _CHUNK_SIZE = 4096
  with open(in_file_name, 'rb') as in_file:
    with open(out_file_name, 'wb') as out_file:
      in_file.seek(skip_size)
      shutil.copyfileobj(in_file, out_file, _CHUNK_SIZE)


def Sync(log=True):
  """Calls 'sync'."""
  Spawn(['sync'], log=log, check_call=True)


def ResetCommitTime():
  """Remounts partitions with commit=0.

  The standard value on CrOS (commit=600) is likely to result in
  corruption during factory testing.  Using commit=0 reverts to the
  default value (generally 5 s).
  """
  if utils.in_chroot():
    return

  devices = set()
  with open('/etc/mtab', 'r') as f:
    for line in f.readlines():
      cols = line.split(' ')
      device = cols[0]
      options = cols[3]
      if 'commit=' in options:
        devices.add(device)

  # Remount all devices in parallel, and wait.  Ignore errors.
  for process in [
      Spawn(['mount', p, '-o', 'commit=0,remount'], log=True)
      for p in sorted(devices)]:
    process.wait()


def GetMainStorageDevice():
  """Returns the path to the main storage device."""
  with open('/etc/mtab') as f:
    for line in f.readlines():
      fields = line.split()
      if fields[1] == '/usr/local' and fields[0].startswith('/dev/'):
        device = fields[0]
        # Remove the partition number (including the letter 'p' if any)
        # and return.
        return re.sub(r'p?(\d+)$', '', device)

  raise IOError('Unable to find main storage device in /etc/mtab')


def MountDeviceAndReadFile(device, path):
  """Mounts a device and reads a file on it.

  Args:
    device: The device like '/dev/mmcblk0p5'.
    path: The file path like '/etc/lsb-release'. The file to read is then
      'mount_point/etc/lsb-release'.

  Returns:
    The content of the file. None if the file can not be read.
  """
  # Remove the starting / of the path.
  path = re.sub('^/', '', path)
  mount_point = tempfile.mkdtemp(prefix='mount_device_and_get_file.')
  content = None
  try:
    if Spawn(['mount', '-o', 'ro', device, mount_point],
             ignore_stdout=True, ignore_stderr=True, sudo=True,
             call=True, log=True).returncode == 0:
      # Success
      logging.info('Mounted %s on %s', device, mount_point)
      content = open(
          os.path.join(mount_point, path)).read()
    else:
      logging.error('Fail to mount device %r', device)
  except IOError:
    logging.exception('Can not read file %r on device %r', path, device)
  finally:
    # Always try to unmount, even if we think the mount failed.
    if Spawn(['umount', '-l', mount_point],
             ignore_stdout=True, ignore_stderr=True, sudo=True,
             call=True, log=True).returncode == 0:
      logging.info('Unmounted %s', device)
    try:
      os.rmdir(mount_point)
    except OSError:
      logging.exception('Unable to remove %s', mount_point)
  return content
