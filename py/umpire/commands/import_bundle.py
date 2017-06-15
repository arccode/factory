# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Imports a bundle.

It reads a factory bundle, copies resources to Umpire repository, and
updates UmpireConfig.

See BundleImporter comments for usage.
"""

import json
import os
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import common
from cros.factory.umpire import config as umpire_config
from cros.factory.umpire import resource
from cros.factory.utils import file_utils


class BundleImporter(object):
  """Imports a bundle.

  It reads a factory bundle and copies resources to Umpire.

  It also updates active UmpireConfig and saves it to staging. Note that if
  staging config already exists, it refuses to import the bundle.

  Usage:
    BundleImporter(env).Import('/path/to/bundle', 'bundle_id')
  """

  def __init__(self, env):
    """Constructor.

    Args:
      env: UmpireEnv object.
    """
    self._env = env

  def Import(self, bundle_path, bundle_id=None, note=None):
    """Imports a bundle.

    Args:
      bundle_path: A bundle's path (could be a directory or a zip file).
      bundle_id: The ID of the bundle. If omitted, use timestamp.
      note: A description of this bundle. If omitted, use bundle_id.

    Returns:
      Updated staging config path.
    """
    if self._env.HasStagingConfigFile():
      raise common.UmpireError(
          'Cannot import bundle as staging config exists. '
          'Please run "umpire unstage" to unstage or "umpire deploy" to '
          'deploy the staging config first.')

    if not bundle_id:
      bundle_id = time.strftime('factory_bundle_%Y%m%d_%H%M%S')
    if not note:
      note = 'n/a'

    config = umpire_config.UmpireConfig(self._env.config)
    if config.GetBundle(bundle_id):
      raise common.UmpireError('bundle_id %r already in use' % bundle_id)

    file_utils.CheckPath(bundle_path, 'bundle')
    if not os.path.isdir(bundle_path):
      with file_utils.TempDirectory() as temp_dir:
        file_utils.ExtractFile(bundle_path, temp_dir, use_parallel=True)
        return self.Import(temp_dir, bundle_id=bundle_id, note=note)

    import_list = BundleImporter._GetImportList(bundle_path)
    payloads = {}
    for path, type_name in import_list:
      payloads.update(self._env.AddPayload(path, type_name))
    payload_json_name = self._env.AddConfigFromBlob(
        json.dumps(payloads), resource.ConfigTypeNames.payload_config)

    config['bundles'].append({
        'id': bundle_id,
        'note': note,
        'payloads': payload_json_name,
        })
    config['rulesets'].insert(0, {
        'bundle_id': bundle_id,
        'note': 'Please update match rule in ruleset',
        'active': False,
        })
    cfg_path = self._env.GetResourcePath(
        self._env.AddConfigFromBlob(config.Dump(),
                                    resource.ConfigTypeNames.umpire_config))
    self._env.StageConfigFile(cfg_path)
    return cfg_path

  @classmethod
  def _GetImportList(cls, bundle_path):
    ret = []
    for type_name in resource.PayloadTypeNames:
      candidates = os.listdir(os.path.join(bundle_path, type_name))
      if not candidates:
        continue
      if len(candidates) > 1:
        raise common.UmpireError(
            'Multiple %s found: %r' % (type_name, candidates))
      ret.append((os.path.join(bundle_path, type_name, candidates[0]),
                  type_name))
    return ret
