# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire config validator.

To validate a Umpire config file 'abc.json':
  from cros.factory.umpire.config import UmpireConfig
  umpire_config = UmpireConfig(file_path='abc.json')
"""

import copy

from cros.factory.umpire import common
from cros.factory.umpire.server.service import umpire_service
from cros.factory.utils import json_utils
from cros.factory.utils.schema import JSONSchemaDict


# Single bundle validator.
# A valid configuration can contain multiple bundles. At any time, one device
# state (mac, sn, mlb_sn) can map to one bundle only.
_BUNDLE_JSON_SCHEMA = {
    'type': 'object',
    'properties': {
        'id': {'type': 'string'},
        'note': {'type': 'string'},
        'payloads': {'type': 'string'}
    },
    'required': ['id', 'note', 'payloads'],
    'additionalProperties': False}

def ValidateConfig(config):
  """Validates Umpire config dict.

  ValidateConfig() imports service modules. Validates configuration schema
  and service parameters.

  Parameter:
    config: Umpire config dict.

  Raises:
    TypeError: when 'services' is not a dict.
    KeyError: when top level key 'services' not found.
    SchemaException: on schema validation failed.
  """
  for service in config['services']:
    umpire_service.LoadServiceModule(service)
  schema = JSONSchemaDict(
      'Top level Umpire config fields',
      {
          'type': 'object',
          'properties': {
              'services': umpire_service.GetServiceSchemata(),
              'bundles': {
                  'type': 'array',
                  'items': _BUNDLE_JSON_SCHEMA
              },
              'active_bundle_id': {
                  'type': 'string'
              },
              'multicast': {
                  'type': 'string'
              }
          },
          'required': ['services', 'bundles', 'active_bundle_id'],
          'additionalProperties': False})
  schema.Validate(config)


def ValidateResources(config, env):
  """Validates resources in active bundle.

  Args:
    config: Umpire config dict.
    env: UmpireEnv.

  Raises:
    UmpireError if there's any resources for active bundle missing.
  """
  error = []
  bundle = config.GetActiveBundle()
  for type_name, part, res_name in env.GetPayloadFiles(bundle['payloads']):
    try:
      env.GetResourcePath(res_name)
    except IOError:
      error.append('[NOT FOUND] resource %s:%s:%r for bundle %r\n' % (
          type_name, part, res_name, bundle['id']))
  if error:
    raise common.UmpireError(''.join(error))


class UmpireConfig(dict):
  """Container of Umpire configuration.

  It reads an Umpire config file in JSON format or a dict. Then validates it.

  Once validated, the UmpireConfig object is a dict for users to access config.

  Raises:
    TypeError: when 'services' is not a dict.
    KeyError: when top level key 'services' not found.
    SchemaException: when schema validation failed.

  Example:
    umpire_config = UmpireConfig(file_path=config_file)
    logging.info('Reads Umpire config services = %s', umpire_config['services'])
  """

  def __init__(self, config=None, file_path=None, validate=True):
    """Loads an UmpireConfig and validates it.

    If validate is set, it validates config with ValidateConfig() and checks
    default bundle's existence.

    Args:
      config: config content or an UmpireConfig dict.
      file_path: path to an Umpire config file. Must be provided if config is
          None.
      validate: True to validate config (schema check only; no resource check)
          Note that it would be removed once all UmpireConfig components are
          implemented.
    """
    assert config is not None or file_path is not None
    if config is not None:
      if isinstance(config, dict):
        # As config dict has multi-layer dict, deepcopy is necessary.
        config = copy.deepcopy(config)
      else:
        config = json_utils.LoadStr(config)
    else:
      config = json_utils.LoadFile(file_path)
    super(UmpireConfig, self).__init__(config)

    if validate:
      ValidateConfig(config)
      self.GetActiveBundle()

  def Dump(self):
    """Dump UmpireConfig to a JSON string.

    Returns:
      A string representing the UmpireConfig in JSON format.
    """
    return json_utils.DumpStr(self, pretty=True)

  def GetActiveBundle(self):
    """Gets the active bundle.

    Returns:
      The active bundle object.
    """
    bundle = self.GetBundle(self['active_bundle_id'])
    if bundle is None:
      raise common.UmpireError('Missing active bundle')
    return bundle

  def GetBundle(self, bundle_id):
    """Gets a bundle object with specific bundle ID.

    Args:
      bundle_id: bundle ID to get

    Returns:
      The bundle object. None if not found.
    """
    return next((b for b in self['bundles'] if b['id'] == bundle_id), None)
