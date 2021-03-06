#!/usr/bin/env python3
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Command-line interface for HWID v3 utilities."""

import hashlib
import logging
import os
import shutil
import sys
from typing import Dict, NamedTuple

from cros.factory.hwid.v3 import builder
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import converter
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.test.rules import phase
from cros.factory.utils.argparse_utils import CmdArg
from cros.factory.utils.argparse_utils import Command
from cros.factory.utils.argparse_utils import ParseCmdline
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils


_COMMON_ARGS = [
    CmdArg('-p', '--hwid-db-path', default=None,
           help='path to the HWID database directory'),
    CmdArg(
        '-j', '--project', default=None, dest='project',
        help=('name of the HWID database to load/build.\n'
              '(required if not running on a DUT)')),
    CmdArg('-v', '--verbose', default=False, action='store_true',
           help='enable verbose output'),
    CmdArg('--no-verify-checksum', default=False, action='store_true',
           help='do not check database checksum'),
    CmdArg(
        '--phase', default=None,
        help=('override phase for phase checking (defaults to the current '
              'as returned by the "factory phase" command)')),
]

_OUTPUT_FORMAT_COMMON_ARGS = [
    CmdArg('--json-output', default=False, action='store_true',
           help='Whether to dump result in JSON format.'),
]

_DATABASE_BUILDER_COMMON_ARGS = [
    CmdArg('--add-default-component', default=None, nargs='+', metavar='COMP',
           dest='add_default_comp',
           help='Component classes that add a default item.\n'),
    CmdArg('--add-null-component', default=None, nargs='+', metavar='COMP',
           dest='add_null_comp',
           help='Component classes that add a null item.\n'),
    CmdArg('--add-region', default=None, nargs='+', metavar='REGION',
           dest='add_regions', help='The new regions to be added.'),
    CmdArg('--region-field-name', default='region_field',
           help="Name of region field. (defaults to \"%(default)s\")"),
]

_HWID_MATERIAL_FIELD_COMMON_ARGS = [
    CmdArg(
        '--device-info-file', default=None,
        help=('A file with device info.  Example content of this file:\n'
              '    component.antenna: ACN\n'
              '    component.has_cellular: True\n'
              '    component.keyboard: US_API\n')),
    CmdArg(
        '--run-vpd', action='store_true',
        help=('Obtain the vpd data from the device before generating '
              'the HWID string.  Also see --vpd-data-file for more '
              'information.')),
    CmdArg(
        '--vpd-data-file', type=str, default=None,
        help=('Obtain the vpd data by reading the specified '
              'json-formatted file before generating the HWID string.  '
              'If some rules in the HWID database need VPD values, '
              'either --run-vpd or --vpd-data-file should be '
              'specified.')),
]

_HWID_MATERIAL_COMMON_ARGS = [
    CmdArg(
        '--material-file', default=None,
        help=('A file contains the materials for HWID generation and DB '
              'update.')),
    # TODO(b/188488068): Stop supporting --probed-results-file.
    CmdArg('--probed-results-file', default=None,
           help='(Deprecated!)  Used to specify a file with probed results.'),
] + _HWID_MATERIAL_FIELD_COMMON_ARGS

_RMA_COMMON_ARGS = [
    CmdArg('--rma-mode', default=False, action='store_true',
           help='Whether to enable RMA mode.'),
]


class Arg:
  """A simple class to store arguments passed to the add_argument method of
  argparse module.
  """

  def __init__(self, *args, **kwargs):
    self.args = args
    self.kwargs = kwargs


def GetHWIDString():
  return process_utils.CheckOutput(['gooftool', 'read_hwid']).strip()


def Output(msg):
  print(msg)


def OutputObject(options, obj):
  if options.json_output:
    Output(json_utils.DumpStr(obj, pretty=True))
  else:
    Output(yaml.safe_dump(obj, default_flow_style=False))


class HWIDMaterial(NamedTuple):
  """A placeholder for materials to generate HWID string / build HWID DB."""
  probed_results: Dict  # An object records the probed results.
  device_info: Dict  # An object records the device info.
  vpd: Dict  # An object records the vpd data.
  framework_version: int

  def DumpStr(self):
    return yaml.dump(self.ConvertToDict())

  @classmethod
  def LoadStr(cls, source):
    yaml_obj = yaml.load(source)
    yaml_obj.setdefault('framework_version', common.OLDEST_FRAMEWORK_VERSION)
    return cls(**yaml_obj)

  def ConvertToDict(self):
    return self._asdict()


def ObtainHWIDMaterial(options):
  """Gets all material needed by the HWID framework according to options.

  Args:
    options: The given options.

  Returns:
    An instance of `HWIDMaterial`.

  Raises:
    ValueError if the given options is invalid.
  """
  if options.run_vpd and options.vpd_data_file:
    raise ValueError('The arguments --run-vpd and --vpd-data-file cannot be '
                     'set at the same time')

  base_hwid_material_file = getattr(options, 'material_file', None)
  probed_results_file = getattr(options, 'probed_results_file', None)

  if sys_utils.InCrOSDevice() or base_hwid_material_file:
    if probed_results_file:
      raise ValueError('`--probed_results_file` is deprecated.')

  else:
    # Host (chroot) environment is often easier to be upgraded.  Hence, there
    # might be a chance that the source code version of the toolkit on DUT is
    # behind the ToT.  Therefore, we want to keep supporting the legacy usage
    # in short-term.
    # TODO(b/188488068): Remove this backward support.
    if not options.device_info_file:
      raise ValueError('Please specify the HWID material by `--material-file` '
                       'if `hwid collect-material` is available. '
                       'Otherwise, please use `--device-info-file` to specify '
                       'the device info while running in chroot.')

    if not probed_results_file:
      raise ValueError('Please specify the HWID material by `--material-file` '
                       'if `hwid collect-material` is available. '
                       'Otherwise, please use `--probed-results-file` to '
                       'specify the probed results while running in chroot.')
    # Carefully examine if the payload is actually the output of `hwid probe`.
    contents = file_utils.ReadFile(probed_results_file)
    # YAML is a superset of JSON, so loading the contents with YAML parser
    # is always fine.
    yaml_blob = yaml.safe_load(contents)
    if set(yaml_blob).issubset(set(HWIDMaterial._fields)):
      raise ValueError(
          'The file you passed seems like an output of '
          '`hwid collect-material`, please use `--material-file` instead.')

    if options.run_vpd:
      raise ValueError('Cannot run `vpd` tool in chroot.')

  if base_hwid_material_file:
    kwargs = HWIDMaterial.LoadStr(
        file_utils.ReadFile(base_hwid_material_file)).ConvertToDict()
  else:
    kwargs = {
        'framework_version': (
            common.FRAMEWORK_VERSION
            if sys_utils.InCrOSDevice() else common.OLDEST_FRAMEWORK_VERSION)
    }

  if base_hwid_material_file is None or probed_results_file:
    kwargs['probed_results'] = hwid_utils.GetProbedResults(
        infile=probed_results_file, project=options.project)
  if base_hwid_material_file is None or options.device_info_file:
    kwargs['device_info'] = hwid_utils.GetDeviceInfo(
        infile=options.device_info_file)
  if (base_hwid_material_file is None or options.run_vpd or
      options.vpd_data_file):
    kwargs['vpd'] = hwid_utils.GetVPDData(run_vpd=options.run_vpd,
                                          infile=options.vpd_data_file)

  hwid_material = HWIDMaterial(**kwargs)
  logging.debug(hwid_material.DumpStr())
  return hwid_material


# TODO(b/188488068): Remove this legacy command.
@Command('probe',
         CmdArg('--output-file', default='-',
                help='File name to store the probed results'),
         doc='(Deprecated!)  Probes components on the DUT.')
def ProbeCommand(options):
  raise RuntimeError(
      'This command is deprecated by `collect-material`. Please run '
      '`hwid collect-material ...` with the same arguments instead!')


@Command('collect-material',
         CmdArg('--output-file', default='-',
                help='File name to store the collected data.'),
         *_HWID_MATERIAL_FIELD_COMMON_ARGS)
def CollectDeviceMaterialCommand(options):
  """Collects all sorts of material for HWID encoding and DB update."""
  if not sys_utils.InCrOSDevice():
    raise RuntimeError('This command must be run on DUT.')
  hwid_material = ObtainHWIDMaterial(options)
  if options.output_file == '-':
    Output(hwid_material.DumpStr())
  else:
    file_utils.WriteFile(options.output_file, hwid_material.DumpStr())


def RunDatabaseBuilder(database_builder, options):
  if options.add_default_comp:
    for comp_cls in options.add_default_comp:
      database_builder.AddDefaultComponent(comp_cls)
  if options.add_null_comp:
    for comp_cls in options.add_null_comp:
      database_builder.AddNullComponent(comp_cls)
  if options.add_regions:
    database_builder.AddRegions(options.add_regions, options.region_field_name)

  hwid_material = ObtainHWIDMaterial(options)

  database_builder.UprevFrameworkVersion(hwid_material.framework_version)

  database_builder.UpdateByProbedResults(
      hwid_material.probed_results, hwid_material.device_info,
      hwid_material.vpd, image_name=options.image_id)


@Command('build-database',
         CmdArg('--image-id', default='EVT',
                help="Name of image_id. Default is 'EVT'\n"),
         *_HWID_MATERIAL_COMMON_ARGS, *_DATABASE_BUILDER_COMMON_ARGS)
def BuildDatabaseWrapper(options):
  '''Build the HWID database from probed result.'''
  if not os.path.isdir(options.hwid_db_path):
    logging.info('%s is not a directory.  Creating...', options.hwid_db_path)
    file_utils.TryMakeDirs(options.hwid_db_path)
  database_path = os.path.join(options.hwid_db_path, options.project.upper())

  database_builder = builder.DatabaseBuilder(project=options.project,
                                             image_name=options.image_id)
  RunDatabaseBuilder(database_builder, options)
  database_builder.Render(database_path)

  logging.info('Output the database to %s', database_path)


@Command('update-database',
         CmdArg('--image-id', default=None, help="Name of image_id.\n"),
         CmdArg('--output-database', default=None,
                help='Write into different file.\n'),
         *_HWID_MATERIAL_COMMON_ARGS, *_DATABASE_BUILDER_COMMON_ARGS)
def UpdateDatabaseWrapper(options):
  '''Update the HWID database from probed result.'''
  old_db_path = os.path.join(options.hwid_db_path, options.project.upper())
  if options.output_database is None:
    # If the output path is not assigned, we update the database in place.
    # We backup the original database before update.
    bak_db_path = old_db_path + '.bak'
    logging.info('In-place update, backup the database to %s', bak_db_path)
    shutil.copyfile(old_db_path, bak_db_path)

  database_path = options.output_database or old_db_path

  database_builder = builder.DatabaseBuilder(database_path=old_db_path)
  RunDatabaseBuilder(database_builder, options)
  database_builder.Render(database_path)

  logging.info('Output the updated database to %s.', database_path)


@Command(
    'generate',
    CmdArg(
        '--allow-mismatched-components', action='store_true',
        help='Allows some probed components to be ignored if no any '
        'component in the database matches with them.'),
    CmdArg('--use-name-match', action='store_true',
           help='Use component name from probed results as matched component.'),
    CmdArg('--with-configless-fields', action='store_true',
           help='Include the configless field.'),
    CmdArg('--brand-code', default=None,
           help='Device brand code (cros_config / brand-code).'),
    CmdArg('--no-brand-code', action='store_true',
           help='Do not add brand code to HWID'), *_HWID_MATERIAL_COMMON_ARGS,
    *_OUTPUT_FORMAT_COMMON_ARGS, *_RMA_COMMON_ARGS)
def GenerateHWIDWrapper(options):
  """Generates HWID."""
  hwid_material = ObtainHWIDMaterial(options)

  identity = hwid_utils.GenerateHWID(
      options.database, hwid_material.probed_results, hwid_material.device_info,
      hwid_material.vpd, options.rma_mode, options.with_configless_fields,
      options.brand_code,
      allow_mismatched_components=options.allow_mismatched_components,
      use_name_match=options.use_name_match)

  OutputObject(
      options, {
          'encoded_string': identity.encoded_string,
          'binary_string': identity.binary_string,
          'database_checksum': options.database.checksum
      })


@Command('decode',
         CmdArg('hwid', nargs='?', default=None,
                help='the HWID to decode.\n(required if not running on a DUT)'),
         *_OUTPUT_FORMAT_COMMON_ARGS)
def DecodeHWIDWrapper(options):
  """Decodes HWID."""
  encoded_string = options.hwid if options.hwid else GetHWIDString()
  identity, bom, configless = hwid_utils.DecodeHWID(options.database,
                                                    encoded_string)

  OutputObject(
      options, {
          'project': identity.project,
          'binary_string': identity.binary_string,
          'image_id': bom.image_id,
          'components': bom.components,
          'brand_code': identity.brand_code,
          'configless': configless
      })


@Command('verify',
         CmdArg('hwid', nargs='?', default=None,
                help='the HWID to verify.\n(required if not running on a DUT)'),
         CmdArg(
             '--allow-mismatched-components', action='store_true',
             help='Allows some probed components to be ignored if no any '
             'component in the database matches with them.'),
         *_HWID_MATERIAL_COMMON_ARGS, *_RMA_COMMON_ARGS)
def VerifyHWIDWrapper(options):
  """Verifies HWID."""
  encoded_string = options.hwid if options.hwid else GetHWIDString()

  hwid_material = ObtainHWIDMaterial(options)

  hwid_utils.VerifyHWID(
      options.database, encoded_string, hwid_material.probed_results,
      hwid_material.device_info, hwid_material.vpd, options.rma_mode,
      current_phase=options.phase,
      allow_mismatched_components=options.allow_mismatched_components)

  # No exception raised. Verification was successful.
  Output('Verification passed.')


@Command('write', CmdArg('hwid', help='the encoded HWID string to write'))
def WriteHWIDWrapper(options):
  """Writes HWID to firmware GBB."""
  if sys_utils.InChroot():
    raise ValueError('Cannot write HWID to GBB in chroot.')

  process_utils.CheckOutput(['gooftool', 'write_hwid', options.hwid])
  Output('HWID %r written to firmware GBB.' % options.hwid)


@Command('read')
def ReadHWIDWrapper(unused_options):
  """Reads HWID from firmware GBB."""
  if sys_utils.InChroot():
    raise ValueError('Cannot read HWID from GBB in chroot.')

  Output(GetHWIDString())


@Command('list-components',
         CmdArg('comp_class', nargs='*', default=None,
                help='the component classes to look up'),
         *_OUTPUT_FORMAT_COMMON_ARGS)
def ListComponentsWrapper(options):
  """Lists components of the given class."""
  components_list = hwid_utils.ListComponents(options.database,
                                              options.comp_class)
  OutputObject(options, components_list)


@Command('enumerate-hwid',
         CmdArg('-i', '--image_id', default=None,
                help='the image ID to enumerate.'),
         CmdArg('-s', '--status', default='supported',
                choices=['supported', 'released',
                         'all'], help='the status of components to enumerate'),
         CmdArg(
             '--comp', nargs='*', default=None,
             help=('Specify some of the component to limit the output.  '
                   'The format of COMP is '
                   '"<comp_cls>=<comp_name>[,<comp_name>[,<comp_name>...]]"')),
         CmdArg('--no-bom', action='store_true',
                help='Print the encoded string only.'),
         CmdArg('--brand-code', default=None, help='The brand code.'))
def EnumerateHWIDWrapper(options):
  """Enumerates possible HWIDs."""
  comps = {}
  if options.comp:
    for comp in options.comp:
      if '=' not in comp:
        raise ValueError('The format of the --comp argument is incorrect.')
      comp_cls, _, comp_names = comp.partition('=')
      comps[comp_cls] = comp_names.split(',')

  # Enumerating may take a very long time so we want to verbosely make logs.
  logging.debug('Enumerating all HWIDs...')
  if options.image_id:
    image_id = options.database.GetImageIdByName(options.image_id)
  else:
    image_id = None
  hwids = hwid_utils.EnumerateHWID(options.database, image_id=image_id,
                                   status=options.status, comps=comps,
                                   brand_code=options.brand_code)

  logging.debug('Printing %d sorted HWIDs...', len(hwids))
  if options.no_bom:
    for k in sorted(hwids):
      Output(k)
  else:
    for k, v in sorted(hwids.items()):
      Output('%s: %s' % (k, v))


@Command('verify-database')
def VerifyHWIDDatabase(options):
  """Verifies the given HWID database."""
  # Do nothing here since all the verifications are done when loading the
  # database with HWID library.
  if options.database.can_encode:
    Output('Database %s verified' % options.project)
  else:
    Output('Database %s (not works for encoding) verified' % options.project)


@Command(
    'converter',
    CmdArg('--output-file', default='-',
           help='File name to store the converted results'),
    CmdArg('--output-checksum-file', default=None,
           help='File name to store the checksum of the converted results'))
def ConverterCommand(options):
  """Convert the default probe statements to project specific statements."""
  probe_statement_path = hwid_utils.GetProbeStatementPath(options.project)
  converted_results_obj = converter.ConvertToProbeStatement(
      options.database, probe_statement_path)
  converted_results_data = json_utils.DumpStr(converted_results_obj,
                                              pretty=True)
  if options.output_file == '-':
    Output(converted_results_data)
  else:
    file_utils.WriteFile(options.output_file, converted_results_data)
  if options.output_checksum_file:
    checksum = hashlib.sha1(converted_results_data.encode('utf-8')).hexdigest()
    file_utils.WriteFile(options.output_checksum_file, checksum)


def ParseOptions(args=None):
  """Parse arguments and generate necessary options."""
  return ParseCmdline('HWID command-line utilities', *_COMMON_ARGS,
                      args_to_parse=args)


def InitializeDefaultOptions(options):
  if not options.hwid_db_path:
    options.hwid_db_path = hwid_utils.GetDefaultDataPath()
  if options.project is None:
    if sys_utils.InChroot():
      Output('Argument -j/--project is required')
      sys.exit(1)
    options.project = hwid_utils.ProbeProject()

  # Build database doesn't need to initialize the database.
  if options.command_name in ('probe', 'collect-material', 'build-database'):
    return

  # Create the Database object here since it's common to all functions.
  logging.debug('Loading database file %s/%s...', options.hwid_db_path,
                options.project.upper())
  options.database = Database.LoadFile(
      os.path.join(options.hwid_db_path, options.project.upper()),
      verify_checksum=(not options.no_verify_checksum))

  phase.OverridePhase(options.phase)

  if options.command_name == 'generate':
    if options.no_brand_code:
      if options.brand_code:
        sys.exit('--no-brand-code and --brand-code are mutually exclusive')
    else:
      options.brand_code = hwid_utils.GetBrandCode(options.brand_code)


def Main():
  """Parses options, sets up logging, and runs the given subcommand."""
  options = ParseOptions()
  if options.verbose:
    logging.basicConfig(level=logging.DEBUG)
  else:
    logging.basicConfig(level=logging.INFO)

  InitializeDefaultOptions(options)

  logging.debug('Perform command <%s>.. ', options.command_name)
  options.command(options)


if __name__ == '__main__':
  Main()
