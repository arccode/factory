#!/usr/bin/env python
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

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import builder
from cros.factory.hwid.v3 import converter
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3 import probe
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.test.rules import phase
from cros.factory.utils.argparse_utils import CmdArg
from cros.factory.utils.argparse_utils import Command
from cros.factory.utils.argparse_utils import ParseCmdline
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils


_COMMON_ARGS = [
    CmdArg('-p', '--hwid-db-path', default=None,
           help='path to the HWID database directory'),
    CmdArg('-j', '--project', default=None, dest='project',
           help=('name of the HWID database to load/build.\n'
                 '(required if not running on a DUT)')),
    CmdArg('-v', '--verbose', default=False, action='store_true',
           help='enable verbose output'),
    CmdArg('--no-verify-checksum', default=False, action='store_true',
           help='do not check database checksum'),
    CmdArg('--phase', default=None,
           help=('override phase for phase checking (defaults to the current '
                 'as returned by the "factory phase" command)')),
]

_OUTPUT_FORMAT_COMMON_ARGS = [
    CmdArg('--json-output', default=False, action='store_true',
           help='Whether to dump result in JSON format.'),
]

_DATABASE_BUILDER_COMMON_ARGS = [
    CmdArg('--add-default-component', default=None,
           nargs='+', metavar='COMP', dest='add_default_comp',
           help='Component classes that add a default item.\n'),
    CmdArg('--add-null-component', default=None,
           nargs='+', metavar='COMP', dest='add_null_comp',
           help='Component classes that add a null item.\n'),
]

_DEVICE_DATA_COMMON_ARGS = [
    CmdArg('--probed-results-file', default=None,
           help=('A file with probed results.\n'
                 '(Required if not running on a DUT.)')),
    CmdArg('--device-info-file', default=None,
           help=('A file with device info.\n'
                 '(Required if not running on a DUT.)\n'
                 'example content of this file:\n'
                 '    component.antenna: ACN\n'
                 '    component.has_cellular: True\n'
                 '    component.keyboard: US_API\n')),
    CmdArg('--run-vpd', action='store_true',
           help=('Obtain the vpd data from the device before generating '
                 'the HWID string.  Also see --vpd-data-file for more '
                 'information.')),
    CmdArg('--vpd-data-file', type=str, default=None,
           help=('Obtain the vpd data by reading the specified '
                 'json-formatted file before generating the HWID string.  '
                 'If some rules in the HWID database need VPD values, '
                 'either --run-vpd or --vpd-data-file should be '
                 'specified.')),
]

_RMA_COMMON_ARGS = [
    CmdArg('--rma-mode', default=False, action='store_true',
           help='Whether to enable RMA mode.'),
]


class Arg(object):
  """A simple class to store arguments passed to the add_argument method of
  argparse module.
  """

  def __init__(self, *args, **kwargs):
    self.args = args
    self.kwargs = kwargs


def GetHWIDString():
  return process_utils.CheckOutput(['gooftool', 'read_hwid']).strip()


def Output(msg):
  print msg


def OutputObject(options, obj):
  if options.json_output:
    Output(json_utils.DumpStr(obj, pretty=True))
  else:
    Output(yaml.safe_dump(obj, default_flow_style=False))


def ObtainAllDeviceData(options):
  """Gets all device data needed by the HWID framework according to options.

  Args:
    options: The given options.

  Returns:
    An instance of `type_utils.Obj` with attributes:
      probed_results: An object records the probed results.
      device_info: An object records the device info.
      vpd: An object records the vpd data.

  Raises:
    ValueError if the given options is invalid.
  """
  if sys_utils.InChroot():
    if not options.device_info_file:
      raise ValueError('Please specify device info with an input file when '
                       'running in chroot.')

    if not options.probed_results_file:
      raise ValueError('Please specify probed results with an input file when '
                       'running in chroot.')

    if options.run_vpd:
      raise ValueError('Cannot run `vpd` tool in chroot.')

  if options.run_vpd and options.vpd_data_file:
    raise ValueError('The arguments --run-vpd and --vpd-data-file cannot be '
                     'set at the same time')

  device_data = type_utils.Obj(
      probed_results=hwid_utils.GetProbedResults(
          infile=options.probed_results_file),
      device_info=hwid_utils.GetDeviceInfo(infile=options.device_info_file),
      vpd=hwid_utils.GetVPDData(run_vpd=options.run_vpd,
                                infile=options.vpd_data_file))

  logging.debug(yaml.dump(device_data.__dict__, default_flow_style=False))

  return device_data


@Command(
    'probe',
    CmdArg('--output-file', default='-',
           help='File name to store the probed results'))
def ProbeCommand(options):
  probed_results_data = json_utils.DumpStr(probe.ProbeDUT(), pretty=True)
  if options.output_file == '-':
    Output(probed_results_data)
  else:
    file_utils.WriteFile(options.output_file, probed_results_data)


def RunDatabaseBuilder(database_builder, options):
  if options.add_default_comp:
    for comp_cls in options.add_default_comp:
      database_builder.AddDefaultComponent(comp_cls)
  if options.add_null_comp:
    for comp_cls in options.add_null_comp:
      database_builder.AddNullComponent(comp_cls)

  device_data = ObtainAllDeviceData(options)

  database_builder.UpdateByProbedResults(
      device_data.probed_results, device_data.device_info, device_data.vpd,
      image_name=options.image_id)


@Command(
    'build-database',
    CmdArg('--image-id', default='EVT',
           help="Name of image_id. Default is 'EVT'\n"),
    *(_DEVICE_DATA_COMMON_ARGS + _DATABASE_BUILDER_COMMON_ARGS))
def BuildDatabaseWrapper(options):
  '''Build the HWID database from probed result.'''
  if not os.path.isdir(options.hwid_db_path):
    raise IOError('%s is not a directory.' % options.hwid_db_path)
  database_path = os.path.join(options.hwid_db_path, options.project.upper())

  database_builder = builder.DatabaseBuilder(project=options.project,
                                             image_name=options.image_id)
  RunDatabaseBuilder(database_builder, options)
  database_builder.Render(database_path)

  logging.info('Output the database to %s', database_path)


@Command(
    'update-database',
    CmdArg('--image-id', default=None,
           help="Name of image_id.\n"),
    CmdArg('--output-database', default=None,
           help='Write into different file.\n'),
    *(_DEVICE_DATA_COMMON_ARGS + _DATABASE_BUILDER_COMMON_ARGS))
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
    CmdArg('--allow-mismatched-components', action='store_true',
           help='Allows some probed components to be ignored if no any '
                'component in the database matches with them.'),
    CmdArg('--use-name-match', action='store_true',
           help='Use component name from probed results as matched component.'),
    CmdArg('--with-configless-fields', action='store_true',
           help='Include the configless field.'),
    CmdArg('--brand-code', default=None,
           help='Device brand code for configless format.'),
    *(_OUTPUT_FORMAT_COMMON_ARGS + _DEVICE_DATA_COMMON_ARGS + _RMA_COMMON_ARGS))
def GenerateHWIDWrapper(options):
  """Generates HWID."""
  device_data = ObtainAllDeviceData(options)

  identity = hwid_utils.GenerateHWID(
      options.database, device_data.probed_results, device_data.device_info,
      device_data.vpd, options.rma_mode, options.with_configless_fields,
      options.brand_code,
      allow_mismatched_components=options.allow_mismatched_components,
      use_name_match=options.use_name_match)

  OutputObject(options, {'encoded_string': identity.encoded_string,
                         'binary_string': identity.binary_string,
                         'database_checksum': options.database.checksum})


@Command(
    'decode',
    CmdArg('hwid', nargs='?', default=None,
           help='the HWID to decode.\n(required if not running on a DUT)'),
    *_OUTPUT_FORMAT_COMMON_ARGS)
def DecodeHWIDWrapper(options):
  """Decodes HWID."""
  encoded_string = options.hwid if options.hwid else GetHWIDString()
  identity, bom, configless = hwid_utils.DecodeHWID(options.database,
                                                    encoded_string)

  OutputObject(options,
               {'project': identity.project,
                'binary_string': identity.binary_string,
                'image_id': bom.image_id,
                'components': bom.components,
                'brand_code': identity.brand_code,
                'configless': configless})


@Command(
    'verify',
    CmdArg('hwid', nargs='?', default=None,
           help='the HWID to verify.\n(required if not running on a DUT)'),
    CmdArg('--allow-mismatched-components', action='store_true',
           help='Allows some probed components to be ignored if no any '
                'component in the database matches with them.'),
    *(_DEVICE_DATA_COMMON_ARGS + _RMA_COMMON_ARGS))
def VerifyHWIDWrapper(options):
  """Verifies HWID."""
  encoded_string = options.hwid if options.hwid else GetHWIDString()

  device_data = ObtainAllDeviceData(options)

  hwid_utils.VerifyHWID(
      options.database, encoded_string, device_data.probed_results,
      device_data.device_info, device_data.vpd, options.rma_mode,
      current_phase=options.phase,
      allow_mismatched_components=options.allow_mismatched_components)

  # No exception raised. Verification was successful.
  Output('Verification passed.')


@Command(
    'write',
    CmdArg('hwid', help='the encoded HWID string to write'))
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


@Command(
    'list-components',
    CmdArg('comp_class', nargs='*', default=None,
           help='the component classes to look up'),
    *_OUTPUT_FORMAT_COMMON_ARGS)
def ListComponentsWrapper(options):
  """Lists components of the given class."""
  components_list = hwid_utils.ListComponents(options.database,
                                              options.comp_class)
  OutputObject(options, components_list)


@Command(
    'enumerate-hwid',
    CmdArg('-i', '--image_id', default=None,
           help='the image ID to enumerate.'),
    CmdArg('-s', '--status', default='supported',
           choices=['supported', 'released', 'all'],
           help='the status of components to enumerate'),
    CmdArg('--comp', nargs='*', default=None,
           help=('Specify some of the component to limit the output.  '
                 'The format of COMP is '
                 '"<comp_cls>=<comp_name>[,<comp_name>[,<comp_name>...]]"')),
    CmdArg('--no-bom', action='store_true',
           help='Print the encoded string only.'))
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
  hwids = hwid_utils.EnumerateHWID(
      options.database, image_id=image_id, status=options.status,
      comps=comps)

  logging.debug('Printing %d sorted HWIDs...', len(hwids))
  if options.no_bom:
    for k in sorted(hwids.iterkeys()):
      Output(k)
  else:
    for k, v in sorted(hwids.iteritems()):
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
  converted_results_obj = converter.ConvertToProbeStatement(options.database)
  converted_results_data = json_utils.DumpStr(
      converted_results_obj, pretty=True)
  if options.output_file == '-':
    Output(converted_results_data)
  else:
    file_utils.WriteFile(options.output_file, converted_results_data)
  if options.output_checksum_file:
    checksum = hashlib.sha1(converted_results_data).hexdigest()
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
  if options.command_name in ('probe', 'build-database'):
    return

  # Create the Database object here since it's common to all functions.
  logging.debug('Loading database file %s/%s...', options.hwid_db_path,
                options.project.upper())
  options.database = Database.LoadFile(
      os.path.join(options.hwid_db_path, options.project.upper()),
      verify_checksum=(not options.no_verify_checksum))

  phase.OverridePhase(options.phase)

  # Get brand code if generate hwid with configless fields.
  if options.command_name == 'generate' and options.with_configless_fields:
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
