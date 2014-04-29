#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common helper function share between archiver and uploader."""

import fcntl
import hashlib
import os
import subprocess
import time
import yaml
import logging

from archiver_exception import ArchiverFieldError

METADATA_DIRECTORY = '.archiver'  # For storing metadata.


def IsValidYAMLFile(arg):
  """Help function to reject invalid YAML syntax"""
  if not os.path.exists(arg):
    error_str = 'The YAML config file %s does not exist!' % arg
    logging.error(error_str)
    raise IOError(error_str)
  else:
    logging.info('Verifying the YAML syntax for %r...', arg)
    try:
      with open(arg) as f:
        content = f.read()
      logging.debug('Raw YAML content:\n%r\n', content)
      yaml.load(content)
    except yaml.YAMLError as e:
      if hasattr(e, 'problem_mark'):
        logging.error('Possible syntax error is around: (line:%d, column:%d)',
                      e.problem_mark.line + 1, e.problem_mark.column + 1)
      raise e
  return arg


# TODO(itspeter):
#   Move to cros.factory.test.utils once migration to Umpire is fully
#   rolled-out.
def CheckExecutableExist(executable_name):
  """Returns a boolean if a executable is callable."""
  try:
    subprocess.check_call(['which', executable_name])
    return True
  except subprocess.CalledProcessError:
    return False


def CheckAndLockFile(lock_file_path):
  """Tries to put an advisory lock on a file.

  The current process ID will be written to the lock_file_path if lock is
  acquired.

  Args:
    lock_file_path: The path to the file needs to be locked.

  Returns:
    If lock acquired successfully, a file descriptor will be returned. The
    caller has the responsibility to keep the file descriptor away from garbage
    collection, otherwise the lock will be released automatically.
    If lock failed to acquire, the content in the file will be returned,
    usually is another process ID.
  """
  # Check if the file is already locked ?
  fd = os.fdopen(os.open(lock_file_path, os.O_RDWR | os.O_CREAT), 'r+')
  try:
    fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
  except IOError:
    with open(lock_file_path, 'r') as f:
      return f.read()

  # Write the owner's process ID.
  WriteAndTruncateFd(fd, str(os.getpid()))
  return fd


def WriteAndTruncateFd(fd, string):
  """Helper function that will write string from beginning of the file."""
  fd.seek(0)
  fd.write(string)
  fd.truncate()
  fd.flush()
  os.fsync(fd.fileno())


def TryMakeDirs(path, raise_exception=False):
  """Tries to create a directory and its parents."""
  # TODO(itspeter):
  #   switch to cros.factory.test.utils.TryMakeDirs once migration to
  #   Umpire is fully rolled-out.
  try:
    if not os.path.exists(path):
      os.makedirs(path)
  except Exception:
    if raise_exception:
      raise


# TODO(itspeter):
#   TimeString function is copy paste directly from /py/test/utils.py
#   switch to cros.factory.test.utils.TimeString once migration to
#   Umpire is fully rolled-out.
def TimeString(unix_time=None, time_separator=':', milliseconds=True):
  """Returns a time (using UTC) as a string.

  The format is like ISO8601 but with milliseconds:

   2012-05-22T14:15:08.123Z

  Args:
    unix_time: Time in seconds since the epoch.
    time_separator: Separator for time components.
    milliseconds: Whether to include milliseconds.
  """

  t = unix_time or time.time()
  ret = time.strftime(
      '%Y-%m-%dT%H' + time_separator + '%M' + time_separator + '%S',
      time.gmtime(t))
  if milliseconds:
    ret += '.%03d' % int((t - int(t)) * 1000)
  ret += 'Z'
  return ret


def GenerateArchiverMetadata(completed_bytes=0):
  """Returns a string that can be written directly into the metadata file."""
  return yaml.dump({'completed_bytes': completed_bytes})


# TODO(itspeter):
#   Move to cros.factory.test.utils once migration to Umpire is fully
#   rolled-out.
def GetMD5ForFiles(files, base_dir=None):
  """Returns a md5 for listed files.

  Args:
    files: List of files that will be hashed.
    base_dir: Base directory.

  Returns:
    A MD5 sum in hexadecimal digits.
  """
  md5_hash = hashlib.md5()  # pylint: disable=E1101
  for filename in files:
    full_path = (os.path.join(base_dir, filename) if base_dir else
                 filename)
    with open(os.path.join(full_path), 'r') as fd:
      md5_hash.update(fd.read())
  return md5_hash.hexdigest()


def GetMetadataPath(file_path, dir_path=None):
  """Returns the metadata path of file_path.

  Args:
    file_path: The path to the file that we want its metadata's path.
    dir_path:
      The directory path of the file_path. If the caller has the infomation
      of its directory name in place, we can save a call of calling
      os.path.dirname() by assigning this.

  Returns:
    The path to the metadata.
  """
  if not dir_path:
    dir_path = os.path.dirname(file_path)

  return os.path.join(
      dir_path, METADATA_DIRECTORY,
      os.path.basename(file_path) + '.metadata')


def GetOrCreateArchiverMetadata(metadata_path):
  """Returns a dictionary based on the metadata of file.

  Regenerate metadata if it is not a valid YAML format
  (syntax error or non-dictionary).

  Args:
    metadata_path: The path to the metadata.

  Returns:
    A dictionary of the parsed YAML from metadata file.
  """
  # Check if metadata directory is created.
  metadata_dir = os.path.dirname(metadata_path)
  try:
    TryMakeDirs(metadata_dir, raise_exception=True)
  except Exception:
    logging.error('Failed to create metadata directory %r for archiver',
                  metadata_dir)

  fd = os.fdopen(os.open(metadata_path, os.O_RDWR | os.O_CREAT), 'r+')
  content = fd.read()
  fd.close()
  if content:
    try:
      metadata = yaml.load(content)
      # Check if it is a dictionary
      if not isinstance(metadata, dict):
        raise ArchiverFieldError(
            'Unexpected metadata format, should be a dictionary')
      return metadata
    except (yaml.YAMLError, ArchiverFieldError):
      logging.info(
          'Metadata %r seems corrupted. YAML syntax error or not a '
          'dictionary. Reconstruct it.', metadata_path)
  return yaml.load(RegenerateArchiverMetadataFile(metadata_path))


def RegenerateArchiverMetadataFile(metadata_path):
  """Regenerates the metadata file such completed_bytes is 0.

  Args:
    metadata_path: The path to the metadata.

  Returns:
    Retrns the string it writes into the metadata_path
  """
  logging.info('Re-generate metadata at %r', metadata_path)
  ret_str = GenerateArchiverMetadata()
  with open(metadata_path, 'w') as fd:
    fd.write(ret_str)
  return ret_str
