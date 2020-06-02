# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Multicast service for umpire resources."""

import os

from cros.factory.umpire.server.service import umpire_service
from cros.factory.utils import json_utils


FACTORY_ENV = '/usr/local/factory/bin/factory_env'

MCAST_DEFAULT_ADDRESS = '224.1.1.1'
_REQUIRED_IMAGE_PARTS = [
    'test_image.part1',
    'test_image.part3',
    'test_image.part4',
    'release_image.part3',
    'release_image.part4',
    'release_image.part6',
    'release_image.part7',
    'release_image.part8',
    'release_image.part9',
    'release_image.part10',
    'release_image.part11',
    'release_image.part12',
]


class MulticastService(umpire_service.UmpireService):
  """Multicast service."""

  def CreateProcesses(self, umpire_config, env):
    """Creates list of processes via config.

    Args:
      umpire_config: Umpire config dict.
      env: UmpireEnv object.

    Returns:
      A list of ServiceProcess.
    """

    mcast_service_config = umpire_config['services']['multicast']

    if 'mgroup' in mcast_service_config:
      mgroup = mcast_service_config['mgroup']
    else:
      mgroup = MCAST_DEFAULT_ADDRESS
    port = int(env.umpire_multicast_begin_port)

    required_components = mcast_service_config['required_components']

    # Read all available components from the payload config file and assign a
    # port for each required component for multicasting.
    mcast_addrs = {}
    bundle = env.config.GetActiveBundle()
    payloads = env.GetPayloadsDict(bundle['payloads'])
    for component in payloads:
      if not required_components.get(component, False):
        continue

      mcast_addrs[component] = {}
      for part in payloads[component]:
        if part == 'version':
          continue

        if 'image' in component:
          image_part = component + '.%s' % (part)
          if image_part not in _REQUIRED_IMAGE_PARTS:
            continue

        mcast_addrs[component][part] = '%s:%s' % (mgroup, port)
        port += 1

    # Add multicast config into umpire env.
    mcast_config = payloads
    mcast_config['multicast'] = mcast_addrs
    env.config['multicast'] = env.AddConfigFromBlob(
        json_utils.DumpStr(mcast_config, pretty=True), 'multicast_config')

    server_file_path = os.path.join(
        env.server_toolkit_dir, 'py', 'multicast', 'server.py')

    args = [
        server_file_path,
        '--payload-file', env.GetResourcePath(env.config['multicast'])
        ]

    proc_config = {
        'executable': FACTORY_ENV,
        'name': 'multicast',
        'args': args,
        'path': '/tmp'}
    proc = umpire_service.ServiceProcess(self)
    proc.SetConfig(proc_config)
    return [proc]
