# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common Umpire classes.

This module provides constants and common Umpire classes.
"""

import json
import logging
import os
import re
import shutil
import tempfile
import urllib.parse

from cros.factory.umpire import common
from cros.factory.umpire.server.commands import parameters
from cros.factory.umpire.server import config
from cros.factory.umpire.server import resource
from cros.factory.umpire.server import utils
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils
from cros.factory.utils import webservice_utils
from cros.factory.utils import json_utils


CROS_PAYLOAD = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    '..', '..', '..', 'bin', 'cros_payload')

# Default Umpire base directory relative to root dir.
DEFAULT_BASE_DIR = os.path.join('var', 'db', 'factory', 'umpire')
DEFAULT_SERVER_DIR = os.path.join('usr', 'local', 'factory')

SESSION_JSON_FILE = 'session.json'
PARAMETER_JSON_FILE = 'parameters.json'

# File name under base_dir
_ACTIVE_UMPIRE_CONFIG = 'active_umpire.json'
_UMPIRE_DATA_DIR = 'umpire_data'
_RESOURCES_DIR = 'resources'
_PARAMETERS_DIR = 'parameters'
_CONFIG_DIR = 'conf'
_LOG_DIR = 'log'
_PID_DIR = 'run'
_TEMP_DIR = 'temp'
_WEBAPP_PORT_OFFSET = 1
_CLI_PORT_OFFSET = 2
_RPC_PORT_OFFSET = 3
_RSYNC_PORT_OFFSET = 4
_HTTP_POST_PORT_OFFSET = 5
_INSTALOG_PULL_SOCKET_OFFSET = 6
_INSTALOG_HTTP_PORT_OFFSET = 7
_INSTALOG_CUSTOMIZED_OUTPUT_OFFSET = 8

PROJECT_NAME_ENV_KEY = 'UMPIRE_PROJECT_NAME'
PROJECT_PORT_ENV_KEY = 'UMPIRE_PROJECT_PORT'


def GetRsyncPortFromBasePort(base_port):
  return base_port + _RSYNC_PORT_OFFSET


class UmpireEnv:
  """Provides accessors of Umpire resources.

  The base directory is obtained in constructor.
  If self.base_dir is modified, the accessors will reflect the change.

  Properties:
    base_dir: Umpire base directory
    config_path: Path of the Umpire Config file
    config: Active UmpireConfig object
  """

  def __init__(self, root_dir='/'):
    self.base_dir = os.path.join(root_dir, DEFAULT_BASE_DIR)
    self.server_toolkit_dir = os.path.join(root_dir, DEFAULT_SERVER_DIR)
    self.config_path = None
    self.config = None


  @property
  def resources_dir(self):
    return os.path.join(self.base_dir, _RESOURCES_DIR)

  @property
  def parameters_dir(self):
    return os.path.join(self.base_dir, _PARAMETERS_DIR)

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
  def parameter_json_file(self):
    return os.path.join(self.parameters_dir, PARAMETER_JSON_FILE)

  @property
  def umpire_base_port(self):
    return common.UMPIRE_DEFAULT_PORT

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

  @property
  def umpire_instalog_http_port(self):
    return self.umpire_base_port + _INSTALOG_HTTP_PORT_OFFSET

  @property
  def umpire_instalog_pull_socket_port(self):
    return self.umpire_base_port + _INSTALOG_PULL_SOCKET_OFFSET

  @property
  def umpire_instalog_customized_output_port(self):
    return self.umpire_base_port + _INSTALOG_CUSTOMIZED_OUTPUT_OFFSET

  @property
  def umpire_multicast_begin_port(self):
    return self.umpire_host_port

  @type_utils.LazyProperty
  def docker_host_ip(self):
    try:
      if sys_utils.IsContainerized():
        # Docker host should be the default router.
        # 'ip route' prints default routing in first line: 'default via <IP>'
        return process_utils.CheckOutput(['ip', 'route']).split()[2]
    except Exception:
      logging.debug('Failed to get default router.')
    return net_utils.LOCALHOST

  @property
  def shopfloor_service_url(self):
    if not self.config:
      raise common.UmpireError('UmpireConfig not loaded yet.')

    # Use default URL if config is empty string or None.
    key = 'services.shop_floor.service_url'
    url = type_utils.GetDict(
        self.config, key,
        'http://localhost:%s/' % common.DEFAULT_SHOPFLOOR_SERVICE_PORT)

    # The webservice_utils.py module allows having a 'protocol prefix' in URL
    # string so we have to preserve that first.
    unused_prefixes, real_url = webservice_utils.ParseURL(url)
    try:
      parsed_url = urllib.parse.urlparse(real_url)
      if parsed_url.hostname == 'localhost':
        # We translate 'localhost' to Docker host when running inside Docker.
        # The prefixes should not contain 'localhost'.
        url = url.replace('localhost', self.docker_host_ip, 1)
    except Exception:
      logging.error('Failed to parse %s: %r.', key, url)
    return url.rstrip('/')

  @property
  def project(self):
    return os.environ.get(PROJECT_NAME_ENV_KEY)

  @property
  def umpire_host_port(self):
    return int(os.environ.get(PROJECT_PORT_ENV_KEY))

  @type_utils.LazyProperty
  def parameters(self):
    return parameters.Parameters(self)

  def LoadConfig(self, custom_path=None, validate=True):
    """Loads Umpire config file and validates it.

    Args:
      custom_path: If specified, load the config file custom_path pointing to.
      validate: True to validate resources in config.

    Raises:
      UmpireError if it fails to load the config file.
    """
    # Load active config & update config_path.
    config_path = custom_path or self.active_config_file
    logging.debug('Load %s config: %s',
                  'custom' if custom_path else 'active', config_path)
    # Note that config won't be set if it fails to load/validate the new config.
    loaded_config = config.UmpireConfig(file_path=config_path)
    if validate:
      config.ValidateResources(loaded_config, self)
    self.config = loaded_config
    self.config_path = config_path

  def ActivateConfigFile(self, config_path):
    """Activates a config file.

    Args:
      config_path: a config file to mark as active.
    """
    if not os.path.isfile(config_path):
      raise common.UmpireError(
          'Unable to activate missing config: ' + config_path)

    config_to_activate = os.path.realpath(config_path)
    logging.info(
        'Deactivate config: %s', os.path.realpath(self.active_config_file))
    os.unlink(self.active_config_file)
    logging.info('Activate config: %s', config_to_activate)
    file_utils.SymlinkRelative(config_to_activate, self.active_config_file,
                               base=self.base_dir)

  def _AddResource(self, src_path, res_name, use_move):
    dst_path = os.path.join(self.resources_dir, res_name)
    utils.CheckAndMoveFile(src_path, dst_path, use_move)

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

      # All Umpire payloads must have version.
      if 'version' not in payloads[type_name]:
        raise common.UmpireError(
            'Cannot identify version information from <%s> payload.' %
            type_name)

      for filename in os.listdir(temp_dir):
        self._AddResource(os.path.join(temp_dir, filename), filename, True)

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

  def GetPayloadFiles(self, payloads_name):
    """Gets files in a payload config.

    Args:
      payloads_name: filename of payload config in resources directory.

    Returns:
      A set of tuples of (resource type, part, file name).
    """
    files = set()
    payloads = self.GetPayloadsDict(payloads_name)
    for type_name, payload_dict in payloads.items():
      for part, res_name in payload_dict.items():
        if part == 'file' or re.match(r'part\d+$', part) or part == 'crx_cache':
          files.add((type_name, part, res_name))
    return files

  def GetActivePayload(self, active_config_file):
    """Get active payloads information.

    Args:
      active_config_file: file path of active config.

    Returns:
      Active payloads information.
      If cannot find the active config, return None.
    """
    active_config = json_utils.LoadFile(active_config_file)
    active_bundle_id = active_config['active_bundle_id']
    bundles = active_config['bundles']
    for bundle in bundles:
      if active_bundle_id == bundle['id']:
        return json_utils.LoadFile(self.GetResourcePath(bundle['payloads']))
    logging.error('Failed to get active bundle\'s payload')
    return None

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

  def ResourceGarbageCollection(self):
    """Remove inactive resources.

    Remove resource files that are not used by any bundles in active config.
    """
    active_files = set()

    for bundle in self.config['bundles']:
      for unused_type, unused_part, res_name in self.GetPayloadFiles(
          bundle['payloads']):
        active_files.add(res_name)

    deleted_files = []
    deleted_size = 0
    for f in os.listdir(self.resources_dir):
      if not resource.IsConfigFileName(f) and f not in active_files:
        deleted_files.append(f)
        f_path = os.path.join(self.resources_dir, f)
        deleted_size += os.path.getsize(f_path)
        os.unlink(f_path)
    # XML-RPC does not support 64-bits integer so we need to convert
    # deleted_size to string.
    return {
        'files': deleted_files,
        'size': str(deleted_size)
    }


class UmpireEnvForTest(UmpireEnv):
  """An UmpireEnv for other unittests.

  It creates a temp directory as its base directory and creates fundamental
  subdirectories (those which define property). The temp directory is removed
  once it is deleted.

  Also, it overrides umpire_base_port to make it able to return a given port to
  avoid port conflicts during running unittests.
  """

  def __init__(self, port=None):
    self._port = port
    self.root_dir = tempfile.mkdtemp()
    super(UmpireEnvForTest, self).__init__(self.root_dir)
    os.makedirs(self.server_toolkit_dir)
    for fundamental_subdir in (
        self.config_dir,
        self.log_dir,
        self.pid_dir,
        self.resources_dir,
        self.temp_dir,
        self.parameters_dir,
        self.umpire_data_dir):
      os.makedirs(fundamental_subdir)
    self.AddConfigFromBlob('{}', resource.ConfigTypeNames.payload_config)

  @property
  def umpire_base_port(self):
    return self._port or super(UmpireEnvForTest, self).umpire_base_port

  def Close(self):
    shutil.rmtree(self.root_dir, ignore_errors=True)
