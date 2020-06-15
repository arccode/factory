# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Export a specific resource from a bundle

It reads active config, download the specific resource of a bundle,
and install it at the specified file_path.

See PayloadExporter comments for usage.
"""

import os

from cros.factory.umpire import common
from cros.factory.umpire.server import config as umpire_config
from cros.factory.umpire.server import umpire_env
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


class PayloadExporter:

  def __init__(self, env):
    """Constructor.

    Args:
      env: UmpireEnv object.
    """
    self._env = env

  def ExportPayload(self, bundle_id, payload_type, file_path):
    """Export a specific resource from a bundle

    It reads active config, download the specific resource of a bundle,
    and install it at the specified file_path.

    Args:
      bundle_id: The ID of the bundle.
      payload_type: Payload type of the resource.
      file_path: File path to export the specific resource.
    """
    config = umpire_config.UmpireConfig(self._env.config)
    bundle = config.GetBundle(bundle_id)
    if not bundle:
      raise common.UmpireError('bundle %r does not exist' % bundle_id)
    file_utils.TryMakeDirs(os.path.dirname(file_path))
    if os.path.isdir(file_path):
      raise common.UmpireError('<file_path> should not be a directory')

    json_url = self._env.GetResourcePath(bundle['payloads'])
    payloads = self._env.GetPayloadsDict(bundle['payloads'])
    # remove old resources
    file_utils.TryUnlink(file_path)

    if payload_type in payloads:
      try:
        cmd = [
            umpire_env.CROS_PAYLOAD,
            'install', json_url,
            file_path,
            payload_type
        ]
        process_utils.Spawn(cmd, check_call=True, log=True)
      except Exception:
        raise common.UmpireError('Failed to export %s' % payload_type)
    else:
      raise common.UmpireError('Payload not found: %s' % payload_type)
