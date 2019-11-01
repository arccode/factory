#!/usr/bin/env python2
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Methods to generate the verification payload from the HWID database."""

import collections
import copy
import re

from six import iteritems

# pylint: disable=import-error, no-name-in-module
from google.protobuf import text_format
import hardware_verifier_pb2
import runtime_probe_pb2

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import common as hwid_common
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import rule as hwid_rule
from cros.factory.utils import json_utils
from cros.factory.utils import schema


class GenerateVerificationPayloadError(Exception):
  """Error that indicates a failure on generating verification payload."""


class ProbeStatementGeneratorNotSuitableError(Exception):
  """The given component values cannot be converted by this generator."""


GenericProbeStatementInfo = collections.namedtuple(
    'GenericProbeStatementInfo', ['probe_statement', 'whitelist_fields'])


# TODO(yhong): Remove the expect field when runtime_probe converts the output
#              format automatically (b/133641904).
GENERIC_PROBE_STATEMENTS = {
    runtime_probe_pb2.ProbeRequest.battery: GenericProbeStatementInfo(
        {'eval': {'generic_battery': {}}},
        ['manufacturer', 'model_name', 'technology']),
    runtime_probe_pb2.ProbeRequest.storage: GenericProbeStatementInfo(
        {'eval': {'generic_storage': {}},
         'expect': {'sectors': [False, 'int'],
                    'manfid': [False, 'hex'],
                    'pci_vendor': [False, 'hex'],
                    'pci_device': [False, 'hex'],
                    'pci_class': [False, 'hex']}},
        ['type', 'sectors', 'manfid', 'name', 'pci_vendor', 'pci_device',
         'pci_class', 'ata_vendor', 'ata_model']),
}


GENERIC_COMPONENT_NAME = 'generic'


class ProbeStatementGenerator(object):
  """Base class of the probe statement generator.

  Each sub-class represents a generator of a specific probe function.

  Properties:
    SUPPORTED_CATEGORIES: A dictionary that maps the component category in
        the HWID database to the corresponding component category enum item
        in the probe statement.
  """
  SUPPORTED_CATEGORIES = None

  @classmethod
  def TryGenerate(cls, comp_values):
    """Generates the corresponding probe statement from the given data.

    Args:
      comp_values: The probed component values from the HWID database.

    Returns:
      The generated probe statement object.

    Raises:
      `ProbeStatementGeneratorNotSuitableError` if it fails to transform
          the given `comp_values` to the corresponding probe statement.
    """
    raise NotImplementedError


_all_probe_statement_generators = []


def RegisterProbeStatementGenerator(cls):
  _all_probe_statement_generators.append(cls)
  return cls


def GetAllProbeStatementGenerators():
  return _all_probe_statement_generators


def _CompValueToExpectStrField(value):
  if isinstance(value, hwid_rule.Value):
    pattern = ('!re ' if value.is_re  else '!eq ') + value.raw_value
  else:
    pattern = '!eq ' + value
  return [True, 'str', pattern]


def _GetHexStrRegexp(num_bits=None):
  if not num_bits:
    return re.compile('0x[0-9a-f]+$', flags=re.IGNORECASE)

  assert num_bits % 8 == 0
  return re.compile('0x[0-9a-f]{%d}$' % (num_bits // 4), flags=re.IGNORECASE)


_NUMBER_REGEXP = re.compile('[0-9]+$')


@RegisterProbeStatementGenerator
class GenericBatteryProbeStatementGenerator(ProbeStatementGenerator):
  SUPPORTED_CATEGORIES = {'battery': runtime_probe_pb2.ProbeRequest.battery}

  @classmethod
  def TryGenerate(cls, comp_values):
    probe_statement = {'eval': {'generic_battery': {}}, 'expect': {}}
    for field_name in ('manufacturer', 'model_name'):
      try:
        probe_statement['expect'][field_name] = _CompValueToExpectStrField(
            comp_values[field_name])
      except KeyError:
        raise ProbeStatementGeneratorNotSuitableError('missing field: %s' %
                                                      field_name)
    return probe_statement


class GenericStorageProbeStatementGeneratorBase(ProbeStatementGenerator):
  """A base class of the probe statement generator of `generic_storage` func.

  The probe function `generic_storage` is actually a superset of different kind
  of probing methods.  The generator for each of the method are similar but
  still different.  This class extracts the common part out and leave the
  method-specific part to be customized by the sub-class.
  """
  SUPPORTED_CATEGORIES = {'storage': runtime_probe_pb2.ProbeRequest.storage}

  STORAGE_TYPE = None  # Type of the storage, defined by the sub-class.

  _COMMON_COMP_VALUE_SCHEMA_ITEMS = {
      'sectors': schema.RegexpStr('sectors', _NUMBER_REGEXP)}

  @classmethod
  def TryGenerate(cls, comp_values):
    fixed_dict_items = copy.copy(cls._COMMON_COMP_VALUE_SCHEMA_ITEMS)
    fixed_dict_items.update(cls.GetExtraCompValueSchemaItems())
    schema_obj = schema.FixedDict(
        'component values', items=fixed_dict_items, allow_undefined_keys=True)
    try:
      schema_obj.Validate(comp_values)
    except schema.SchemaException as e:
      raise ProbeStatementGeneratorNotSuitableError('schema mismatch: %r' % e)

    probe_statement = {
        'eval': {'generic_storage': {}},
        'expect': {
            'sectors': [True, 'int', '!eq ' + comp_values['sectors']]
        }
    }
    probe_statement['expect'].update(cls.GenerateExtraExpectFields(comp_values))
    return probe_statement

  @classmethod
  def GetExtraCompValueSchemaItems(cls):
    raise NotImplementedError

  @classmethod
  def GenerateExtraExpectFields(cls, comp_values):
    raise NotImplementedError


@RegisterProbeStatementGenerator
class GenericStorageMMCProbeStatementGenerator(
    GenericStorageProbeStatementGeneratorBase):
  """Generator for MMC type of `generic_storage` function."""

  @classmethod
  def GetExtraCompValueSchemaItems(cls):
    return {'name': schema.RegexpStr('name', re.compile(r'.{6}$')),
            'manfid': schema.RegexpStr('manfid', _GetHexStrRegexp(num_bits=24)),
            'oemid': schema.RegexpStr('oemid', _GetHexStrRegexp(num_bits=16)),
            'prv': schema.RegexpStr('prv', _GetHexStrRegexp())}

  @classmethod
  def GenerateExtraExpectFields(cls, comp_values):
    ret = {fn: [True, 'hex', '!eq ' + comp_values[fn]]
           for fn in ('manfid', 'oemid', 'prv')}
    ret['name'] = _CompValueToExpectStrField(comp_values['name'])
    return ret


@RegisterProbeStatementGenerator
class GenericStorageATAProbeStatementGenerator(
    GenericStorageProbeStatementGeneratorBase):
  """Generator for ATA/SATA type of `generic_storage` function."""

  @classmethod
  def GetExtraCompValueSchemaItems(cls):
    return {'vendor': schema.RegexpStr('vendor', re.compile(r'.+$')),
            'model': schema.RegexpStr('manfid', re.compile(r'.+$'))}

  @classmethod
  def GenerateExtraExpectFields(cls, comp_values):
    return {'ata_' + fn: [True, 'str', '!eq ' + comp_values[fn]]
            for fn in ('vendor', 'model')}


@RegisterProbeStatementGenerator
class GenericStorageNVMeProbeStatementGenerator(
    GenericStorageProbeStatementGeneratorBase):
  """Generator for NVMe type of `generic_storage` function."""

  @classmethod
  def GetExtraCompValueSchemaItems(cls):
    return {'vendor': schema.RegexpStr('vendor', _GetHexStrRegexp(num_bits=16)),
            'device': schema.RegexpStr('device', _GetHexStrRegexp(num_bits=16)),
            'class': schema.RegexpStr('class', _GetHexStrRegexp(num_bits=24))}

  @classmethod
  def GenerateExtraExpectFields(cls, comp_values):
    return {'pci_' + fn: [True, 'hex', '!eq ' + comp_values[fn]]
            for fn in ('vendor', 'device', 'class')}


def GenerateVerificationPayload(dbs):
  """Generates the corresponding verification payload from the given HWID DBs.

  This function ignores the component categories that no corresponding generator
  can handle.  For example, if no generator can handle the `cpu` category,
  this function will ignore all CPU components.  If at least one generator
  class can handle `cpu` category but all related generators fail to handle
  any of the `cpu` component in the given HWID databases, this function raises
  exception to indicate a failure.

  Args:
    dbs: A list of the HWID database object of the same board.

  Returns:
    A string-to-string dictionary which represents the files that should
    be committed into the bsp package.

  Raises:
    `GenerateVerificationPayloadError` if it fails to generate the
        corresponding payloads.
  """
  _STATUS_MAP = {
      hwid_common.COMPONENT_STATUS.supported: hardware_verifier_pb2.QUALIFIED,
      hwid_common.COMPONENT_STATUS.unqualified:
          hardware_verifier_pb2.UNQUALIFIED,
      hwid_common.COMPONENT_STATUS.deprecated: hardware_verifier_pb2.REJECTED,
      hwid_common.COMPONENT_STATUS.unsupported: hardware_verifier_pb2.REJECTED,
  }

  def _AddProbeStatement(probe_config_data, comp_category, probe_statement):
    comp_category_name = runtime_probe_pb2.ProbeRequest.SupportCategory.Name(
        comp_category)
    probe_config_data.setdefault(comp_category_name, {}).update(
        probe_statement)

  def _AppendProbeStatement(
      probe_config_data, comp_category, comp_name, probe_statement):
    comp_category_name = runtime_probe_pb2.ProbeRequest.SupportCategory.Name(
        comp_category)
    probe_config_data.setdefault(comp_category_name, {})[
        comp_name] = probe_statement

  ps_generators = collections.defaultdict(list)
  for ps_gen in GetAllProbeStatementGenerators():
    for hwid_comp_category in ps_gen.SUPPORTED_CATEGORIES:
      ps_generators[hwid_comp_category].append(ps_gen)

  ret_files = {}
  hw_verification_spec = hardware_verifier_pb2.HwVerificationSpec()
  for db in dbs:
    model_prefix = db.project.lower()
    probe_config_data = {}
    for hwid_comp_category, ps_gens in iteritems(ps_generators):
      comps = db.GetComponents(hwid_comp_category, include_default=False)
      for comp_name, comp_info in iteritems(comps):
        unique_comp_name = model_prefix + '_' + comp_name
        if comp_info.status == hwid_common.COMPONENT_STATUS.duplicate:
          continue

        is_handled = False
        for ps_gen in ps_gens:
          try:
            # `comp_info.values` is in type of collections.OrderedDict, which
            # makes the schema check fails so we convert it to a regular dict
            # first.
            probe_statement = ps_gen.TryGenerate(dict(comp_info.values))
          except ProbeStatementGeneratorNotSuitableError:
            continue
          if is_handled:
            assert False, ("The code shouldn't reach here because we expect "
                           'only one generator can handle the given component '
                           'by design.')
          comp_category = ps_gen.SUPPORTED_CATEGORIES[hwid_comp_category]
          _AppendProbeStatement(probe_config_data, comp_category,
                                unique_comp_name, probe_statement)
          hw_verification_spec.component_infos.add(
              component_category=comp_category, component_uuid=unique_comp_name,
              qualification_status=_STATUS_MAP[comp_info.status])
          is_handled = True
        if not is_handled:
          raise GenerateVerificationPayloadError(
              'no probe statement generator supports %r typed component %r' %
              (hwid_comp_category, comp_info))

      # Append the generic probe statements.
      for comp_category, ps_info in iteritems(GENERIC_PROBE_STATEMENTS):
        _AppendProbeStatement(probe_config_data, comp_category,
                              GENERIC_COMPONENT_NAME, ps_info.probe_statement)
    probe_config_pathname = 'runtime_probe/%s/probe_config.json' % model_prefix
    ret_files[probe_config_pathname] = json_utils.DumpStr(probe_config_data,
                                                          pretty=True)
  hw_verification_spec.component_infos.sort(
      key=lambda ci: (ci.component_category, ci.component_uuid))
  # Append the whitelists in the verification spec.
  for comp_category, ps_info in iteritems(GENERIC_PROBE_STATEMENTS):
    hw_verification_spec.generic_component_value_whitelists.add(
        component_category=comp_category, field_names=ps_info.whitelist_fields)
  ret_files['hw_verification_spec.prototxt'] = text_format.MessageToString(
      hw_verification_spec)

  return ret_files


def main():
  # only import the required modules while running this module as a program
  import argparse
  import logging
  import os

  from cros.factory.utils import file_utils

  ap = argparse.ArgumentParser(
      description=('Generate the verification payload source files from the '
                   'given HWID databases.'))
  ap.add_argument('-o', '--output_dir', metavar='PATH',
                  help=('Base path to the output files. In most of the cases, '
                        'it should be '
                        'chromeos-base/chromeos-bsp-<BOARD>-private/files '
                        'in a private overlay repository.'))
  ap.add_argument('hwid_db_paths', metavar='HWID_DATABASE_PATH', nargs='+',
                  help=('Paths to the input HWID databases. If the board '
                        'has multiple models, users should specify all models '
                        'at once.'))
  ap.add_argument('--no_verify_checksum', action='store_true',
                  help="Don't verify the checksum in the HWID databases.")
  args = ap.parse_args()

  logging.basicConfig(level=logging.INFO)

  dbs = []
  for hwid_db_path in args.hwid_db_paths:
    logging.info('Load the HWID database file (%s).', hwid_db_path)
    dbs.append(database.Database.LoadFile(
        hwid_db_path, verify_checksum=not args.no_verify_checksum))

  logging.info('Generate the verification payload data.')
  results = GenerateVerificationPayload(dbs)

  for pathname, content in iteritems(results):
    logging.info('Output the verification payload file (%s).', pathname)
    fullpath = os.path.join(args.output_dir, pathname)
    file_utils.TryMakeDirs(os.path.dirname(fullpath))
    file_utils.WriteFile(fullpath, content)


if __name__ == '__main__':
  main()
