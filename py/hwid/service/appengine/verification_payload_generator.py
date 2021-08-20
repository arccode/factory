#!/usr/bin/env python3
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Methods to generate the verification payload from the HWID database."""

import collections
import functools
import hashlib
import re
import typing

# pylint: disable=import-error, no-name-in-module
from google.protobuf import text_format
import hardware_verifier_pb2
import runtime_probe_pb2

from cros.factory.hwid.v3 import common as hwid_common
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import rule as hwid_rule
from cros.factory.probe.runtime_probe import probe_config_definition
from cros.factory.probe.runtime_probe import probe_config_types
from cros.factory.utils import json_utils
from cros.factory.utils import type_utils


class GenericProbeStatementInfoRecord:
  """Placeholder for info. related to the generic probe statement.

  Attributes:
    probe_category: The name of the probe category.
    probe_func_name: The name of the probe function.
    allowlist_fields: A dictionary which keys are the allowed fields in the
        output while the corresponding value can be `None` or some value for
        filtering unwanted generic probed result.  Type of the values must
        match the definition declared in
        `cros.factory.probe.runtime_probe.probe_config_definitions` because
        they will be fed to the probe statement generator.
  """

  def __init__(self, probe_category, probe_func_name, allowlist_fields):
    """Constructor.

    Args:
      probe_category: The name of the probe category.
      probe_func_name: The name of the probe function.
      allowlist_fields: Either a list of allowed fields in the output or
          a dictionary of allowed fields with values for filtering.
    """
    self.probe_category = probe_category
    self.probe_func_name = probe_func_name
    self.allowlist_fields = (
        allowlist_fields if isinstance(allowlist_fields, dict) else
        {fn: None
         for fn in allowlist_fields})

  def GenerateProbeStatement(self):
    return probe_config_definition.GetProbeStatementDefinition(
        self.probe_category).GenerateProbeStatement(
            'generic', self.probe_func_name, self.allowlist_fields)


# TODO(yhong): Remove the expect field when runtime_probe converts the output
#              format automatically (b/133641904).
@type_utils.CachedGetter
def _GetAllGenericProbeStatementInfoRecords():
  return [
      GenericProbeStatementInfoRecord(
          'battery', 'generic_battery',
          ['manufacturer', 'model_name', 'technology']),
      GenericProbeStatementInfoRecord('storage', 'generic_storage', [
          'type', 'sectors', 'mmc_hwrev', 'mmc_manfid', 'mmc_name', 'mmc_oemid',
          'mmc_prv', 'mmc_serial', 'pci_vendor', 'pci_device', 'pci_class',
          'nvme_model', 'ata_vendor', 'ata_model'
      ]),
      GenericProbeStatementInfoRecord('cellular', 'cellular_network', [
          'bus_type', 'pci_vendor_id', 'pci_device_id', 'pci_revision',
          'pci_subsystem', 'usb_vendor_id', 'usb_product_id', 'usb_bcd_device'
      ]),
      GenericProbeStatementInfoRecord('ethernet', 'ethernet_network', [
          'bus_type', 'pci_vendor_id', 'pci_device_id', 'pci_revision',
          'pci_subsystem', 'usb_vendor_id', 'usb_product_id', 'usb_bcd_device'
      ]),
      GenericProbeStatementInfoRecord('wireless', 'wireless_network', [
          'bus_type', 'pci_vendor_id', 'pci_device_id', 'pci_revision',
          'pci_subsystem', 'usb_vendor_id', 'usb_product_id', 'usb_bcd_device',
          'sdio_vendor_id', 'sdio_device_id'
      ]),
      GenericProbeStatementInfoRecord('dram', 'memory',
                                      ['part', 'size', 'slot']),
      # TODO(yhong): Include other type of cameras if needed.
      GenericProbeStatementInfoRecord(
          'camera', 'usb_camera', {
              'bus_type': None,
              'usb_vendor_id': None,
              'usb_product_id': None,
              'usb_bcd_device': None,
              'usb_removable': re.compile('^(FIXED|UNKNOWN)$'),
          }),
      GenericProbeStatementInfoRecord(
          'display_panel', 'edid', ['height', 'product_id', 'vendor', 'width']),
  ]


class _FieldRecord:

  def __init__(self, hwid_field_names, probe_statement_field_name,
               value_converters, is_optional=False):
    if not isinstance(hwid_field_names, list):
      hwid_field_names = [hwid_field_names]
    self.hwid_field_names = hwid_field_names
    self.probe_statement_field_name = probe_statement_field_name
    self.value_converters = type_utils.MakeList(value_converters)
    self.is_optional = is_optional


class MissingComponentValueError(Exception):
  """Some required component values is missing so that they should not be
  converted by this generator."""


class ProbeStatementConversionError(Exception):
  """The given component values is consider invalid so that it cannot be
  converted by this generator."""


class _ProbeStatementGenerator:

  def __init__(self, probe_category, probe_function_name, field_converters,
               probe_function_argument=None):
    self.probe_category = probe_category

    self._probe_statement_generator = (
        probe_config_definition.GetProbeStatementDefinition(probe_category))
    self._probe_function_name = probe_function_name
    if field_converters and isinstance(field_converters[0], _FieldRecord):
      self._field_converters = [field_converters]
    else:
      self._field_converters = field_converters
    self._probe_function_argument = probe_function_argument

  def TryGenerate(self, comp_name, comp_values, information=None):

    def GenerateExpectedFields(field_converters):
      expected_fields = {}

      # Extract the fields for probe statement from the component values.
      # If any of the required field is missing, raise the case.
      converters = collections.defaultdict(list)
      optional_converters = []
      for fc in field_converters:
        found_hwid_field_names = [
            name for name in fc.hwid_field_names if name in comp_values
        ]
        if not found_hwid_field_names:
          if fc.is_optional:
            optional_converters.append(fc)
            continue
          raise MissingComponentValueError(
              'missing component value field(s) for field %r : %r' %
              (fc.probe_statement_field_name, fc.hwid_field_names))
        if len(found_hwid_field_names) > 1:
          found_hwid_vals = [
              comp_values[name] for name in found_hwid_field_names
          ]
          if found_hwid_vals.count(found_hwid_vals[0]) != len(found_hwid_vals):
            raise ProbeStatementConversionError(
                'found multiple valid component value fields for field %r : %r)'
                % (fc.probe_statement_field_name, found_hwid_field_names))
        converters[found_hwid_field_names[0]].append(fc)

      # Convert the format of each fields for the probe statement.  Raises the
      # error if it fails.
      for hwid_field_name, fcs in converters.items():
        for fc in fcs:
          expected_field = None
          for value_converter in fc.value_converters:
            try:
              expected_field = value_converter(comp_values[hwid_field_name])
              break
            except Exception as e:
              err = e
          if expected_field is None:
            raise ProbeStatementConversionError(
                'unable to convert the value of field %r to %r: %r' %
                (hwid_field_name, fc.probe_statement_field_name, err))
          if expected_fields.setdefault(fc.probe_statement_field_name,
                                        expected_field) != expected_field:
            raise ProbeStatementConversionError(
                'found multiple valid component value fields for field %r' %
                fc.probe_statement_field_name)
      for fc in optional_converters:
        expected_fields.setdefault(fc.probe_statement_field_name)

      return expected_fields

    expected_fields = []

    try:
      expected_fields = list(
          map(GenerateExpectedFields, self._field_converters))
    except Exception as e:
      err = e
    if not expected_fields:
      raise err

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

  storage_shared_fields = [same_name_field_converter('sectors', StrToNum)]
  all_probe_statement_generators['storage'] = [
      # eMMC
      _ProbeStatementGenerator(
          'storage', 'generic_storage', storage_shared_fields + [
              _FieldRecord(['hwrev', 'mmc_hwrev'], 'mmc_hwrev',
                           GetHWIDHexStrToHexStrConverter(1), is_optional=True),
              _FieldRecord(['name', 'mmc_name'], 'mmc_name',
                           SimplyForwardValue),
              _FieldRecord(['manfid', 'mmc_manfid'], 'mmc_manfid',
                           GetHWIDHexStrToHexStrConverter(2)),
              _FieldRecord(['oemid', 'mmc_oemid'], 'mmc_oemid',
                           GetHWIDHexStrToHexStrConverter(4)),
              _FieldRecord(['prv', 'mmc_prv'], 'mmc_prv',
                           GetHWIDHexStrToHexStrConverter(2), is_optional=True),
              _FieldRecord(['serial', 'mmc_serial'], 'mmc_serial',
                           GetHWIDHexStrToHexStrConverter(8), is_optional=True),
          ]),
      # NVMe
      _ProbeStatementGenerator(
          'storage', 'generic_storage', storage_shared_fields + [
              _FieldRecord(['vendor', 'pci_vendor'], 'pci_vendor',
                           GetHWIDHexStrToHexStrConverter(4)),
              _FieldRecord(['device', 'pci_device'], 'pci_device',
                           GetHWIDHexStrToHexStrConverter(4)),
              _FieldRecord(['class', 'pci_class'], 'pci_class',
                           GetHWIDHexStrToHexStrConverter(6)),
              same_name_field_converter('nvme_model', HWIDValueToStr,
                                        is_optional=True),
          ]),
      # ATA
      _ProbeStatementGenerator(
          'storage', 'generic_storage', storage_shared_fields + [
              _FieldRecord(['vendor', 'ata_vendor'], 'ata_vendor',
                           HWIDValueToStr),
              _FieldRecord(['model', 'ata_model'], 'ata_model', HWIDValueToStr),
          ]),
  ]

  # TODO(yhong): Also convert SDIO network component probe statements.
  network_pci_fields = [
      _FieldRecord('vendor', 'pci_vendor_id',
                   GetHWIDHexStrToHexStrConverter(4)),
      # TODO(yhong): Set `pci_device_id` to non optional field when b/150914933
      #     is resolved.
      _FieldRecord('device', 'pci_device_id', GetHWIDHexStrToHexStrConverter(4),
                   is_optional=True),
      _FieldRecord('revision_id', 'pci_revision',
                   GetHWIDHexStrToHexStrConverter(2), is_optional=True),
      _FieldRecord('subsystem_device', 'pci_subsystem',
                   GetHWIDHexStrToHexStrConverter(4), is_optional=True),
  ]
  network_sdio_fields = [
      _FieldRecord('vendor', 'sdio_vendor_id',
                   GetHWIDHexStrToHexStrConverter(4)),
      _FieldRecord('device', 'sdio_device_id',
                   GetHWIDHexStrToHexStrConverter(4)),
  ]
  usb_fields = [
      _FieldRecord('idVendor', 'usb_vendor_id',
                   GetHWIDHexStrToHexStrConverter(4, has_prefix=False)),
      _FieldRecord('idProduct', 'usb_product_id',
                   GetHWIDHexStrToHexStrConverter(4, has_prefix=False)),
      _FieldRecord('bcdDevice', 'usb_bcd_device',
                   GetHWIDHexStrToHexStrConverter(4, has_prefix=False),
                   is_optional=True),
  ]
  all_probe_statement_generators['cellular'] = [
      _ProbeStatementGenerator('cellular', 'cellular_network',
                               network_pci_fields),
      _ProbeStatementGenerator('cellular', 'cellular_network', usb_fields),
  ]
  all_probe_statement_generators['ethernet'] = [
      _ProbeStatementGenerator('ethernet', 'ethernet_network',
                               network_pci_fields),
      _ProbeStatementGenerator('ethernet', 'ethernet_network', usb_fields),
  ]
  all_probe_statement_generators['wireless'] = [
      _ProbeStatementGenerator('wireless', 'wireless_network',
                               [network_pci_fields, network_sdio_fields]),
      _ProbeStatementGenerator('wireless', 'wireless_network', usb_fields),
  ]

  dram_fields = [
      same_name_field_converter('part', HWIDValueToStr),
      same_name_field_converter('size', StrToNum),
      same_name_field_converter('slot', StrToNum, is_optional=True),
  ]
  all_probe_statement_generators['dram'] = [
      _ProbeStatementGenerator('dram', 'memory', dram_fields),
  ]

  # TODO(kevinptt): Support "device_type" argument in runtime_probe.
  input_device_fields = [
      same_name_field_converter('name', HWIDValueToStr),
      _FieldRecord(
          ['hw_version', 'product'],
          'product',
          [
              GetHWIDHexStrToHexStrConverter(4, has_prefix=False),
              # raydium_ts
              GetHWIDHexStrToHexStrConverter(8, has_prefix=True),
          ]),
      same_name_field_converter(
          'vendor', GetHWIDHexStrToHexStrConverter(4, has_prefix=False),
          is_optional=True),
  ]
  all_probe_statement_generators['stylus'] = [
      _ProbeStatementGenerator('stylus', 'input_device', input_device_fields),
  ]
  all_probe_statement_generators['touchpad'] = [
      _ProbeStatementGenerator('touchpad', 'input_device', input_device_fields),
  ]
  all_probe_statement_generators['touchscreen'] = [
      _ProbeStatementGenerator('touchscreen', 'input_device',
                               input_device_fields),
  ]

  # This is the old name for video_codec + camera.
  all_probe_statement_generators['video'] = [
      _ProbeStatementGenerator('camera', 'usb_camera', usb_fields),
  ]
  all_probe_statement_generators['camera'] = [
      _ProbeStatementGenerator('camera', 'usb_camera', usb_fields),
  ]

  display_panel_fields = [
      same_name_field_converter('height', StrToNum),
      same_name_field_converter(
          'product_id', GetHWIDHexStrToHexStrConverter(4, has_prefix=False)),
      same_name_field_converter('vendor', HWIDValueToStr),
      same_name_field_converter('width', StrToNum),
  ]
  all_probe_statement_generators['display_panel'] = [
      _ProbeStatementGenerator('display_panel', 'edid', display_panel_fields),
  ]

  return all_probe_statement_generators


class VerificationPayloadGenerationResult(typing.NamedTuple):
  """
  Attributes:
    generated_file_contents: A string-to-string dictionary which represents the
        files that should be committed into the bsp package.
    error_msgs: A list of errors encountered during the generation.
    payload_hash: Hash of the payload.
    primary_identifiers: An instance of collections.defaultdict(dict) mapping
        `model` to {(category, component name): target component name} which
        groups components with same probe statement.
  """
  generated_file_contents: dict
  error_msgs: list
  payload_hash: str
  primary_identifiers: typing.DefaultDict[str, typing.Dict]


ComponentVerificationPayloadPiece = collections.namedtuple(
    'ComponentVerificationPayloadPiece',
    ['is_duplicate', 'error_msg', 'probe_statement', 'component_info'])

_STATUS_MAP = {
    hwid_common.COMPONENT_STATUS.supported: hardware_verifier_pb2.QUALIFIED,
    hwid_common.COMPONENT_STATUS.unqualified: hardware_verifier_pb2.UNQUALIFIED,
    hwid_common.COMPONENT_STATUS.deprecated: hardware_verifier_pb2.REJECTED,
    hwid_common.COMPONENT_STATUS.unsupported: hardware_verifier_pb2.REJECTED,
}

_ProbeRequestSupportCategory = runtime_probe_pb2.ProbeRequest.SupportCategory


def GetAllComponentVerificationPayloadPieces(db, waived_categories):
  """Generates materials for verification payload from each components in HWID.

  This function goes over each component in HWID one-by-one, and attempts to
  derive the corresponding material for building up the final verification
  payload.

  Args:
    db: An instance of HWID database.
    waived_categories: A list of component categories to ignore.

  Returns:
    A dictionary that maps the HWID component to the corresponding material.
    The key is a pair of the component category and the component name.  The
    value is an instance of `ComponentVerificationPayloadPiece`.  Callers can
    also look up whether a specific component is in the returned dictionary
    to know whether that component is covered by this verification payload
    generator.
  """
  ret = {}

  model_prefix = db.project.lower()
  for hwid_comp_category, ps_gens in GetAllProbeStatementGenerators().items():
    if hwid_comp_category in waived_categories:
      continue
    comps = db.GetComponents(hwid_comp_category, include_default=False)
    for comp_name, comp_info in comps.items():
      unique_comp_name = model_prefix + '_' + comp_name

      error_msg = None
      all_suitable_generator_and_ps = []
      try:
        for ps_gen in ps_gens:
          try:
            ps = ps_gen.TryGenerate(unique_comp_name, comp_info.values,
                                    comp_info.information)
          except MissingComponentValueError:
            continue
          else:
            all_suitable_generator_and_ps.append((ps_gen, ps))
      except ProbeStatementConversionError as e:
        error_msg = ('Failed to generate the probe statement for component '
                     '%r: %r.' % (unique_comp_name, e))

      if not all_suitable_generator_and_ps and not error_msg:
        # Ignore this component if no any generator are suitable for it.
        continue

      if len(all_suitable_generator_and_ps) > 1:
        assert False, ("The code shouldn't reach here because we expect "
                       'only one generator can handle the given component '
                       'by design.')

      is_duplicate = comp_info.status == hwid_common.COMPONENT_STATUS.duplicate
      if is_duplicate or error_msg:
        probe_statement = None
        component_info = None
      else:
        ps_gen, probe_statement = all_suitable_generator_and_ps[0]
        component_info = hardware_verifier_pb2.ComponentInfo(
            component_category=_ProbeRequestSupportCategory.Value(
                ps_gen.probe_category), component_uuid=unique_comp_name,
            qualification_status=_STATUS_MAP[comp_info.status])
      ret[(hwid_comp_category, comp_name)] = ComponentVerificationPayloadPiece(
          is_duplicate, error_msg, probe_statement, component_info)
  return ret


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

  def _ComponentSortKey(comp_vp_piece):
    qual_status_preference = {
        hardware_verifier_pb2.QUALIFIED: 0,
        hardware_verifier_pb2.UNQUALIFIED: 1,
        hardware_verifier_pb2.REJECTED: 2,
    }
    return (qual_status_preference.get(
        comp_vp_piece.component_info.qualification_status,
        3), comp_vp_piece.probe_statement.component_name)

  def _StripModelPrefix(comp_name, model):
    """Strip the known model prefix in comp name."""

    model = model.lower()
    if not comp_name.startswith(model + '_'):
      raise ValueError(r'Component name {comp_name!r} does not start with'
                       r'"{model}_".')
    return comp_name.partition('_')[2]

  def _CollectPrimaryIdentifiers(grouped_comp_vp_piece_per_model,
                                 grouped_primary_comp_name_per_model):
    """Collect the mappings from grouped comp_vp_pieces.

    This function extracts the required fields (model, category, component name,
    and targeted component name) for deduplicating probe
    statements from ComponentVerificationPayloadPiece which contains unnecessary
    information.
    """

    primary_identifiers = collections.defaultdict(dict)
    for model, grouped_comp_vp_piece in grouped_comp_vp_piece_per_model.items():
      grouped_primary_comp_name = grouped_primary_comp_name_per_model[model]
      for hash_value, comp_vp_piece_list in grouped_comp_vp_piece.items():
        if len(comp_vp_piece_list) <= 1:
          continue
        primary_component_name = grouped_primary_comp_name[hash_value]
        for comp_vp_piece in comp_vp_piece_list:
          probe_statement = comp_vp_piece.probe_statement
          if probe_statement.component_name == primary_component_name:
            continue
          primary_identifiers[model][
              probe_statement.category_name,
              _StripModelPrefix(probe_statement
                                .component_name, model)] = _StripModelPrefix(
                                    primary_component_name, model)
    return primary_identifiers

  error_msgs = []
  generated_file_contents = {}

  grouped_comp_vp_piece_per_model = {}
  grouped_primary_comp_name_per_model = {}
  hw_verification_spec = hardware_verifier_pb2.HwVerificationSpec()
  for db, waived_categories in dbs:
    model_prefix = db.project.lower()
    probe_config = probe_config_types.ProbeConfigPayload()
    all_pieces = GetAllComponentVerificationPayloadPieces(db, waived_categories)
    grouped_comp_vp_piece = collections.defaultdict(list)
    grouped_primary_comp_name = {}
    for comp_vp_piece in all_pieces.values():
      if comp_vp_piece.is_duplicate:
        continue
      if comp_vp_piece.error_msg:
        error_msgs.append(comp_vp_piece.error_msg)
        continue
      grouped_comp_vp_piece[
          comp_vp_piece.probe_statement.statement_hash].append(comp_vp_piece)

    for hash_val, comp_vp_piece_list in grouped_comp_vp_piece.items():
      comp_vp_piece = min(comp_vp_piece_list, key=_ComponentSortKey)
      grouped_primary_comp_name[
          hash_val] = comp_vp_piece.probe_statement.component_name
      probe_config.AddComponentProbeStatement(comp_vp_piece.probe_statement)
      hw_verification_spec.component_infos.append(comp_vp_piece.component_info)

    # Append the generic probe statements.
    for ps_gen in _GetAllGenericProbeStatementInfoRecords():
      if ps_gen.probe_category not in waived_categories:
        probe_config.AddComponentProbeStatement(ps_gen.GenerateProbeStatement())

    probe_config_pathname = 'runtime_probe/%s/probe_config.json' % model_prefix
    generated_file_contents[probe_config_pathname] = probe_config.DumpToString()
    grouped_comp_vp_piece_per_model[db.project] = grouped_comp_vp_piece
    grouped_primary_comp_name_per_model[db.project] = grouped_primary_comp_name

  primary_identifiers = _CollectPrimaryIdentifiers(
      grouped_comp_vp_piece_per_model, grouped_primary_comp_name_per_model)

  hw_verification_spec.component_infos.sort(
      key=lambda ci: (ci.component_category, ci.component_uuid))

  # Append the allowlists in the verification spec.
  for ps_info in _GetAllGenericProbeStatementInfoRecords():
    hw_verification_spec.generic_component_value_allowlists.add(
        component_category=_ProbeRequestSupportCategory.Value(
            ps_info.probe_category), field_names=list(ps_info.allowlist_fields))

  generated_file_contents[
      'hw_verification_spec.prototxt'] = text_format.MessageToString(
          hw_verification_spec)
  payload_json = json_utils.DumpStr(generated_file_contents, sort_keys=True)
  payload_hash = hashlib.sha1(payload_json.encode('utf-8')).hexdigest()

  return VerificationPayloadGenerationResult(
      generated_file_contents, error_msgs, payload_hash, primary_identifiers)


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
  ap.add_argument(
      '-o', '--output_dir', metavar='PATH',
      help=('Base path to the output files. In most of the cases, '
            'it should be '
            'chromeos-base/racc-config-<BOARD>/files '
            'in a private overlay repository.'))
  ap.add_argument(
      'hwid_db_paths', metavar='HWID_DATABASE_PATH', nargs='+',
      help=('Paths to the input HWID databases. If the board '
            'has multiple models, users should specify all models '
            'at once.'))
  ap.add_argument('--no_verify_checksum', action='store_false',
                  help="Don't verify the checksum in the HWID databases.",
                  dest='verify_checksum')
  ap.add_argument(
      '--waived_comp_category', nargs='*', default=[], dest='waived_categories',
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
        logging.info('Will ignore the component category %r for %r.',
                     category_name, db_obj.project)
        waived_list.append(category_name)

  logging.info('Generate the verification payload data.')
  result = GenerateVerificationPayload(dbs)
  for model, mapping in result.primary_identifiers.items():
    logs = [f'Found duplicate probe statements for model {model}:']
    for (category, comp_name), primary_comp_name in mapping.items():
      logs.append(f'  {category}/{comp_name} will be mapped to '
                  f'{category}/{primary_comp_name}.')
    logging.info('\n'.join(logs))

  if result.error_msgs:
    for error_msg in result.error_msgs:
      logging.error(error_msg)
    sys.exit(1)

  for pathname, content in result.generated_file_contents.items():
    logging.info('Output the verification payload file (%s).', pathname)
    fullpath = os.path.join(args.output_dir, pathname)
    file_utils.TryMakeDirs(os.path.dirname(fullpath))
    file_utils.WriteFile(fullpath, content)
  logging.info('Payload hash: %s', result.payload_hash)


if __name__ == '__main__':
  main()
