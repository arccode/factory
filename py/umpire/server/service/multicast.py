# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Multicast service for umpire resources."""

import os

from cros.factory.umpire.server.service import umpire_service
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils
from cros.factory.utils.schema import JSONSchemaDict


FACTORY_ENV = '/usr/local/factory/bin/factory_env'

MCAST_CONFIG_NAME = 'multicast_config.json'
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
_MULTICAST_CONFIG_SCHEMA = JSONSchemaDict(
    'multicast config schema object', {
        'definitions': {
            'multicast_group': {
                'description': 'An IP address in 224.0.0.0/4',
                'type': 'string',
            },
            'file_payload': {
                'type': 'object',
                'properties': {
                    'file': {
                        '$ref': '#/definitions/multicast_group'
                    },
                },
                'additionalProperties': False,
            },
            'image_payload': {
                'type': 'object',
                'patternProperties': {
                    r'part\d+': {
                        '$ref': '#/definitions/multicast_group'
                    },
                },
                'additionalProperties': False,
            },
        },
        'type': 'object',
        'properties': {
            'multicast': {
                'type': 'object',
                'properties': {
                    'server_ip': {
                        'type': 'string',
                    },
                    'test_image': {
                        '$ref': '#/definitions/image_payload'
                    },
                    'toolkit': {
                        '$ref': '#/definitions/file_payload'
                    },
                    'release_image': {
                        '$ref': '#/definitions/image_payload'
                    },
                },
                'additionalProperties': False,
            },
        },
        'additionalProperties': True,
        'required': ['multicast'],
    })


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

    mgroup = mcast_service_config.get('mgroup', MCAST_DEFAULT_ADDRESS)
    port = env.umpire_multicast_begin_port

    required_components = mcast_service_config['required_components']

    # Read all available components from the payload config file and assign a
    # port for each required component for multicasting.
    mcast_addrs = {}
    bundle = env.config.GetActiveBundle()
    payloads = env.GetPayloadsDict(bundle['payloads'])
    for component in sorted(payloads.keys()):
      for part in payloads[component]:
        if part == 'version':
          continue

        if 'image' in component:
          image_part = component + '.%s' % (part)
          if image_part not in _REQUIRED_IMAGE_PARTS:
            continue

        if required_components.get(component, False):
          mcast_addrs.setdefault(component, {})
          mcast_addrs[component][part] = '%s:%s' % (mgroup, port)
        # Increment the port number here even if the port is not used, so the
        # port number won't be changed after we update `required_components`
        # argument.  If the port number has changed during a download and there
        # is a client listening on a port, the client will download an
        # unexpected file
        port += 1

    # Add multicast config into umpire env.
    mcast_config = payloads
    mcast_config['multicast'] = mcast_addrs
    mcast_config['multicast']['server_ip'] = mcast_service_config.get(
        'server_ip', '')

    _MULTICAST_CONFIG_SCHEMA.Validate(mcast_config)

    mcast_resource_name = env.AddConfigFromBlob(
        json_utils.DumpStr(mcast_config, pretty=True), 'multicast_config')

    env.config['multicast'] = mcast_resource_name

    mcast_config_file = os.path.join(env.base_dir, MCAST_CONFIG_NAME)

    file_utils.TryUnlink(mcast_config_file)
    os.symlink(
        os.path.join('resources', mcast_resource_name), mcast_config_file)

    return []
