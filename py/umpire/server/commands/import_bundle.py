# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Imports a bundle.

It reads a factory bundle, copies resources to Umpire repository, and
updates UmpireConfig.

See BundleImporter comments for usage.
"""

import glob
import json
import os
import time

from cros.factory.umpire import common
from cros.factory.umpire.server.commands import deploy
from cros.factory.umpire.server import config as umpire_config
from cros.factory.umpire.server import resource
from cros.factory.utils import file_utils


class BundleImporter:
  """Imports a bundle.

  It reads a factory bundle and copies resources to Umpire.

  It also try to update active UmpireConfig and deploy it.

  Usage:
    BundleImporter(daemon).Import('/path/to/bundle', 'bundle_id')
  """

  def __init__(self, daemon):
    """Constructor.

    Args:
      daemon: UmpireDaemon object.
    """
    self._daemon = daemon

  def Import(self, bundle_path, bundle_id=None, note=None):
    """Imports a bundle.

    Args:
      bundle_path: A bundle's path (could be a directory or a zip file).
      bundle_id: The ID of the bundle. If omitted, use timestamp.
      note: A description of this bundle.
    """
    if not bundle_id:
      bundle_id = time.strftime('factory_bundle_%Y%m%d_%H%M%S')
    if note is None:
      note = ''

    config = umpire_config.UmpireConfig(self._daemon.env.config)
    if config.GetBundle(bundle_id):
      raise common.UmpireError('bundle_id %r already in use' % bundle_id)

    file_utils.CheckPath(bundle_path, 'bundle')
    if not os.path.isdir(bundle_path):
      with file_utils.TempDirectory() as temp_dir:
        file_utils.ExtractFile(bundle_path, temp_dir, use_parallel=True)
        self.Import(temp_dir, bundle_id=bundle_id, note=note)
        return

    import_list = BundleImporter._GetImportList(bundle_path)
    payloads = {}
    for path, type_name in import_list:
      payloads.update(self._daemon.env.AddPayload(path, type_name))
    payload_json_name = self._daemon.env.AddConfigFromBlob(
        json.dumps(payloads), resource.ConfigTypeNames.payload_config)

    config['bundles'].insert(0, {
        'id': bundle_id,
        'note': note,
        'payloads': payload_json_name
    })
    config['active_bundle_id'] = bundle_id
    deploy.ConfigDeployer(self._daemon).Deploy(
        self._daemon.env.AddConfigFromBlob(
            config.Dump(), resource.ConfigTypeNames.umpire_config))

  @classmethod
  def _GetImportList(cls, bundle_path):
    ret = []
    for type_name in resource.PayloadTypeNames:
      target = resource.GetPayloadType(type_name).import_pattern
      candidates = glob.glob(os.path.join(bundle_path, target))
      if len(candidates) > 1:
        raise common.UmpireError(
            'Multiple %s found: %r' % (type_name, candidates))
      if len(candidates) == 1:
        ret.append((candidates[0], type_name))
    return ret
