# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Multicast service for umpire resources."""

import os
import re

from cros.factory.umpire.server.service import umpire_service
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils


FACTORY_ENV = '/usr/local/factory/bin/factory_env'

MCAST_CONFIG_NAME = 'multicast_config.json'
DEFAULT_MGROUP = '224.3.1.1'
DEFAULT_MGROUP_PREFIX = '224.3'
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
  """Multicast service.

  This service generates a config resource file from Umpire config, and creates
  a symbolic link at Umpire base directory for the multicast server."""

  @staticmethod
  def _GetMcastGroup(service_config):
    if 'mgroup' in service_config:
      mgroup = service_config['mgroup']
    elif 'server_ip' in service_config:
      mgroup = (
          DEFAULT_MGROUP_PREFIX +
          re.search(r'\.\d+\.\d+$', service_config['server_ip']).group())
    else:
      mgroup = DEFAULT_MGROUP
    assert re.match(r'\d+\.\d+\.\d+\.\d+', mgroup)
    return mgroup

  @staticmethod
  def GenerateConfig(service_config, payloads, port):
    """Generates multicast config.

    Read all available components from the payload config, and assign a port
    for each required component.

    Args:
      service_config: The config dict of multicast service.
      payloads: The Umpire payload config.
      port: The beginning port for multicasting.

    Returns:
      Config for the multicast server."""

    mgroup = MulticastService._GetMcastGroup(service_config)

    required_components = service_config['required_components']

    mcast_addrs = {}
    for component in sorted(payloads.keys()):
      for part in payloads[component]:
        if part == 'version':
          continue

        def _IsRequiredPart(component, part):
          image_part = component + '.%s' % (part)
          return image_part in _REQUIRED_IMAGE_PARTS

        if 'image' in component and not _IsRequiredPart(component, part):
          continue

        if required_components.get(component, False):
          mcast_addrs.setdefault(component, {})
          mcast_addrs[component][part] = '%s:%s' % (mgroup, port)

        # Increment the port number here even if the port is not used, so the
        # active clients won't get the wrong payload when we update
        # `required_components` argument.
        port += 1

    mcast_config = payloads
    mcast_config['multicast'] = mcast_addrs
    mcast_config['multicast']['server_ip'] = service_config.get('server_ip', '')

    return mcast_config

  def CreateProcesses(self, umpire_config, env):
    """Creates list of processes via config.

    Args:
      umpire_config: Umpire config dict.
      env: UmpireEnv object.

    Returns:
      A list of ServiceProcess.
    """

    port = env.umpire_multicast_begin_port
    bundle = env.config.GetActiveBundle()
    payloads = env.GetPayloadsDict(bundle['payloads'])

    mcast_config = self.GenerateConfig(umpire_config['services']['multicast'],
                                       payloads, port)

    mcast_resource = env.AddConfigFromBlob(
        json_utils.DumpStr(mcast_config, pretty=True), 'multicast_config')

    env.config['multicast'] = mcast_resource

    mcast_config_file = os.path.join(env.base_dir, MCAST_CONFIG_NAME)
    file_utils.ForceSymlink(
        os.path.join('resources', mcast_resource), mcast_config_file)

    return []
