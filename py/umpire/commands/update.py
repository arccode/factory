# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Updates a resource in a bundle.

See ResourceUpdater for detail.
"""

import copy
import os

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.common import (
    ResourceType, UmpireError, UPDATEABLE_RESOURCES)
from cros.factory.umpire import config as umpire_config
from cros.factory.umpire import utils as umpire_utils
from cros.factory.utils import file_utils


# Mapping of updateable resource type (command string) to ResourceType enum.
_RESOURCE_TYPE_MAP = {
    'factory_toolkit': ResourceType.FACTORY_TOOLKIT,
    'firmware': ResourceType.FIRMWARE,
    'fsi': ResourceType.ROOTFS_RELEASE,
    'hwid': ResourceType.HWID}


class ResourceUpdater(object):
  """Updates a resource in a bundle from active config.

  It copies the given resources to Umpire repository. Then updates the
  specified bundle's resource mapping. Finally, it adds the updated config
  to resources and marks it as staging.

  Usage:
    resource_updater = ResourceUpdater(env)
    ResourceUpdater.Update(resources_to_update, source_id='old_bundle_id',
                           dest_id='new_bundle_id')
  """
  def __init__(self, env):
    """Constructor.

    It copies active config (env.config) to be modified.
    It checks env.HasStagingConfigFile(). If True, raises exception.

    Args:
      env: UmpireEnv object.

    Raises:
      UmpireError if staging config exists.
    """
    if env.HasStagingConfigFile():
      raise UmpireError(
          'Cannot update resources as staging config exists. '
          'Please run "umpire unstage" to unstage or "umpire deploy" to '
          'deploy the staging config first.')

    self._env = env

    # Copy current config for editing.
    self._config = umpire_config.UmpireConfig(env.config)

    self._config_basename = os.path.basename(env.config_path)
    self._target_bundle = None

  def Update(self, resources_to_update, source_id=None, dest_id=None):
    """Updates resource(s) in a bundle.

    Args:
      resources_to_update: list of (resource_type, resource_path) to update.
      source_id: source bundle's ID. If omitted, uses default bundle.
      dest_id: If specified, it copies source bundle with ID dest_id and
          replaces the specified resource(s). Otherwise, it replaces
          resource(s) in place.

    Returns:
      Path to updated config file in resources.
    """
    if not source_id:
      source_id = self._config.GetDefaultBundle()['id']

    self._SanityCheck(resources_to_update)
    self._PrepareTargetBundle(source_id, dest_id)
    self._UpdateResourceMap(resources_to_update)
    return self._WriteToStagingConfig()

  def _PrepareTargetBundle(self, source_id,  dest_id):
    target_bundle = self._config.GetBundle(source_id)
    if not target_bundle:
      raise UmpireError('Source bundle ID does not exist: ' + source_id)

    if dest_id:
      if self._config.GetBundle(dest_id):
        raise UmpireError('Destination bundle ID already exists: ' + dest_id)
      target_bundle = copy.deepcopy(target_bundle)
      target_bundle['id'] = dest_id
      self._config['bundles'].insert(0, target_bundle)

    self._target_bundle = target_bundle

  def _SanityCheck(self, resources):
    for resource_type, resource_path in resources:
      if resource_type not in UPDATEABLE_RESOURCES:
        raise UmpireError('Unsupported resource type: ' + resource_type)
      if not os.path.isfile(resource_path):
        raise UmpireError('Resource not found: ' + resource_path)

  def _UpdateResourceMap(self, resources):
    resource_map = self._target_bundle['resources']
    for resource_type, resource_path in resources:
      resource_name = os.path.basename(
          self._env.AddResource(resource_path,
                                res_type=_RESOURCE_TYPE_MAP.get(resource_type)))
      if resource_type == 'factory_toolkit':
        resource_map['device_factory_toolkit'] = resource_name
        resource_map['server_factory_toolkit'] = resource_name
        umpire_utils.UnpackFactoryToolkit(self._env, resource_name)

      elif resource_type == 'fsi':
        resource_map['rootfs_release'] = resource_name
      else:
        resource_map[resource_type] = resource_name

  def _WriteToStagingConfig(self):
    """Writes self._config to resources and set it as staging.

    Returns:
      config path in resources.
    """
    with file_utils.TempDirectory() as temp_dir:
      temp_config_path = os.path.join(temp_dir, self._config_basename)
      self._config.WriteFile(temp_config_path)
      res_path = self._env.AddResource(temp_config_path)
      self._env.StageConfigFile(res_path)
      return res_path
