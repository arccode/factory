# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire config validator.

To validate a Umpire config file 'abc.json':
  from cros.factory.umpire.config import UmpireConfig
  umpire_config = UmpireConfig(file_path='abc.json')
"""

from __future__ import print_function

import copy
import re

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import common
from cros.factory.umpire.server.service import umpire_service
from cros.factory.utils import json_utils
from cros.factory.utils.schema import FixedDict
from cros.factory.utils.schema import List
from cros.factory.utils.schema import Optional
from cros.factory.utils.schema import Scalar


NUMBER_SHOP_FLOOR_HANDLERS = 50


# Ruleset matcher validator.
_RULE_MATCHER_SCHEMA = FixedDict(
    'Matcher of a rule',
    optional_items={
        'mac': List('MAC address list',
                    Scalar('Network interface MAC address', basestring)),
        'sn': List('Serial number list',
                   Scalar('Serial number', basestring)),
        'mlb_sn': List('MLB serial number list',
                       Scalar('MLB serial number', basestring)),
        'stage': List('Matched stage list', Scalar('Stage', basestring)),
        'sn_range': List(
            'Inclusive serial number start/end pair',
            Scalar('Serial number or "-" as open end', basestring)),
        'mlb_sn_range': List(
            'Inclusive MLB serial number start/end pair',
            Scalar('MLB serial number or "-" as open end', basestring))})
# Factory stage range.
_FACTORY_STAGE_RANGE = List(
    'Factory stage range',
    Optional(label='Factory stage',
             types=[Scalar('Fixed factory stage', basestring)]))
# Rulesets enable_update validator.
_ENABLE_UPDATE_SCHEMA = FixedDict(
    'Matcher of enable update',
    optional_items={
        'device_factory_toolkit': _FACTORY_STAGE_RANGE,
        'firmware_bios': _FACTORY_STAGE_RANGE,
        'firmware_ec': _FACTORY_STAGE_RANGE,
        'firmware_pd': _FACTORY_STAGE_RANGE,
        'rootfs_release': _FACTORY_STAGE_RANGE,
        'rootfs_test': _FACTORY_STAGE_RANGE})
# Rulesets validator.
_RULESETS_SCHEMA = List(
    'Rule sets for selecting configuration',
    FixedDict(
        'Rule and description',
        items={
            'bundle_id': Scalar('The target bundle', basestring),
            'note': Scalar('Brief summary of this rule', basestring),
            'active': Scalar('Initial state of this rule', bool)},
        optional_items={
            'match': _RULE_MATCHER_SCHEMA,
            'enable_update': _ENABLE_UPDATE_SCHEMA}))
# Single bundle validator.
# A valid configuration can contain multiple bundles. At any time, one device
# state (mac, sn, mlb_sn) can map to one bundle only.
_BUNDLE_SCHEMA = FixedDict(
    'Bundle for one device',
    items={
        'id': Scalar('Unique key for this bundle', basestring),
        'note': Scalar('Notes', basestring),
        'payloads': Scalar('Payload', basestring)},
    # TODO(hungte) Remove the deprecated shop_floor.
    optional_items={
        'shop_floor': FixedDict(
            '(Deprecated) Shop floor handler settings',
            optional_items={
                'handler': Scalar('Full handler package name', basestring),
                'handler_config': FixedDict(
                    'Optional handler configs',
                    optional_items={
                        'mount_point_smt': Scalar('SMT mount point',
                                                  basestring),
                        'mount_point_fatp': Scalar('FATP mount point',
                                                   basestring)
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
  for service in config['services']:
    umpire_service.LoadServiceModule(service)
  schema = FixedDict(
      'Top level Umpire config fields',
      items={
          'rulesets': _RULESETS_SCHEMA,
          'services': umpire_service.GetServiceSchemata(),
          'bundles': List('Bundles', _BUNDLE_SCHEMA)})
  schema.Validate(config)


def ValidateResources(config, env):
  """Validates resources in each active bundle.

  Args:
    config: Umpire config dict.
    env: UmpireEnv.

  Raises:
    UmpireError if there's any resources for active bundles missing.
  """
  error = []
  for bundle in config.GetActiveBundles():
    payloads = env.GetPayloadsDict(bundle['payloads'])
    for type_name, payload_dict in payloads.iteritems():
      for part, res_name in payload_dict.iteritems():
        if part == 'file' or re.match(r'part\d+$', part):
          try:
            env.GetResourcePath(res_name)
          except IOError:
            error.append('[NOT FOUND] resource %s:%s:%r for bundle %r\n' % (
                type_name, part, res_name, bundle['id']))
  if error:
    raise common.UmpireError(''.join(error))


def ShowDiff(original, new):
  """Shows difference between original and new UmpireConfig.

  Note that it only compares active bundles, i.e. bundles which are used by
  active rulesets.

  Args:
    original: Original UmpireConfig object.
    new: New UmpireConfig object.

  Returns:
    List of string showing the difference.
  """
  def DumpRulesets(rulesets):
    INDENT_SPACE = '  '
    for r in rulesets:
      rule_json = json_utils.DumpStr(r, pretty=True)
      result.extend((INDENT_SPACE + line) for line in rule_json.splitlines())

  result = []
  original_active_rulesets = [r for r in original['rulesets'] if r['active']]
  new_active_rulesets = [r for r in new['rulesets'] if r['active']]
  newly_added_rulesets = [r for r in new_active_rulesets
                          if r not in original_active_rulesets]
  deleted_rulesets = [r for r in original_active_rulesets
                      if r not in new_active_rulesets]

  if newly_added_rulesets:
    result.append('Newly added rulesets:')
    DumpRulesets(newly_added_rulesets)

  if deleted_rulesets:
    result.append('Deleted rulesets:')
    DumpRulesets(deleted_rulesets)

  return result


class UmpireConfig(dict):
  """Container of Umpire configuration.

  It reads an Umpire config file in JSON format or a dict. Then validates it.

  Once validated, the UmpireConfig object is a dict for users to access config.

  Properties:
    bundle_map: maps bundle ID to bundle dict.

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
        config = json_utils.LoadStr(config, convert_to_str=False)
    else:
      config = json_utils.LoadFile(file_path, convert_to_str=False)
    super(UmpireConfig, self).__init__(config)

    self.bundle_map = {}
    self.BuildBundleMap()

    if validate:
      ValidateConfig(config)
      if not self.GetDefaultBundle():
        raise common.UmpireError('Missing default bundle')

  def BuildBundleMap(self):
    """Builds bundle_map attribute.

    bundle_map is a dict maps bundle ID to bundle dict.
    """
    self.bundle_map = {bundle['id']: bundle for bundle in self['bundles']}

  def Dump(self):
    """Dump UmpireConfig to a JSON string.

    Returns:
      A string representing the UmpireConfig in JSON format.
    """
    return json_utils.DumpStr(self, pretty=True)

  def GetDefaultBundle(self):
    """Gets the default bundle.

    Returns:
      The default bundle object. None if not found.
    """
    for rule in self['rulesets']:
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
    return self.bundle_map.get(bundle_id)

  def GetActiveBundles(self):
    """Gets active bundles.

    Returns:
      Iterable of active bundles.
    """
    for active_rule in (r for r in self['rulesets'] if r['active']):
      bundle_id = active_rule['bundle_id']
      if bundle_id in self.bundle_map:
        yield self.bundle_map[bundle_id]
