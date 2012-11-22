# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''File-related utilities...'''


from contextlib import contextmanager

import logging
import os
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
