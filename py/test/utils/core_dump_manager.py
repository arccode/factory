# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os

from cros.factory.utils import sys_utils

DEFAULT_CRASH_PATH = '/var/factory/crash'


class CoreDumpManagerException(Exception):
  pass


class CoreDumpManager:
  """The manager that takes care of core dump files.

  Properties:
    crash_dir: The directory of core dump files.
    watchlist: The file patterns to match. E.g. ['*glbench*']. If it is not set
        in constructor, use [].
  """

  def __init__(self, watchlist=None, crash_dir=DEFAULT_CRASH_PATH):
    self._crash_dir = crash_dir
    self._watchlist = watchlist if watchlist else []
    self._SetCoreDump()

  @classmethod
  def CoreDumpEnabled(cls):
    return os.path.exists('/proc/sys/kernel/core_pattern')

  def _SetCoreDump(self):
    """Sets core dump files to be unlimited and set core_pattern."""
    if sys_utils.InChroot():
      return
    if not os.path.exists(self._crash_dir):
      os.mkdir(self._crash_dir)
    with open('/proc/sys/kernel/core_pattern', 'w') as f:
      f.write(os.path.join(self._crash_dir, 'core.%p:%s:%u:%e'))

  def ScanFiles(self):
    """Scans the core dump directory and returns matched list of files.

    Scans the core dump directory and check if there is any file
    matching watchlist. Delete all the files that do not match watchlist.

    Returns:
      A list of file paths that match watchlist. Returns [] if watchlist is
      not specified, or there is no matched file.

    Raises:
      CoreDumpManagerException: If CoreDumpManager fails to remove unused
          core dump files.
    """
    watched_files = sum([glob.glob(os.path.join(self._crash_dir, x))
                         for x in self._watchlist], [])

    try:
      for root, dirs, files in os.walk(self._crash_dir):
        for f in files:
          if os.path.join(root, f) not in watched_files:
            logging.warning('Remove %s because it is not in watchlist',
                            os.path.join(root, f))
            os.unlink(os.path.join(root, f))
        for d in dirs:
          os.rmdir(os.path.join(root, d))
    except Exception as e:
      logging.exception('Unable to remove unused core dump files')
      raise CoreDumpManagerException(e)
    if watched_files:
      logging.warning('Found core dump files %s !', watched_files)
    return watched_files

  def ClearFiles(self, files):
    """Removes files under core dump directory.

    Args:
      files: A list of file paths to remove. The path should be under
          crash directry.

    Raises:
      CoreDumpManagerException: If any path in files is not in crash
          directory or can not be removed.
    """
    for f in files:
      if os.path.dirname(f) != self._crash_dir:
        logging.error('Should not remove file %s that is not under'
                      ' crash directory %s', f, self._crash_dir)
        raise CoreDumpManagerException('file path is not correct')
      try:
        os.unlink(f)
      except Exception as e:
        logging.exception('Unable to remove used core dump files')
        raise CoreDumpManagerException(e)
      else:
        logging.info('Removed %s', f)
