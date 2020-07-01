#!/usr/bin/env python3
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Methods to generate the verification payload from the HWID database."""

import re
import functools

# pylint: disable=import-error, no-name-in-module
from google.protobuf import text_format
import hardware_verifier_pb2
import runtime_probe_pb2

from cros.factory.hwid.v3 import common as hwid_common
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import rule as hwid_rule
from cros.factory.probe.runtime_probe import probe_config_definition
from cros.factory.probe.runtime_probe import probe_config_types
from cros.factory.utils import type_utils


class ProbeStatementGeneratorNotSuitableError(Exception):
  """The given component values cannot be converted by this generator."""


class GenericProbeStatementInfoRecord:
  """Placeholder for info. related to the generic probe statement.

  Attributes:
    probe_category: The name of the probe category.
    probe_func_name: The name of the probe function.
    whitelist_fields: A list of fields that is allowed to be outputted.
  """

  def __init__(self, probe_category, probe_func_name, whitelist_fields):
    self.probe_category = probe_category
    self.probe_func_name = probe_func_name
    self.whitelist_fields = whitelist_fields

  def GenerateProbeStatement(self):
    return probe_config_definition.GetProbeStatementDefinition(
        self.probe_category).GenerateProbeStatement(
            'generic', self.probe_func_name,
            {fn: None for fn in self.whitelist_fields})


# TODO(yhong): Remove the expect field when runtime_probe converts the output
#              format automatically (b/133641904).
@type_utils.CachedGetter
def _GetAllGenericProbeStatementInfoRecords():
  return [
      GenericProbeStatementInfoRecord(
          'battery', 'generic_battery',
          ['manufacturer', 'model_name', 'technology']),
      GenericProbeStatementInfoRecord(
          'storage', 'generic_storage',
          ['type', 'sectors', 'manfid', 'name', 'pci_vendor', 'pci_device',
           'pci_class', 'ata_vendor', 'ata_model']),
      GenericProbeStatementInfoRecord(
          'network', 'generic_network',
          ['type', 'bus_type', 'pci_vendor_id', 'pci_device_id',
           'pci_revision', 'usb_vendor_id', 'usb_product_id',
           'usb_bcd_device']),
      GenericProbeStatementInfoRecord(
          'dram', 'memory',
          ['part', 'size', 'slot']),
  ]


class _FieldRecord:
  def __init__(self, hwid_field_name, probe_statement_field_name,
               value_converter, is_optional=False):
    self.hwid_field_name = hwid_field_name
    self.probe_statement_field_name = probe_statement_field_name
    self.value_converter = value_converter
    self.is_optional = is_optional


class MissingComponentValueError(ProbeStatementGeneratorNotSuitableError):
  pass


class ProbeStatementConversionError(ProbeStatementGeneratorNotSuitableError):
  pass


class _ProbeStatementGenerator:
  def __init__(self, probe_category, probe_function_name, field_converters,
               probe_function_argument=None):
    self.probe_category = probe_category

    self._probe_statement_generator = (
        probe_config_definition.GetProbeStatementDefinition(probe_category))
    self._probe_function_name = probe_function_name
    self._field_converters = field_converters
    self._probe_function_argument = probe_function_argument

  def TryGenerate(self, comp_name, comp_values, information=None):
    expected_fields = {}
    for fc in self._field_converters:
      try:
        val = comp_values[fc.hwid_field_name]
      except KeyError:
        if fc.is_optional:
          expected_fields[fc.probe_statement_field_name] = None
          continue
        raise MissingComponentValueError(
            'missing component value field: %r' % fc.hwid_field_name)
      try:
        expected_fields[fc.probe_statement_field_name] = fc.value_converter(val)
      except Exception as e:
        raise ProbeStatementConversionError(
            'unable to convert the value of field %r : %r' %
            (fc.hwid_field_name, e))
    try:
      return self._probe_statement_generator.GenerateProbeStatement(
          comp_name, self._probe_function_name, expected_fields,
          probe_function_argument=self._probe_function_argument,
          information=information)
    except Exception as e:
      raise ProbeStatementConversionError(
          'unable to convert to the probe statement : %r' % e)


@type_utils.CachedGetter
def GetAllProbeStatementGenerators():
  def HWIDValueToStr(value):
    if isinstance(value, hwid_rule.Value):
      return re.compile(value.raw_value) if value.is_re else value.raw_value
    return value

  def StrToNum(value):
    if not re.match('-?[0-9]+$', value):
      raise ValueError('not a regular string of number')
    return int(value)

  def HWIDHexStrToHexStr(num_digits, has_prefix, value):
    prefix = '0x' if has_prefix else ''
    if not re.match('%s0*[0-9a-fA-F]{1,%d}$' % (prefix, num_digits), value):
      raise ValueError(
          'not a regular string of %d digits hex number' % num_digits)
    # Regulate the output to the fixed-digit hex string with upper cases.
    return value.upper()[len(prefix):][-num_digits:].zfill(num_digits)

  def GetHWIDHexStrToHexStrConverter(num_digits, has_prefix=True):
    return functools.partial(HWIDHexStrToHexStr, num_digits, has_prefix)

  def SimplyForwardValue(value):
    return value

  def same_name_field_converter(n, c, *args, **kwargs):
    return _FieldRecord(n, n, c, *args, **kwargs)

  all_probe_statement_generators = {}

  all_probe_statement_generators['battery'] = [
      _ProbeStatementGenerator('battery', 'generic_battery', [
          same_name_field_converter('manufacturer', HWIDValueToStr),
          same_name_field_converter('model_name', HWIDValueToStr),
          same_name_field_converter('technology', HWIDValueToStr),
      ])
  ]

  storage_shared_fields = [
      same_name_field_converter('sectors', StrToNum)
  ]
  all_probe_statement_generators['storage'] = [
      # eMMC
      _ProbeStatementGenerator(
          'storage', 'generic_storage',
          storage_shared_fields + [
              same_name_field_converter('name', SimplyForwardValue),
              same_name_field_converter(
                  'manfid', GetHWIDHexStrToHexStrConverter(2)),
              same_name_field_converter(
                  'oemid', GetHWIDHexStrToHexStrConverter(4)),
              same_name_field_converter(
                  'prv', GetHWIDHexStrToHexStrConverter(2)),
          ]
      ),
      # NVMe
      _ProbeStatementGenerator(
          'storage', 'generic_storage',
          storage_shared_fields + [
              _FieldRecord('vendor', 'pci_vendor',
                           GetHWIDHexStrToHexStrConverter(4)),
              _FieldRecord('device', 'pci_device',
                           GetHWIDHexStrToHexStrConverter(4)),
              _FieldRecord('class', 'pci_class',
                           GetHWIDHexStrToHexStrConverter(6)),
          ]
      ),
      # ATA
      _ProbeStatementGenerator(
          'storage', 'generic_storage',
          storage_shared_fields + [
              _FieldRecord('vendor', 'ata_vendor', HWIDValueToStr),
              _FieldRecord('model', 'ata_model', HWIDValueToStr),
          ]
      ),
  ]

  # TODO(yhong): Also convert SDIO network component probe statements.
  network_pci_fields = [
      _FieldRecord('vendor', 'pci_vendor_id',
                   GetHWIDHexStrToHexStrConverter(4)),
      # TODO(yhong): Set `pci_device_id` to non optional field when b/150914933
      #     is resolved.
      _FieldRecord('device', 'pci_device_id',
                   GetHWIDHexStrToHexStrConverter(4),
                   is_optional=True),
      _FieldRecord('revision_id', 'pci_revision',
                   GetHWIDHexStrToHexStrConverter(2),
                   is_optional=True),
  ]
  network_usb_fields = [
      _FieldRecord('idVendor', 'usb_vendor_id',
                   GetHWIDHexStrToHexStrConverter(4, has_prefix=False)),
      _FieldRecord('idProduct', 'usb_product_id',
                   GetHWIDHexStrToHexStrConverter(4, has_prefix=False)),
      _FieldRecord('bcdDevice', 'usb_bcd_device',
                   GetHWIDHexStrToHexStrConverter(4, has_prefix=False),
                   is_optional=True),
  ]
  all_probe_statement_generators['wireless'] = [
      _ProbeStatementGenerator(
          'network', 'wireless_network', network_pci_fields),
      _ProbeStatementGenerator(
          'network', 'wireless_network', network_usb_fields),
  ]
  all_probe_statement_generators['cellular'] = [
      _ProbeStatementGenerator(
          'network', 'cellular_network', network_pci_fields),
      _ProbeStatementGenerator(
          'network', 'cellular_network', network_usb_fields),
  ]
  all_probe_statement_generators['ethernet'] = [
      _ProbeStatementGenerator(
          'network', 'ethernet_network', network_pci_fields),
      _ProbeStatementGenerator(
          'network', 'ethernet_network', network_usb_fields),
  ]

  dram_fields = [
      same_name_field_converter('part', HWIDValueToStr),
      same_name_field_converter('size', StrToNum),
      same_name_field_converter('slot', StrToNum, is_optional=True),
  ]
  all_probe_statement_generators['dram'] = [
      _ProbeStatementGenerator('dram', 'memory', dram_fields),
  ]

  return all_probe_statement_generators


class VerificationPayloadGenerationResult:
  """
  Attributes:
    generated_file_contents: A string-to-string dictionary which represents the
        files that should be committed into the bsp package.
    error_msgs: A list of errors encountered during the generation.
  """
  def __init__(self):
    self.generated_file_contents = {}
    self.error_msgs = []


def GenerateVerificationPayload(dbs):
  """Generates the corresponding verification payload from the given HWID DBs.

  This function ignores the component categories that no corresponding generator
  can handle.  For example, if no generator can handle the `cpu` category,
  this function will ignore all CPU components.  If at least one generator
  class can handle `cpu` category but all related generators fail to handle
  any of the `cpu` component in the given HWID databases, this function raises
  exception to indicate a failure.

  Args:
    dbs: A list of tuple of the HWID database object and the waived categories.

  Returns:
    Instance of `VerificationPayloadGenerationResult`.
  """
  _STATUS_MAP = {
      hwid_common.COMPONENT_STATUS.supported: hardware_verifier_pb2.QUALIFIED,
      hwid_common.COMPONENT_STATUS.unqualified:
          hardware_verifier_pb2.UNQUALIFIED,
      hwid_common.COMPONENT_STATUS.deprecated: hardware_verifier_pb2.REJECTED,
      hwid_common.COMPONENT_STATUS.unsupported: hardware_verifier_pb2.REJECTED,
  }
  ProbeRequestSupportCategory = runtime_probe_pb2.ProbeRequest.SupportCategory

  def TryGenerateProbeStatement(comp_name, comp_values, ps_gens,
                                information=None):
    ret = []
    for ps_gen in ps_gens:
      try:
        ps = ps_gen.TryGenerate(comp_name, comp_values, information)
        ret.append((ps_gen, ps))
      except ProbeStatementGeneratorNotSuitableError:
        continue
    return ret

  ps_generators = GetAllProbeStatementGenerators()
  ret = VerificationPayloadGenerationResult()

  hw_verification_spec = hardware_verifier_pb2.HwVerificationSpec()
  for db, waived_categories in dbs:
    model_prefix = db.project.lower()
    probe_config = probe_config_types.ProbeConfigPayload()
    for hwid_comp_category, ps_gens in ps_generators.items():
      if hwid_comp_category in waived_categories:
        continue
      comps = db.GetComponents(hwid_comp_category, include_default=False)
      for comp_name, comp_info in comps.items():
        unique_comp_name = model_prefix + '_' + comp_name
        if comp_info.status == hwid_common.COMPONENT_STATUS.duplicate:
          continue

        results = TryGenerateProbeStatement(
            unique_comp_name, comp_info.values, ps_gens, comp_info.information)
        if not results:
          ret.error_msgs.append('No probe statement generator is suitable for '
                                'component %r.' % unique_comp_name)
          continue
        if len(results) > 1:
          assert False, ("The code shouldn't reach here because we expect "
                         'only one generator can handle the given component '
                         'by design.')
        ps_gen, probe_statement = results[0]

        probe_config.AddComponentProbeStatement(probe_statement)
        hw_verification_spec.component_infos.add(
            component_category=ProbeRequestSupportCategory.Value(
                ps_gen.probe_category),
            component_uuid=unique_comp_name,
            qualification_status=_STATUS_MAP[comp_info.status])

    # Append the generic probe statements.
    for ps_gen in _GetAllGenericProbeStatementInfoRecords():
      probe_config.AddComponentProbeStatement(ps_gen.GenerateProbeStatement())

    probe_config_pathname = 'runtime_probe/%s/probe_config.json' % model_prefix
    ret.generated_file_contents[
        probe_config_pathname] = probe_config.DumpToString()

  hw_verification_spec.component_infos.sort(
      key=lambda ci: (ci.component_category, ci.component_uuid))

  # Append the whitelists in the verification spec.
  for ps_info in _GetAllGenericProbeStatementInfoRecords():
    hw_verification_spec.generic_component_value_whitelists.add(
        component_category=ProbeRequestSupportCategory.Value(
            ps_info.probe_category),
        field_names=ps_info.whitelist_fields)

  ret.generated_file_contents[
      'hw_verification_spec.prototxt'] = text_format.MessageToString(
          hw_verification_spec)

  return ret


def main():
  # only import the required modules while running this module as a program
  import argparse
  import logging
  import os
  import sys

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
  ap.add_argument('--no_verify_checksum', action='store_false',
                  help="Don't verify the checksum in the HWID databases.",
                  dest='verify_checksum')
  ap.add_argument('--waived_comp_category', nargs='*', default=[],
                  dest='waived_categories',
                  help=('Waived component category, must specify in format of '
                        '`<model_name>.<category_name>`.'))
  args = ap.parse_args()

  logging.basicConfig(level=logging.INFO)

  dbs = []
  for hwid_db_path in args.hwid_db_paths:
    logging.info('Load the HWID database file (%s).', hwid_db_path)
    dbs.append((database.Database.LoadFile(
        hwid_db_path, verify_checksum=args.verify_checksum), []))
  for waived_category in args.waived_categories:
    model_name, unused_sep, category_name = waived_category.partition('.')
    for db_obj, waived_list in dbs:
      if db_obj.project.lower() == model_name.lower():
        logging.info('Will ignore the componente category %r for %r.',
                     category_name, db_obj.project)
        waived_list.append(category_name)

  logging.info('Generate the verification payload data.')
  result = GenerateVerificationPayload(dbs)

  for error_msg in result.error_msgs:
    logging.error(error_msg)
    sys.exit(1)

  if not result.error_msgs:
    for pathname, content in result.generated_file_contents.items():
      logging.info('Output the verification payload file (%s).', pathname)
      fullpath = os.path.join(args.output_dir, pathname)
      file_utils.TryMakeDirs(os.path.dirname(fullpath))
      file_utils.WriteFile(fullpath, content)


if __name__ == '__main__':
  main()
