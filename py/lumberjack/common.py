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
