# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Updates a resource in a bundle.

See ResourceUpdater for detail.
"""

import copy
import json
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import common
from cros.factory.umpire.server import config as umpire_config
from cros.factory.umpire.server import resource


class ResourceUpdater(object):
  """Updates a resource in a bundle from active config.

  It copies the given resources to Umpire repository. Then updates the
  specified bundle's resource mapping. Finally, it adds the updated config
  to resources and marks it as staging.

  Usage:
    resource_updater = ResourceUpdater(env)
    resource_updater.Update(resources_to_update, source_id='old_bundle_id',
                            dest_id='new_bundle_id')
  """

  def __init__(self, env):
    """Constructor.

    Args:
      env: UmpireEnv object.
    """
    self._env = env

  def Update(self, payloads_to_update, source_id=None, dest_id=None):
    """Updates payload(s) in a bundle.

    Args:
      payloads_to_update: list of (type_name, file_path) to update.
      source_id: source bundle's ID. If omitted, uses default bundle.
      dest_id: If specified, it copies source bundle with ID dest_id and
          replaces the specified resource(s). Otherwise, it replaces
          resource(s) in place.
    """
    if self._env.HasStagingConfigFile():
      raise common.UmpireError(
          'Cannot update resources as staging config exists. '
          'Please run "umpire unstage" to unstage or "umpire deploy" to '
          'deploy the staging config first.')

    for type_name, file_path in payloads_to_update:
      if type_name not in resource.PayloadTypeNames:
        raise common.UmpireError('Unsupported payload type: %s' % type_name)
      if not os.path.isfile(file_path):
        raise common.UmpireError('File not found: %s' % file_path)

    config = umpire_config.UmpireConfig(self._env.config)
    if not source_id:
      source_id = config.GetDefaultBundle()['id']
    bundle = config.GetBundle(source_id)
    if not bundle:
      raise common.UmpireError(
          'Source bundle ID does not exist: %s' % source_id)
    if dest_id:
      if config.GetBundle(dest_id):
        raise common.UmpireError(
            'Destination bundle ID already exists: %s' % dest_id)
      bundle = copy.deepcopy(bundle)
      bundle['id'] = dest_id
      config.bundles.append(bundle)

    payloads = self._env.GetPayloadsDict(bundle['payloads'])
    for type_name, path in payloads_to_update:
      payloads.update(self._env.AddPayload(path, type_name))
    bundle['payloads'] = self._env.AddConfigFromBlob(
        json.dumps(payloads), resource.ConfigTypeNames.payload_config)
    self._env.StageConfigFile(self._env.GetResourcePath(
        self._env.AddConfigFromBlob(config.Dump(),
                                    resource.ConfigTypeNames.umpire_config)))
