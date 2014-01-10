# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Common Umpire classes.

This module provides constants and common Umpire classes.
"""

import logging
import os

UMPIRE_CLI = 'umpire'
UMPIRE_DAEMON = 'umpired'

# File name under base_dir
UMPIRE_CONFIG = 'umpire.yaml'
ACTIVE_UMPIRE_CONFIG = 'active_umpire.yaml'
STAGING_UMPIRE_CONFIG = 'staging_umpire.yaml'
UMPIRED_PID_FILE = 'run/umpired.pid'
UMPIRED_LOG_FILE = 'log/umpired.log'

FACTORY_SOFTWARE_PACK = 'factory.par'

# Resource types which can use "umpire update" to update.
UPDATEABLE_RESOURCES = ['factory_toolkit', 'firmware', 'fsi', 'hwid']


class UmpireError(Exception):
  """General umpire exception class."""
  pass


class UmpireEnv(object):
  """Provides accessors of Umpire resources.

  The base directory is obtained in constructor. If a user wants to run
  locally (e.g. --local is used), just modify self.base_dir to local
  directory and the accessors will reflect the change.
  """
  def __init__(self):
    self.base_dir = self._GetUmpireBaseDir(os.path.realpath(__file__))
    if not self.base_dir:
      logging.info('Umpire base dir not found, use current directory.')
      self.base_dir = os.getcwd()

  @staticmethod
  def _GetUmpireBaseDir(path):
    """Gets Umpire base directory.

    It resolves Umpire base directory (ended by "umpire") based on the
    given path.

    Args:
      path: a path rooted at Umpire base dir.

    Returns:
      Umpire base directory; None if "umpire" is not found in path.
    """
    while path and path != '/':
      path, tail = os.path.split(path)
      if tail == 'umpire':
        return os.path.join(path, tail)
    return None

  def GetPidFile(self):
    return os.path.join(self.base_dir, UMPIRED_PID_FILE)

  def GetLogFile(self):
    return os.path.join(self.base_dir, UMPIRED_LOG_FILE)

  def GetActiveConfigFile(self):
    return os.path.join(self.base_dir, ACTIVE_UMPIRE_CONFIG)

  def GetStagingConfigFile(self):
    return os.path.join(self.base_dir, STAGING_UMPIRE_CONFIG)
