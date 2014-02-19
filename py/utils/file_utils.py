# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""File-related utilities..."""


from contextlib import contextmanager

import errno
import logging
import os
import re
import shutil
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.common import MakeList
from cros.factory.test import utils
from cros.factory.tools import mount_partition
from cros.factory.utils.process_utils import Spawn


# This should really be in this module rather than in test.utils.
# TODO: Move TryMakeDirs method to this module and update existing files
# accordingly.
TryMakeDirs = utils.TryMakeDirs


@contextmanager
def UnopenedTemporaryFile(**kwargs):
  """Yields an unopened temporary file.

  The file is not opened, and it is deleted when the context manager
  is closed.

  Args:
    Any allowable arguments to tempfile.mkstemp (e.g., prefix,
      suffix, dir).
  """
  f, path = tempfile.mkstemp(**kwargs)
  os.close(f)
  try:
    yield path
  finally:
    os.unlink(path)


@contextmanager
def TempDirectory(**kwargs):
  """Yields an temporary directory.

  The directory is deleted when the context manager is closed.

  Args:
    Any allowable arguments to tempfile.mkdtemp (e.g., prefix,
      suffix, dir).
  """
  path = tempfile.mkdtemp(**kwargs)
  try:
    yield path
  finally:
    shutil.rmtree(path)


def Read(filename):
  """Returns the content of a file.

  It is used to facilitate unittest.

  Args:
    filename: file name.

  Returns:
    File content. None if IOError.
  """
  try:
    with open(filename) as f:
      return f.read()
  except IOError as e:
    logging.error('Cannot read file "%s": %s', filename, e)
    return None


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
  """Unlinks a file only if it exists.

  Args:
    path: File to attempt to unlink.

  Raises:
    Any OSError thrown by unlink (except ENOENT, which means that the file
    simply didn't exist).
  """
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
    The content of the file.

  Raises:
    Exception if mount or umount fails.
    IOError if the file can not be read.
  """
  # Remove the starting / of the path.
  path = re.sub('^/', '', path)
  with mount_partition.MountPartition(device) as mount_point:
    logging.debug('Mounted at %s.', mount_point)
    content = open(
        os.path.join(mount_point, path)).read()
  return content


class ExtractFileError(Exception):
  """Failure of extracting compressed file."""
  pass


def ExtractFile(compressed_file, output_dir, only_extracts=None,
                overwrite=True):
  """Extracts compressed file to output folder.

  Args:
    compressed_file: Path to a compressed file.
    output_dir: The path to the output directory.
    only_extracts: An optional list of files to extract from the given
      compressed file.
    overwrite: Whether to overwrite existing files without prompt.  Defaults to
      True.

  Raises:
    ExtractFileError if the method fails to extract the file.
  """
  TryMakeDirs(output_dir)
  logging.info('Extracting %s to %s', compressed_file, output_dir)
  only_extracts = MakeList(only_extracts) if only_extracts else []
  if only_extracts:
    logging.info('Extracts only file(s): %s', only_extracts)

  if compressed_file.endswith('.zip'):
    overwrite_opt = ['-o'] if overwrite else []
    cmd = (['unzip'] + overwrite_opt + [compressed_file] +
           ['-d', output_dir] + only_extracts)
  elif (any(compressed_file.endswith(suffix) for suffix in
            ('.tar.bz2', '.tbz2', '.tar.gz', '.tgz', 'tar.xz', '.txz'))):
    overwrite_opt = [] if overwrite else ['--keep-old-files']
    cmd = (['tar', '-xvvf'] + overwrite_opt + [compressed_file] +
           ['-C', output_dir] + only_extracts)
  else:
    raise ExtractFileError('Unsupported compressed file: %s' % compressed_file)

  return Spawn(cmd, log=True, check_call=True)
