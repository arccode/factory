# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common Umpire classes.

This module provides constants and common Umpire classes.
"""

import filecmp
import json
import logging
import os
import shutil
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common
from cros.factory.umpire import config
from cros.factory.umpire import resource
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


CROS_PAYLOAD = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    '..', '..', 'bin', 'cros_payload')
# File name under base_dir
_ACTIVE_UMPIRE_CONFIG = 'active_umpire.yaml'
_STAGING_UMPIRE_CONFIG = 'staging_umpire.yaml'
_UMPIRED_PID_FILE = 'umpired.pid'
_UMPIRED_LOG_FILE = 'umpired.log'
_DEVICE_TOOLKITS_DIR = os.path.join('toolkits', 'device')
_UMPIRE_DATA_DIR = 'umpire_data'
_RESOURCES_DIR = 'resources'
_CONFIG_DIR = 'conf'
_LOG_DIR = 'log'
_PID_DIR = 'run'
_TEMP_DIR = 'temp'
_WEBAPP_PORT_OFFSET = 1
_CLI_PORT_OFFSET = 2
_RPC_PORT_OFFSET = 3
_RSYNC_PORT_OFFSET = 4
_HTTP_POST_PORT_OFFSET = 5
_INSTALOG_SOCKET_PORT_OFFSET = 6
_INSTALOG_HTTP_PORT_OFFSET = 7


def GetRsyncPortFromBasePort(base_port):
  return base_port + _RSYNC_PORT_OFFSET


# TODO(chuntsen): Remove instalog_socket_port.
def GetInstalogPortFromBasePort(base_port):
  return base_port + _INSTALOG_SOCKET_PORT_OFFSET


class UmpireEnv(object):
  """Provides accessors of Umpire resources.

  The base directory is obtained in constructor. If a user wants to run
  locally (e.g. --local is used), just modify self.base_dir to local
  directory and the accessors will reflect the change.

  Properties:
    base_dir: Umpire base directory
    config_path: Path of the Umpire Config file
    config: Active UmpireConfig object
    staging_config: Staging UmpireConfig object
  """
  # List of Umpire mandatory subdirectories.
  # Use tuple to avoid modifying.
  SUB_DIRS = ('bin', 'conf', 'dashboard', 'log', 'resources', 'run', 'temp',
              'toolkits', 'umpire_data', 'updates')

  def __init__(self, root_dir='/'):
    self.base_dir = os.path.join(root_dir, common.DEFAULT_BASE_DIR)
    self.server_toolkit_dir = os.path.join(root_dir, common.DEFAULT_SERVER_DIR)
    self.config_path = None
    self.config = None
    self.staging_config = None

  @property
  def device_toolkits_dir(self):
    return os.path.join(self.base_dir, _DEVICE_TOOLKITS_DIR)

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
  def temp_dir(self):
    return os.path.join(self.base_dir, _TEMP_DIR)

  @property
  def umpire_data_dir(self):
    return os.path.join(self.base_dir, _UMPIRE_DATA_DIR)

  @property
  def active_config_file(self):
    return os.path.join(self.base_dir, _ACTIVE_UMPIRE_CONFIG)

  @property
  def staging_config_file(self):
    return os.path.join(self.base_dir, _STAGING_UMPIRE_CONFIG)

  @property
  def umpire_ip(self):
    if not self.config:
      raise common.UmpireError('UmpireConfig not loaded yet.')
    return self.config.get('ip', '0.0.0.0')

  @property
  def umpire_base_port(self):
    if not self.config:
      raise common.UmpireError('UmpireConfig not loaded yet.')
    return self.config.get('port', common.UMPIRE_DEFAULT_PORT)

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
    return GetRsyncPortFromBasePort(self.umpire_base_port)

  @property
  def umpire_http_post_port(self):
    return self.umpire_base_port + _HTTP_POST_PORT_OFFSET

  # TODO(chuntsen): Remove instalog_socket_port.
  @property
  def umpire_instalog_socket_port(self):
    return GetInstalogPortFromBasePort(self.umpire_base_port)

  @property
  def umpire_instalog_http_port(self):
    return self.umpire_base_port + _INSTALOG_HTTP_PORT_OFFSET

  @property
  def shopfloor_service_url(self):

    def IsInsideDocker():
      with open('/proc/1/sched') as f:
        return f.readline().split()[0] != 'init'

    if not self.config:
      raise common.UmpireError('UmpireConfig not loaded yet.')
    url = self.config.get('shopfloor_service_url')
    if url is None:
      # When running inside Docker, we want to reach the service running outside
      # Docker so the host should be default router; otherwise host should be
      # localhost.
      host = 'localhost'
      try:
        if IsInsideDocker():
          # 'ip route' prints default routing in first line: 'default via <IP>'
          host = process_utils.CheckOutput([
              'ip', 'route']).splitlines()[0].split()[2]
      except Exception:
        logging.debug('Probably not inside Docker, bind to localhost.')

      url = 'http://%s:%s' % (host, common.DEFAULT_SHOPFLOOR_SERVICE_PORT)
    return url.rstrip('/')

  def ReadConfig(self, custom_path=None):
    """Reads Umpire config.

    It just returns config. It doesn't change config in property.

    Args:
      custom_path: If specified, load the config file custom_path pointing to.
          Default loads active config.

    Returns:
      UmpireConfig object.
    """
    config_path = custom_path or self.active_config_file
    return config.UmpireConfig(config_path)

  def LoadConfig(self, custom_path=None, validate=True):
    """Loads Umpire config file and validates it.

    Args:
      custom_path: If specified, load the config file custom_path pointing to.
      validate: True to validate resources in config.

    Raises:
      UmpireError if it fails to load the config file.
    """
    def _LoadValidateConfig(path):
      result = config.UmpireConfig(path)
      if validate:
        config.ValidateResources(result, self)
      return result

    # Load active config & update config_path.
    config_path = custom_path or self.active_config_file
    logging.debug('Load %sconfig: %s', 'active ' if not custom_path else '',
                  config_path)
    # Note that config won't be set if it fails to load/validate the new config.
    self.config = _LoadValidateConfig(config_path)
    self.config_path = config_path

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
      raise common.UmpireError(
          'Unable to stage a config file as another config is already staged. '
          'Check %r to decide if it should be deployed (use "umpire deploy"), '
          'edited again ("umpire edit") or discarded ("umpire unstage").' %
          self.staging_config_file)

    if config_path is None:
      config_path = self.active_config_file

    source = os.path.realpath(config_path)
    if not os.path.isfile(source):
      raise common.UmpireError(
          "Unable to stage config %s as it doesn't exist." % source)
    if force and self.HasStagingConfigFile():
      logging.info('Force staging, unstage existing one first.')
      self.UnstageConfigFile()
    logging.info('Stage config: ' + source)
    file_utils.SymlinkRelative(source, self.staging_config_file,
                               base=self.base_dir)

  def UnstageConfigFile(self):
    """Unstage the current staging config file.

    Returns:
      Real path of the staging file being unstaged.
    """
    if not self.HasStagingConfigFile():
      raise common.UmpireError(
          "Unable to unstage as there's no staging config file.")
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
      raise common.UmpireError(
          'Unable to activate missing config: ' + config_path)

    config_to_activate = os.path.realpath(config_path)
    if os.path.isfile(self.active_config_file):
      logging.info('Deactivate config: ' +
                   os.path.realpath(self.active_config_file))
      os.unlink(self.active_config_file)
    logging.info('Activate config: ' + config_to_activate)
    file_utils.SymlinkRelative(config_to_activate, self.active_config_file,
                               base=self.base_dir)

  def _AddResource(self, src_path, res_name, use_move):
    dst_path = os.path.join(self.resources_dir, res_name)
    if os.path.exists(dst_path):
      if filecmp.cmp(src_path, dst_path, shallow=False):
        logging.warning('Skip copying as file already exists: %s', dst_path)
        return
      raise common.UmpireError(
          'Hash collision: file %r != resource file %r' % (src_path, dst_path))
    if use_move:
      os.rename(src_path, dst_path)
    else:
      file_utils.AtomicCopy(src_path, dst_path)
    logging.info('Resource added: %s', dst_path)

  def AddPayload(self, file_path, type_name):
    """Adds a cros_payload component into <base_dir>/resources.

    Args:
      file_path: file to be added.
      type_name: An element of resource.PayloadTypeNames.

    Returns:
      The json dictionary generated by cros_payload.
    """
    with file_utils.TempDirectory(dir=self.temp_dir) as temp_dir:
      json_name = '.json'
      json_path = os.path.join(temp_dir, json_name)
      file_utils.WriteFile(json_path, '{}')
      process_utils.Spawn([CROS_PAYLOAD, 'add', json_name, type_name,
                           os.path.abspath(file_path)],
                          cwd=temp_dir, log=True, check_call=True,
                          env=dict(os.environ, TMPDIR=self.temp_dir))
      payloads = json.loads(file_utils.ReadFile(json_path))
      os.unlink(json_path)
      for filename in os.listdir(temp_dir):
        self._AddResource(os.path.join(temp_dir, filename), filename, True)

    # TODO(b/38512373): Remove this part.
    if type_name == resource.PayloadTypeNames.toolkit:
      resource.UnpackFactoryToolkit(
          self, file_path, resource.GetFilePayloadHash(payloads[type_name]))

    return payloads

  def AddConfig(self, file_path, type_name):
    """Adds a config file into <base_dir>/resources.

    Args:
      file_path: file to be added.
      type_name: An element of resource.ConfigTypeNames.

    Returns:
      Resource file name.
    """
    file_utils.CheckPath(file_path, 'source')
    res_name = resource.BuildConfigFileName(type_name, file_path)
    self._AddResource(file_path, res_name, False)
    return res_name

  def AddConfigFromBlob(self, blob, type_name):
    """Adds a config file into <base_dir>/resources.

    Args:
      blob: content of config file to be added.
      type_name: An element of resource.ConfigTypeNames.

    Returns:
      Resource file name.
    """
    with file_utils.UnopenedTemporaryFile() as file_path:
      file_utils.WriteFile(file_path, blob)
      return self.AddConfig(file_path, type_name)

  def GetPayloadsDict(self, payloads_name):
    """Gets a payload config.

    Args:
      payloads_name: filename of payload config in resources directory.

    Returns:
      A dictionary of specified cros_payload JSON config.
    """
    return json.loads(file_utils.ReadFile(self.GetResourcePath(payloads_name)))

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
    if check:
      file_utils.CheckPath(path, 'resource')
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
    try:
      bundle = self.config.GetBundle(bundle_id)
      payloads = self.GetPayloadsDict(bundle['payloads'])
      payload = payloads[resource.PayloadTypeNames.toolkit]
      toolkit_path = os.path.join(self.device_toolkits_dir,
                                  resource.GetFilePayloadHash(payload))
      assert os.path.isdir(toolkit_path)
      return toolkit_path
    except Exception:
      return None


class UmpireEnvForTest(UmpireEnv):
  """An UmpireEnv for other unittests.

  It creates a temp directory as its base directory and creates fundamental
  subdirectories (those which define property). The temp directory is removed
  once it is deleted.
  """

  def __init__(self):
    self.root_dir = tempfile.mkdtemp()
    super(UmpireEnvForTest, self).__init__(self.root_dir)
    os.makedirs(self.server_toolkit_dir)
    for fundamental_subdir in (
        self.config_dir,
        self.log_dir,
        self.pid_dir,
        self.resources_dir,
        self.temp_dir,
        self.umpire_data_dir):
      os.makedirs(fundamental_subdir)
    self.AddConfigFromBlob('{}', resource.ConfigTypeNames.payload_config)

  def Close(self):
    if os.path.isdir(self.root_dir):
      shutil.rmtree(self.root_dir)
