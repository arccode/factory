# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Common Umpire classes.

This module provides constants and common Umpire classes.
"""

import errno
import filecmp
import logging
import os
import shutil
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.tools import get_version
from cros.factory.umpire.common import (
    GetHashFromResourceName, ResourceType, RESOURCE_HASH_DIGITS, UmpireError,
    DEFAULT_BASE_DIR)
from cros.factory.umpire import config
from cros.factory.umpire.shop_floor_manager import ShopFloorManager
from cros.factory.umpire.version import (UMPIRE_VERSION_MAJOR,
                                         UMPIRE_VERSION_MINOR)
from cros.factory.utils import file_utils


# File name under base_dir
_UMPIRE_CONFIG = 'umpire.yaml'
_ACTIVE_UMPIRE_CONFIG = 'active_umpire.yaml'
_STAGING_UMPIRE_CONFIG = 'staging_umpire.yaml'
_UMPIRED_PID_FILE = 'umpired.pid'
_UMPIRED_LOG_FILE = 'umpired.log'
_DEVICE_TOOLKITS_DIR = os.path.join('toolkits', 'device')
_SERVER_TOOLKITS_DIR = os.path.join('toolkits', 'server')
_UMPIRE_DATA_DIR = 'umpire_data'
_RESOURCES_DIR = 'resources'
_CONFIG_DIR = 'conf'
_LOG_DIR = 'log'
_PID_DIR = 'run'
_BIN_DIR = 'bin'
_WEBAPP_PORT_OFFSET = 1
_CLI_PORT_OFFSET = 2
_RPC_PORT_OFFSET = 3
_RSYNC_PORT_OFFSET = 4
# FastCGI port ranges starts at base_port + FCGI_PORTS_OFFSET.
_FCGI_PORTS_OFFSET = 10


class UmpireEnv(object):

  """Provides accessors of Umpire resources.

  The base directory is obtained in constructor. If a user wants to run
  locally (e.g. --local is used), just modify self.base_dir to local
  directory and the accessors will reflect the change.

  Properties:
    active_server_toolkit_hash: The server toolkit hash Umpire Daemon isi
                                running.
    base_dir: Umpire base directory
    config_path: Path of the Umpire Config file
    config: Active UmpireConfig object
    staging_config: Staging UmpireConfig object
    shop_floor_manager: ShopFloorManager instance
  """

  # Umpire directory permission 'rwxr-x---'.
  UMPIRE_DIR_MODE = 0750
  # Umpire exetuable permission 'rwxr-x---'.
  UMPIRE_BIN_MODE = 0750

  def __init__(self, active_server_toolkit_hash=None):
    self.active_server_toolkit_hash = active_server_toolkit_hash
    self.base_dir = self._GetUmpireBaseDir(os.path.realpath(__file__))
    if not self.base_dir:
      logging.info('Umpire base dir not found, use current directory.')
      self.base_dir = os.getcwd()
    self.config_path = None
    self.config = None
    self.staging_config = None
    self.shop_floor_manager = None

  @staticmethod
  def _GetUmpireBaseDir(path):
    """Gets Umpire base directory.

    It resolves Umpire base directory based on the given path.
    e.g. DEFAULT_BASE_DIR = '/var/db/factory/umpire',
    path = ('/var/db/factory/umpire/<board>/toolkits/server/03443c8e/'
            'usr/local/factory/py/umpire/umpire_env.py')
    Umpire base directory should be '/var/db/factory/umpire/<board>'.

    Args:
      path: a path rooted at Umpire base dir.

    Returns:
      Umpire base directory; None if DEFAULT_BASE_DIR/<board> is
      not found in path.
    """
    if path.startswith(DEFAULT_BASE_DIR + '/'):
      sub_default_base_dir_path = path[len(DEFAULT_BASE_DIR) + 1:]
      board_name = sub_default_base_dir_path.split('/')[0]
      base_directory = os.path.join(DEFAULT_BASE_DIR, board_name)
      if os.path.exists(base_directory):
        return base_directory
    return None

  @property
  def server_toolkits_dir(self):
    return os.path.join(self.base_dir, _SERVER_TOOLKITS_DIR)

  @property
  def device_toolkits_dir(self):
    return os.path.join(self.base_dir, _DEVICE_TOOLKITS_DIR)

  @property
  def active_server_toolkit_dir(self):
    return os.path.join(self.server_toolkits_dir,
                        self.active_server_toolkit_hash)

  @property
  def resources_dir(self):
    return os.path.join(self.base_dir, _RESOURCES_DIR)

  @property
  def config_dir(self):
    return os.path.join(self.base_dir, _CONFIG_DIR)

  @property
  def log_dir(self):
    return os.path.join(self.base_dir, _LOG_DIR)

  @property
  def pid_dir(self):
    return os.path.join(self.base_dir, _PID_DIR)

  @property
  def bin_dir(self):
    return os.path.join(self.base_dir, _BIN_DIR)

  @property
  def umpired_pid_file(self):
    return os.path.join(self.pid_dir, _UMPIRED_PID_FILE)

  @property
  def umpired_log_file(self):
    return os.path.join(self.log_dir, _UMPIRED_LOG_FILE)

  @property
  def active_config_file(self):
    return os.path.join(self.base_dir, _ACTIVE_UMPIRE_CONFIG)

  @property
  def staging_config_file(self):
    return os.path.join(self.base_dir, _STAGING_UMPIRE_CONFIG)

  @property
  def umpire_base_port(self):
    if not self.config:
      raise UmpireError('UmpireConfig not loaded yet.')
    if 'port' not in self.config:
      raise UmpireError('port is not defined in UmpireConfig %s' %
                        self.config_path)
    return self.config['port']

  @property
  def umpire_webapp_port(self):
    return self.umpire_base_port + _WEBAPP_PORT_OFFSET

  @property
  def umpire_cli_port(self):
    return self.umpire_base_port + _CLI_PORT_OFFSET

  @property
  def umpire_rpc_port(self):
    return self.umpire_base_port + _RPC_PORT_OFFSET

  @property
  def umpire_rsync_port(self):
    return self.umpire_base_port + _RSYNC_PORT_OFFSET

  @property
  def fastcgi_start_port(self):
    return self.umpire_base_port + _FCGI_PORTS_OFFSET

  @property
  def umpire_version_major(self):
    return UMPIRE_VERSION_MAJOR

  @property
  def umpire_version_minor(self):
    return UMPIRE_VERSION_MINOR

  @property
  def umpire_data_dir(self):
    return os.path.join(self.base_dir, _UMPIRE_DATA_DIR)

  def LoadConfig(self, custom_path=None, init_shop_floor_manager=True):
    """Loads Umpire config file and validates it.

    Also, if init_shop_floor_manager is True, it also initializes
    ShopFloorManager.

    Args:
      custom_path: If specified, load the config file custom_path pointing to.
      init_shop_floor_manager: True to init ShopFloorManager object.

    Raises:
      UmpireError if it fails to load the config file.
    """
    def _LoadValidateConfig(path):
      result = config.UmpireConfig(path)
      config.ValidateResources(result, self)
      return result

    def _InitShopFloorManager():
      # Can be obtained after a valid config is loaded.
      port_start = self.fastcgi_start_port
      if port_start:
        self.shop_floor_manager = ShopFloorManager(
            port_start, port_start + config.NUMBER_SHOP_FLOOR_HANDLERS)

    # Load active config & update config_path.
    config_path = custom_path if custom_path else self.active_config_file
    logging.debug('Load %sconfig: %s', 'active ' if not custom_path else '',
                  config_path)
    # Note that config won't be set if it fails to load/validate the new config.
    self.config = _LoadValidateConfig(config_path)
    self.config_path = config_path

    if init_shop_floor_manager:
      _InitShopFloorManager()

  def HasStagingConfigFile(self):
    """Checks if a staging config file exists.

    Returns:
      True if a staging config file exists.
    """
    return os.path.isfile(self.staging_config_file)

  def StageConfigFile(self, config_path=None, force=False):
    """Stages a config file.

    Args:
      config_path: a config file to mark as staging. Default: active file.
      force: True to stage the file even if it already has staging file.
    """
    if not force and self.HasStagingConfigFile():
      raise UmpireError(
          'Unable to stage a config file as another config is already staged. '
          'Check %r to decide if it should be deployed (use "umpire deploy"), '
          'edited again ("umpire edit") or discarded ("umpire unstage").' %
          self.staging_config_file)

    if config_path is None:
      config_path = self.active_config_file

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
    """Unstage the current staging config file.

    Returns:
      Real path of the staging file being unstaged.
    """
    if not self.HasStagingConfigFile():
      raise UmpireError("Unable to unstage as there's no staging config file.")
    staging_real_path = os.path.realpath(self.staging_config_file)
    logging.info('Unstage config: ' + staging_real_path)
    os.unlink(self.staging_config_file)
    return staging_real_path

  def ActivateConfigFile(self, config_path=None):
    """Activates a config file.

    Args:
      config_path: a config file to mark as active. Default: use staging file.
    """
    if config_path is None:
      config_path = self.staging_config_file

    if not os.path.isfile(config_path):
      raise UmpireError('Unable to activate missing config: ' + config_path)

    config_to_activate = os.path.realpath(config_path)
    if os.path.isfile(self.active_config_file):
      logging.info('Deactivate config: ' +
                   os.path.realpath(self.active_config_file))
      os.unlink(self.active_config_file)
    logging.info('Activate config: ' + config_to_activate)
    os.symlink(config_to_activate, self.active_config_file)

  def AddResource(self, file_name, res_type=None):
    """Adds a file into base_dir/resources.

    Args:
      file_name: file to be added.
      res_type: (optional) resource type. If specified, it is one of the enum
        ResourceType. It tries to get version and fills in resource file name
        <base_name>#<version>#<hash>.

    Returns:
      Resource file name (full path).
    """
    def TryGetVersion():
      """Tries to get version of the given file with res_type.

      Now it can retrive version only from file of FIRMWARE, ROOTFS_RELEASE
      and ROOTFS_TEST resource type.

      Returns:
        version string if found. '' if type is not supported or version
        failed to obtain.
      """
      if res_type is None:
        return ''

      if res_type == ResourceType.FIRMWARE:
        bios, ec = None, None
        if file_name.endswith('.gz'):
          bios, ec = get_version.GetFirmwareVersionsFromOmahaChannelFile(
              file_name)
        else:
          bios, ec = get_version.GetFirmwareVersions(file_name)
        return '%s:%s' % (bios if bios else '', ec if ec else '')

      if (res_type == ResourceType.ROOTFS_RELEASE or
          res_type == ResourceType.ROOTFS_TEST):
        version = get_version.GetReleaseVersionFromOmahaChannelFile(
            file_name, no_root=True)
        return version if version else ''

      if res_type == ResourceType.HWID:
        version = get_version.GetHWIDVersion(file_name)
        return version if version else ''

      return ''

    file_utils.CheckPath(file_name, 'source')
    basename = os.path.basename(file_name)
    version = TryGetVersion()
    md5 = file_utils.Md5sumInHex(file_name)[:RESOURCE_HASH_DIGITS]
    res_file_name = os.path.join(
        self.resources_dir,
        '#'.join([basename, version, md5]))

    if os.path.isfile(res_file_name):
      if filecmp.cmp(file_name, res_file_name, shallow=False):
        logging.warning('Skip copying as file already exists: ' + res_file_name)
        return res_file_name
      else:
        raise UmpireError(
            'Hash collision: file %r != resource file %r' % (file_name,
                                                             res_file_name))
    else:
      file_utils.AtomicCopy(file_name, res_file_name)
      logging.info('Resource added: ' + res_file_name)
      return res_file_name

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

  def InResource(self, path):
    """Checks if path points to a file in resources directory.

    Args:
      path: Either a full-path of a file or a file's basename.

    Returns:
      True if the path points to a file in resources directory.
    """
    dirname = os.path.dirname(path)
    if not dirname:
      path = self.GetResourcePath(path, check=False)
    elif dirname != self.resources_dir:
      return False
    return os.path.isfile(path)

  def GetBundleDeviceToolkit(self, bundle_id):
    """Gets a bundle's device toolkit path.

    Args:
      bundle_id: bundle ID.

    Returns:
      Full path of extracted device toolkit path.
      None if bundle_id is invalid.
    """
    bundle = self.config.GetBundle(bundle_id)
    if not bundle:
      return None
    resources = bundle.get('resources')
    if not resources:
      return None
    toolkit_resource = resources.get('device_factory_toolkit')
    if not toolkit_resource:
      return None
    toolkit_hash = GetHashFromResourceName(toolkit_resource)
    toolkit_path = os.path.join(self.device_toolkits_dir, toolkit_hash)
    if not os.path.isdir(toolkit_path):
      return None
    return toolkit_path


class UmpireEnvForTest(UmpireEnv):
  """An UmpireEnv for other unittests.

  It creates a temp directory as its base directory and creates fundamenta
  subdirectories (those which define property). The temp directory is removed
  once it is deleted.
  """
  def __init__(self):
    super(UmpireEnvForTest, self).__init__()
    self.base_dir = tempfile.mkdtemp()
    for fundamental_subdir in (
        self.config_dir,
        self.device_toolkits_dir,
        self.log_dir,
        self.pid_dir,
        self.resources_dir,
        self.server_toolkits_dir,
        self.umpire_data_dir):
      os.makedirs(fundamental_subdir)

    # Create dummy resource files.
    for res in ['complete.gz##d41d8cd9',
                'install_factory_toolkit.run##d41d8cd9',
                'efi.gz##d41d8cd9',
                'firmware.gz##d41d8cd9',
                'hwid.gz##d41d8cd9',
                'vmlinux##d41d8cd9',
                'oem.gz##d41d8cd9',
                'rootfs-release.gz##d41d8cd9',
                'rootfs-test.gz##d41d8cd9',
                'install_factory_toolkit.run##d41d8cd9',
                'state.gz##d41d8cd9']:
      file_utils.TouchFile(os.path.join(self.resources_dir, res))

  def __del__(self):
    if os.path.isdir(self.base_dir):
      shutil.rmtree(self.base_dir)
