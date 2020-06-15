# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Updates a resource in a bundle.

See ResourceUpdater for detail.
"""

import copy
import json
import os

from cros.factory.umpire import common
from cros.factory.umpire.server.commands import deploy
from cros.factory.umpire.server import config as umpire_config
from cros.factory.umpire.server import resource


class ResourceUpdater:
  """Updates a resource in a bundle from active config.

  It copies the given resources to Umpire repository. Then updates the
  specified bundle's resource mapping. Finally, it adds the updated config
  to resources and deploys it.

  Usage:
    resource_updater = ResourceUpdater(daemon)
    resource_updater.Update(resources_to_update, source_id='old_bundle_id',
                            dest_id='new_bundle_id')
  """

  def __init__(self, daemon):
    """Constructor.

    Args:
      daemon: UmpireDaemon object.
    """
    self._daemon = daemon

  def Update(self, payloads_to_update, source_id=None, dest_id=None):
    """Updates payload(s) in a bundle.

    Args:
      payloads_to_update: list of (type_name, file_path) to update.
      source_id: source bundle's ID. If omitted, uses default bundle.
      dest_id: If specified, it copies source bundle with ID dest_id and
          replaces the specified resource(s). Otherwise, it replaces
          resource(s) in place.
    """
    for type_name, file_path in payloads_to_update:
      if type_name not in resource.PayloadTypeNames:
        raise common.UmpireError('Unsupported payload type: %s' % type_name)
      if not os.path.isfile(file_path):
        raise common.UmpireError('File not found: %s' % file_path)

    config = umpire_config.UmpireConfig(self._daemon.env.config)
    if not source_id:
      source_id = config.GetActiveBundle()['id']
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
      config['bundles'].append(bundle)

    payloads = self._daemon.env.GetPayloadsDict(bundle['payloads'])
    for type_name, path in payloads_to_update:
      payloads.update(self._daemon.env.AddPayload(path, type_name))
    bundle['payloads'] = self._daemon.env.AddConfigFromBlob(
        json.dumps(payloads), resource.ConfigTypeNames.payload_config)
    deploy.ConfigDeployer(self._daemon).Deploy(
        self._daemon.env.AddConfigFromBlob(
            config.Dump(), resource.ConfigTypeNames.umpire_config))
