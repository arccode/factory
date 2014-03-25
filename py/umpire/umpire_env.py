# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Common Umpire classes.

This module provides constants and common Umpire classes.
"""

import errno
import filecmp
import logging
import os

import factory_common  # pylint: disable=W0611
from cros.factory.utils import file_utils
from cros.factory.umpire.common import RESOURCE_HASH_DIGITS, UmpireError
from cros.factory.umpire import config


# File name under base_dir
_UMPIRE_CONFIG = 'umpire.yaml'
_ACTIVE_UMPIRE_CONFIG = 'active_umpire.yaml'
_STAGING_UMPIRE_CONFIG = 'staging_umpire.yaml'
_UMPIRED_PID_FILE = os.path.join('run', 'umpired.pid')
_UMPIRED_LOG_FILE = os.path.join('log', 'umpired.log')
_CLIENT_TOOLKITS_DIR = os.path.join('toolkits', 'client')
_SERVER_TOOLKITS_DIR = os.path.join('toolkits', 'server')
_RESOURCES_DIR = 'resources'

class UmpireEnv(object):
  """Provides accessors of Umpire resources.

  The base directory is obtained in constructor. If a user wants to run
  locally (e.g. --local is used), just modify self.base_dir to local
  directory and the accessors will reflect the change.

  Properties:
    base_dir: Umpire base directory
    config_path: Path of the Umpire Config file
    config: Umpire Config object
  """

  def __init__(self):
    self.base_dir = self._GetUmpireBaseDir(os.path.realpath(__file__))
    if not self.base_dir:
      logging.info('Umpire base dir not found, use current directory.')
      self.base_dir = os.getcwd()
    self.config_path = None
    self.config = None

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

  @property
  def server_toolkits_dir(self):
    return os.path.join(self.base_dir, _SERVER_TOOLKITS_DIR)

  @property
  def client_toolkits_dir(self):
    return os.path.join(self.base_dir, _CLIENT_TOOLKITS_DIR)

  @property
  def resources_dir(self):
    return os.path.join(self.base_dir, _RESOURCES_DIR)

  @property
  def umpired_pid_file(self):
    return os.path.join(self.base_dir, _UMPIRED_PID_FILE)

  @property
  def umpired_log_file(self):
    return os.path.join(self.base_dir, _UMPIRED_LOG_FILE)

  @property
  def active_config_file(self):
    return os.path.join(self.base_dir, _ACTIVE_UMPIRE_CONFIG)

  @property
  def staging_config_file(self):
    return os.path.join(self.base_dir, _STAGING_UMPIRE_CONFIG)

  def LoadConfig(self, staging=False, custom_path=None):
    """Loads Umpire config file.

    It loads user specific file if custom_path is given. Otherwise, it loads
    staging/active config depending on staging flag.
    Once the config is loaded, updates self.config and self.config_path.

    Args:
      staging: True to load staging config file. Default to load active config
          file. Unused if custom_path is specified.
      custom_path: If specified, load the config file custom_path pointing to.

    Raises:
      UmpireError if it fails to load the config file.
    """
    config_path = None
    if custom_path:
      config_path = custom_path
    else:
      config_path = (self.staging_config_file if staging else
                     self.active_config_file)

    # Update config & config_path after the config is loaded successfully.
    self.config = config.UmpireConfig(config_path)
    self.config_path = config_path

  def HasStagingConfigFile(self):
    """Checks if a staging config file exists.

    Returns:
      True if a staging config file exists.
    """
    return os.path.isfile(self.staging_config_file)

  def StageConfigFile(self, config_path, force=False):
    """Stages a config file.

    Args:
      config_path: a config file to mark as staging.
      force: True to stage the file even if it already has staging file.
    """
    if not force and self.HasStagingConfigFile():
      raise UmpireError(
          'Unable to stage a config file as another config is already staged. '
          'Check %r to decide if it should be deployed (use "umpire deploy"), '
          'edited again ("umpire edit") or discarded ("umpire unstage").' %
          self.staging_config_file)

    source = os.path.realpath(config_path)
    if not os.path.isfile(source):
      raise UmpireError("Unable to stage config %s as it doesn't exist." %
                        source)
    if force and self.HasStagingConfigFile():
      logging.info('Force staging, unstage existing one first.')
      self.UnstageConfigFile()
    logging.info('Stage config: ' + source)
    os.symlink(source, self.staging_config_file)

  def UnstageConfigFile(self):
    """Unstage the current staging config file."""
    if not self.HasStagingConfigFile():
      raise UmpireError("Unable to unstage as there's no staging config file.")
    logging.info('Unstage config: ' +
                 os.path.realpath(self.staging_config_file))
    os.unlink(self.staging_config_file)

  def AddResource(self, filename):
    """Adds a file into base_dir/resources.

    Args:
      filename: file to be added

    Returns:
      resource filename
    """
    file_utils.CheckPath(filename, 'source')
    md5 = file_utils.Md5sumInHex(filename)
    res_filename = os.path.join(
        self.resources_dir,
        '%s##%s' % (os.path.basename(filename), md5[:RESOURCE_HASH_DIGITS]))
    if os.path.isfile(res_filename):
      if filecmp.cmp(filename, res_filename, shallow=False):
        logging.warning('Skip copying as file already exists: ' + res_filename)
        return res_filename
      else:
        raise UmpireError(
            'Hash collision: file %r != resource file %r' % (filename,
                                                             res_filename))
    else:
      file_utils.AtomicCopy(filename, res_filename)
      logging.info('Resource added: ' + res_filename)
      return res_filename

  def GetResourcePath(self, resource_name, check=True):
    """Gets a resource's full path.

    Args:
      resource_name: resource name.
      check: True to check if the resource exists.

    Returns:
      Full path of the resource.

    Raises:
      IOError if the resource does not exist.
    """
    path = os.path.join(self.resources_dir, resource_name)
    if check and not os.path.exists(path):
      raise IOError(errno.ENOENT, 'Resource does not exist', path)
    return path
