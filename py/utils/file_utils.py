# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''File-related utilities...'''


from contextlib import contextmanager

import errno
import logging
import os
import shutil
import tempfile


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
