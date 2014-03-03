# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Updates a resource in a bundle.

See ResourceUpdater for detail.
"""

import copy
import os

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.common import UmpireError, UPDATEABLE_RESOURCES


class ResourceUpdater(object):
  """Updates a resource in a bundle.

  It copies the given resources to Umpire repository and updates the specified
  bundle's resource mapping.

  Usage:
    resource_updater = ResourceUpdater(env)
    resources_to_update = ResourceUpdater.ParseResourceStr(resource_str)
    ResourceUpdater.Update(resources_to_update, source_id='old_bundle_id',
                           dest_id='new_bundle_id')
  """
  def __init__(self, env):
    """Constructor.

    Args:
      env: UmpireEnv object.
    """
    self._env = env
    self._config = self._env.config
    self._target_bundle = None

  def Update(self, resources_to_update, source_id=None, dest_id=None):
    """Updates resource(s) in a bundle.

    Args:
      resources_to_update: list of (resource_type, resource_path) to update.
      source_id: source bundle's ID. If omitted, uses default bundle.
      dest_id: If specified, it copies source bundle with ID dest_id and
          replaces the specified resource(s). Otherwise, it replaces
          resource(s) in place.
    """
    if not source_id:
      source_id = self._config.GetDefaultBundle()['id']

    self._SanityCheck(resources_to_update)
    self._PrepareTargetBundle(source_id, dest_id)
    self._UpdateResourceMap(resources_to_update)

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
      resource_name = os.path.basename(self._env.AddResource(resource_path))
      if resource_type == 'factory_toolkit':
        resource_map['device_factory_toolkit'] = resource_name
        resource_map['server_factory_toolkit'] = resource_name
      elif resource_type == 'fsi':
        resource_map['rootfs_release'] = resource_name
      else:
        resource_map[resource_type] = resource_name
