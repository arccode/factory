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
import urlparse

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import common
from cros.factory.umpire.server import config
from cros.factory.umpire.server import resource
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils
from cros.factory.utils import webservice_utils


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

PROJECT_NAME_ENV_KEY = 'UMPIRE_PROJECT_NAME'


def GetRsyncPortFromBasePort(base_port):
  return base_port + _RSYNC_PORT_OFFSET

class Parameter(object):
  """Provides operation on parameter objects.

  Properties:
    data: including files and dirs.
    files: parmeter component files.
    dirs: parameter directory.
  """
  def __init__(self, data):
    self.data = data

  @property
  def files(self):
    return self.data['files']

  @property
  def dirs(self):
    return self.data['dirs']

  def _FindComponentsByName(self, dir_id, name):
    """Return List of component(s) in given directory and component name.

    If name is None, return all components in this directory.
    """
    fs = [f for f in self.files if f['dir_id'] == dir_id]
    if name is not None:
      fs = [f for f in fs if f['name'] == name]
    return fs

  def _FindChildDirByName(self, parent_id, dir_name):
    """Return directory in given parent directory and directory name."""
    return next((d for d in self.dirs
                 if d['name'] == dir_name and d['parent_id'] == parent_id),
                None)

  def _FindComponentById(self, comp_id):
    """Return component with given id."""
    return next((c for c in self.files if c['id'] == comp_id), None)

  def _UpdateExistingComponent(self, component, using_ver, dst_path):
    """Update existing component, including revision and update new version."""
    if dst_path:
      # update component to new version
      if using_ver is not None:
        raise common.UmpireError(
            'Intend to update version and use old version at the same time.')
      version_count = len(component['revisions'])
      component['revisions'].append(dst_path)
      component['using_ver'] = version_count
    elif using_ver is not None:
      # rollback component to existed version
      if not 0 <= using_ver < len(component['revisions']):
        raise common.UmpireError(
            'Intend to use invalid version of parameter %d.' % component['id'])
      component['using_ver'] = using_ver
    else:
      raise common.UmpireError('Unknown operation.')
    # TODO(hsinyi): add rename component
    return component

  def _CreateComponent(self, dir_id, comp_name, dst_path):
    """Create new component."""
    comp_id = len(self.files)
    component = {
        'id': comp_id,
        'dir_id': dir_id,
        'name': comp_name,
        'using_ver': 0,
        'revisions': [dst_path]
    }
    self.files.append(component)
    return component

  def UpdateComponent(self, comp_id, dir_id, comp_name, using_ver, dst_path):
    """See UmpireEnv.UpdateParameterComponent for detail"""
    if comp_id is not None:
      component = self._FindComponentById(comp_id)
      return self._UpdateExistingComponent(component, using_ver, dst_path)
    else:
      # check if same name component already existed in same dir
      existed_comp = self._FindComponentsByName(dir_id, comp_name)
      if existed_comp:
        # create file but name existed in same dir, view as updating version
        return self._UpdateExistingComponent(existed_comp[0], using_ver,
                                             dst_path)
      else:
        if using_ver is not None:
          raise common.UmpireError(
              'Intend to create component but assigned using_ver.')
        return self._CreateComponent(dir_id, comp_name, dst_path)

  def CreateDirectory(self, parent_id, name):
    """See UmpireEnv.CreateParameterDirectory for detail."""
    existed_dir = self._FindChildDirByName(parent_id, name)
    if existed_dir is not None:
      # create dir but name existed in parent dir, directly return
      return existed_dir

    dir_id = len(self.dirs)
    new_dir = {
        'id': dir_id,
        'parent_id': parent_id,
        'name': name
    }
    self.dirs.append(new_dir)
    # TODO(hsinyi): add rename directory
    return new_dir

  def _GetDirIdByNameSpace(self, namespace):
    """Retrieve directory by given namespace."""
    if namespace is None:
      return None
    namespace = namespace.split('/')
    current_id = None
    for name in namespace:
      next_dir = self._FindChildDirByName(current_id, name)
      if next_dir is None:
        raise common.UmpireError('Directory namespace not exists.')
      current_id = next_dir['id']
    return current_id

  def GetComponentsAbsPath(self, namespace, name):
    """See UmpireEnv.QueryParameters for detail."""
    try:
      dir_id = self._GetDirIdByNameSpace(namespace)
    except common.UmpireError:
      logging.error('Intend to request non-existent namespace.')
      return []
    fs = self._FindComponentsByName(dir_id, name)
    return [(f['name'], f['revisions'][f['using_ver']]) for f in fs]


class UmpireEnv(object):
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
    self._parameter = None

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
  def parameter(self):
    if self._parameter is None:
      self._parameter = Parameter(json_utils.LoadFile(self.parameter_json_file))
    return self._parameter

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
      parsed_url = urlparse.urlparse(real_url)
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

  def _AddFile(self, src_path, dst_path, use_move):
    """Check if destination file exists and add file.

    Args:
      src_path: source file path.
      dst_path: destination file path.
      use_move: use os.rename() or file_utils.AtomicCopy().

    Raise:
      UmpireError if dst_path exists but has different content from src_path.
    """
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
    os.chmod(dst_path, 0o644)
    logging.info('File added: %s', dst_path)

  def _AddResource(self, src_path, res_name, use_move):
    dst_path = os.path.join(self.resources_dir, res_name)
    self._AddFile(src_path, dst_path, use_move)

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

  def _DumpParameter(self):
    """Dump parameter to json file."""
    json_utils.DumpFile(self.parameter_json_file, self.parameter.data)

  def GetParameterDstPath(self, src_path):
    """Prepend file MD5 sum to file path"""
    original_filename = os.path.basename(src_path)
    md5sum = file_utils.MD5InHex(src_path)
    new_filemame = '.'.join([original_filename, md5sum])
    return os.path.join(self.parameters_dir, new_filemame)

  def AddParameter(self, src_path):
    dst_path = self.GetParameterDstPath(src_path)
    self._AddFile(src_path, dst_path, False)
    return dst_path

  def UpdateParameterComponent(self, comp_id, dir_id, comp_name, using_ver,
                               src_path):
    """Update a parameter component file.

    Support following types of actions:
      1) Create new component.
      2) Rollback component to existed version.
      3) Update component to new version.

    Args:
      comp_id: component id. None if intend to create a new component.
      dir_id: directory id where the component will be created.
              None if component is at root directory.
      comp_name: component name.
      using_ver: file version component will use.
      src_path: uploaded file path.

    Returns:
      Updated component dictionary.
    """
    dst_path = self.AddParameter(src_path) if src_path else None
    component = self.parameter.UpdateComponent(comp_id, dir_id, comp_name,
                                               using_ver, dst_path)
    self._DumpParameter()
    return component

  def GetParameterInfo(self):
    """Dump parameter info.

    Returns:
      Parameter dictionary, which contains component files and directories.
      {
        "files": FileComponent[],
        "dirs": Directory[]
      }
      FileComponent = {
        "id": number, // index
        "dir_id": number | null, // directory index
        "name": string, // component name
        "using_ver": number, // version to use, range: [0, len(revisions))
        "revisions": string[], // file paths
      }
      Directory = {
        "id": number, // index
        "parent_id": number | null, // parent directory index
        "name": string, // directory name
      }
    """
    return self.parameter.data

  def CreateParameterDirectory(self, parent_id, name):
    """Create a parameter directory.

    Args:
      parent_id: parent directory id where the dir will be created.
                 None if parent is root directory.
      name: dir name.

    Returns:
      Created directory dictionary and its index.
    """
    directory = self.parameter.CreateDirectory(parent_id, name)
    self._DumpParameter()
    return directory

  def QueryParameters(self, namespace, name):
    """Gets file path of queried component(s).

    Args:
      namespace: relative directory path(separate by '/') of queried
                 component(s). None if they are in root directory.
      name: component name of queried component. None if queries all components
            under namespace.

    Returns:
      List of tuple(component name, file path)
    """
    return self.parameter.GetComponentsAbsPath(namespace, name)


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
