# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Umpire YAML config validator.

To validate a YAML file 'abc.yaml':
  from cros.factory.umpire.config import UmpireConfig
  umpire_config = UmpireConfig('abc.yaml')
"""

import os
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.schema import FixedDict, List, Scalar
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire.service.umpire_service import LoadServiceModule
from cros.factory.umpire.service.umpire_service import GetServiceSchemata


# Rulesets validator.
_RULESETS_SCHEMA = List(
    'Rule sets for selecting configuration',
    FixedDict(
        'Rule and description',
        items={
            'bundle_id': Scalar('The target bundle', str),
            'note': Scalar('Brief summary of this rule', str),
            'active': Scalar('Initial state of this rule', bool)},
        optional_items={
            'mac': List('MAC address list',
                        Scalar('Network interface MAC address', str)),
            'sn': List('Serial number list',
                       Scalar('Serial number', str)),
            'mlb_sn': List('MLB serial number list',
                           Scalar('MLB serial number', str)),
            'sn_range': List(
                'Inclusive serial number start/end pair',
                Scalar('Serial number or "-" as open end', str)),
            'mlb_sn_range': List(
                'Inclusive MLB serial number start/end pair',
                Scalar('MLB serial number or "-" as open end', str))}))
# Resources validator.
_RESOURCES_SCHEMA = FixedDict(
    'Resource files in a bundle',
    items={
        'device_factory_toolkit': Scalar('Device package', str),
        'oem_partition': Scalar('OEM channel', str),
        'rootfs_release': Scalar('RELEASE channel', str),
        'rootfs_test': Scalar('TEST channel', str),
        'stateful_partition': Scalar('STATE channel', str)},
    optional_items={
        'server_factory_toolkit': Scalar('Server package', str),
        'netboot_kernel': Scalar('Netboot kernel uimg', str),
        'complete_script': Scalar('COMPLETE channel', str),
        'efi_partition': Scalar('EFI channel', str),
        'firmware': Scalar('FIRMWARE channel', str),
        'hwid': Scalar('HWID updater', str)})
# Single bundle validator.
# A valid configuration can contain multiple bundles. At any time, one device
# state (mac, sn, mlb_sn) can map to one bundle only.
_BUNDLE_SCHEMA = FixedDict(
    'Bundle for one device',
    items={
        'id': Scalar('Unique key for this bundle', str),
        'note': Scalar('Notes', str),
        'resources': _RESOURCES_SCHEMA,
        'shop_floor': FixedDict(
            'Shop floor handler settings',
            items={
                'handler': Scalar('Full handler package name', str)},
            optional_items={
                'handler_config': FixedDict(
                    'Optional handler configs',
                    optional_items={
                        'mount_point_smt': Scalar('SMT mount point', str),
                        'mount_point_fatp': Scalar('FATP mount point', str)
                        })})})


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
  map(LoadServiceModule, config['services'].keys())
  schema = FixedDict(
      'Top level Umpire config fields',
      items={
          'board': Scalar('Board name', str),
          'rulesets': _RULESETS_SCHEMA,
          'services': GetServiceSchemata(),
          'bundles': List('Bundles', _BUNDLE_SCHEMA),
          'ip': Scalar('IP address to bind', str),
          'port': Scalar('Base port', int)})
  schema.Validate(config)


class UmpireOrderedDict(dict):
  """Used to output UmpireConfig with desired key order."""
  def Omap(self):
    result = [(k, self[k]) for k in ['board', 'ip', 'port']]
    result.append(('rulesets',
                   [RulesetOrderedDict(r) for r in self['rulesets']]))
    result.append(('services', ServicesOrderedDict(self['services'])))
    result.append(('bundles',
                   [BundleOrderedDict(b) for b in self['bundles']]))
    return result


class RulesetOrderedDict(dict):
  """Used to output an UmpireConfig's ruleset with desired key order."""
  _KEY_ORDER = ['bundle_id', 'note', 'active', 'update', 'match']
  def Omap(self):
    return [(k, self[k]) for k in self._KEY_ORDER if k in self]


class ServicesOrderedDict(dict):
  """Used to output an UmpireConfig's services with desired key order."""
  _KEY_ORDER = ['archiver', 'http', 'shop_floor_handler', 'minijack',
                'mock_shop_floor_backend', 'rsync', 'dhcp', 'tftp']
  def Omap(self):
    return [(k, self[k]) for k in self._KEY_ORDER if k in self]


class BundleOrderedDict(dict):
  """Used to output an UmpireConfig's bundle with desired key order."""
  _KEY_ORDER = ['id', 'note', 'shop_floor', 'auto_update', 'resources']
  def Omap(self):
    return [(k, self[k]) for k in self._KEY_ORDER if k in self]


def RepresentOmap(dumper, data):
  """A YAML representer for ordered map with dict look."""
  return dumper.represent_mapping(u'tag:yaml.org,2002:map', data.Omap())


yaml.add_representer(UmpireOrderedDict, RepresentOmap)
yaml.add_representer(RulesetOrderedDict, RepresentOmap)
yaml.add_representer(ServicesOrderedDict, RepresentOmap)
yaml.add_representer(BundleOrderedDict, RepresentOmap)


class UmpireConfig(dict):
  """Container of Umpire configuration.

  It reads an Umpire config file in YAML format or a dict. Then validates it.

  Once validated, the UmpireConfig object is a dict for users to access config.

  Raises:
    TypeError: when 'services' is not a dict.
    KeyError: when top level key 'services' not found.
    SchemaException: when schema validation failed.

  Example:
    umpire_config = UmpireConfig(config_file)
    logging.info('Reads Umpire config for boards: %s', umpire_config['board']
  """
  def __init__(self, config, validate=True):
    """Loads an UmpireConfig and validates it.

    If validate is set, it validates config with ValidateConfig() and checks
    default bundle's existance.

    Args:
      config_path: path to an Umpire config file or an UmpireConfig dict.
      validate: True to validate. Note that it would be removed once
          all UmpireConfig components are implemented.
    """
    if isinstance(config, str) and os.path.isfile(config):
      with open(config, 'r') as f:
        config = yaml.load(f)

    super(UmpireConfig, self).__init__(config)

    if validate:
      ValidateConfig(config)
      if not self.GetDefaultBundle():
        raise UmpireError('Missing default bundle')

  def WriteFile(self, config_file):
    """Writes UmpireConfig to a file in YAML format.

    Args:
      config_file: path to write.
    """
    with open(config_file, 'w') as f:
      yaml.dump(UmpireOrderedDict(self), f, default_flow_style=False)

  def GetDefaultBundle(self):
    """Gets the default bundle.

    Returns:
      The default bundle object. None if not found.
    """
    for rule in reversed(self.get('rulesets', [])):
      if rule['active']:
        return self.GetBundle(rule['bundle_id'])
    return None

  def GetBundle(self, bundle_id):
    """Gets a bundle object with specific bundle ID.

    Args:
      bundle_id: bundle ID to get

    Returns:
      The bundle object. None if not found.
    """
    for bundle in self.get('bundles', []):
      if bundle['id'] == bundle_id:
        return bundle
    return None
