#!/usr/bin/env python
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Command-line interface for HWID v3 utilities."""

import json
import logging
import os
import shutil
import sys

import factory_common  # pylint: disable=W0611
from cros.factory.hwid.v3.bom import ProbedComponentResult
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3 import rule
from cros.factory.hwid.v3 import yaml_wrapper as yaml
try:
  from cros.factory.test import device_data
  _HAS_DEVICE_DATA = True
except ImportError:
  _HAS_DEVICE_DATA = False
from cros.factory.test.rules import phase
from cros.factory.utils.argparse_utils import CmdArg
from cros.factory.utils.argparse_utils import Command
from cros.factory.utils.argparse_utils import ParseCmdline
from cros.factory.utils import sys_utils
from cros.factory.utils import yaml_utils
from cros.factory.utils import process_utils


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

_DATABASE_BUILDER_COMMON_ARGS = [
    CmdArg('--add-default-component', default=None,
           nargs='+', metavar='COMP', dest='add_default_comp',
           help='Component classes that add a default item.\n'),
    CmdArg('--add-null-component', default=None,
           nargs='+', metavar='COMP', dest='add_null_comp',
           help='Component classes that add a null item.\n'),
    CmdArg('--del-component', default=None,
           nargs='+', metavar='COMP', dest='del_comp',
           help='Component classes that is deleted from database.\n'),
    CmdArg('--region', default=None, nargs='+',
           help='Supported regions'),
    CmdArg('--chassis', default=None, nargs='+',
           help='Supported chassis identifiers')
]

_VPD_COMMON_ARGS = [
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


class Arg(object):
  """A simple class to store arguments passed to the add_argument method of
  argparse module.
  """

  def __init__(self, *args, **kwargs):
    self.args = args
    self.kwargs = kwargs


def _GetHWIDString():
  return process_utils.CheckOutput(['gooftool', 'read_hwid']).strip()


@Command(
    'build-database',
    CmdArg('--probed-results-file', default=None, required=True,
           help='a file with probed results.\n'),
    CmdArg('--image-id', default='EVT',
           help="Name of image_id. Default is 'EVT'\n"),
    *_DATABASE_BUILDER_COMMON_ARGS)
def BuildDatabaseWrapper(options):
  '''Build the HWID database from probed result.'''
  if not os.path.isfile(options.probed_results_file):
    raise IOError('File %s is not found.' % options.probed_results_file)
  if not os.path.isdir(options.hwid_db_path):
    raise IOError('%s is not a directory.' % options.hwid_db_path)
  yaml_utils.ParseMappingAsOrderedDict(loader=yaml.Loader, dumper=yaml.Dumper)
  probed_results = hwid_utils.GetProbedResults(
      infile=options.probed_results_file)
  database_path = os.path.join(options.hwid_db_path, options.project.upper())
  hwid_utils.BuildDatabase(
      database_path, probed_results, options.project,
      options.image_id, options.add_default_comp, options.add_null_comp,
      options.del_comp, options.region, options.chassis)
  logging.info('Output the database to %s', database_path)


@Command(
    'update-database',
    CmdArg('--probed-results-file', default=None,
           help='a file with probed results.\n'),
    CmdArg('--image-id', default=None,
           help="Name of image_id.\n"),
    CmdArg('--output-database', default=None,
           help='Write into different file.\n'),
    *_DATABASE_BUILDER_COMMON_ARGS)
def UpdateDatabaseWrapper(options):
  '''Update the HWID database from probed result.'''
  if options.probed_results_file is None:
    probed_results = None
  else:
    if not os.path.isfile(options.probed_results_file):
      raise IOError('File %s is not found.' % options.probed_results_file)
    probed_results = hwid_utils.GetProbedResults(
        infile=options.probed_results_file)

  old_db_path = os.path.join(options.hwid_db_path, options.project.upper())
  if options.output_database is None:
    # If the output path is not assigned, we update the database in place.
    # We backup the original database before update.
    bak_db_path = old_db_path + '.bak'
    logging.info('In-place update, backup the database to %s', bak_db_path)
    shutil.copyfile(old_db_path, bak_db_path)

  # Load the original database as OrderedDict
  yaml_utils.ParseMappingAsOrderedDict(loader=yaml.Loader, dumper=yaml.Dumper)
  logging.info('Load the orignal database from %s', old_db_path)
  with open(old_db_path, 'r') as f:
    old_db = yaml.load(f)
  database_path = options.output_database or old_db_path
  hwid_utils.UpdateDatabase(
      database_path, probed_results, old_db, options.image_id,
      options.add_default_comp, options.add_null_comp, options.del_comp,
      options.region, options.chassis)
  logging.info('Output the updated database to %s.', database_path)


@Command(
    'generate',
    CmdArg('--probed-results-file', default=None,
           help=('A file with probed results.\n'
                 '(Required if not running on a DUT)')),
    CmdArg('--device-info-file', default=None,
           help=('A file with device info.\n'
                 '(Required if not running on a DUT.)\n'
                 'example content of this file:\n'
                 '    component.antenna: ACN\n'
                 '    component.has_cellular: True\n'
                 '    component.keyboard: US_API\n')),
    CmdArg('--rma-mode', default=False, action='store_true',
           help='Whether to enable RMA mode.'),
    CmdArg('--json-output', default=False, action='store_true',
           help='Whether to dump result in JSON format.'),
    *_VPD_COMMON_ARGS)
def GenerateHWIDWrapper(options):
  """Generates HWID."""
  if options.run_vpd and options.vpd_data_file:
    raise ValueError('The arguments --run-vpd and --vpd-data-file cannot be '
                     'set at the same time')

  bom = hwid_utils.GenerateBOMFromProbedResults(
      options.database, hwid_utils.GetProbedResults(
          infile=options.probed_results_file))

  # Select right device info (from file or shopfloor).
  if options.device_info_file:
    device_info = hwid_utils.GetDeviceInfo(options.device_info_file)
  elif sys_utils.InChroot():
    raise ValueError('Cannot get device info from shopfloor in chroot. '
                     'Please specify device info with an input file. If you '
                     'are running with command-line, use --device-info-file')
  elif not _HAS_DEVICE_DATA:
    raise ValueError('The device_data module is not available.')
  else:
    device_info = device_data.GetAllDeviceData()

  vpd = hwid_utils.GetVPDData(options.run_vpd, options.vpd_data_file)

  verbose_output = {
      'device_info': device_info,
      'bom': bom,
      'vpd': vpd
  }
  logging.debug(yaml.dump(verbose_output, default_flow_style=False))
  identity = hwid_utils.GenerateHWID(options.database, bom, device_info,
                                     rma_mode=options.rma_mode, vpd=vpd)
  if options.json_output:
    print json.dumps({
        'encoded_string': identity.encoded_string,
        'binary_string': identity.binary_string,
        'hwdb_checksum': options.database.checksum})
  else:
    print 'Encoded HWID string: %s' % identity.encoded_string
    print 'Binary HWID string: %s' % identity.binary_string


@Command(
    'decode',
    CmdArg('hwid', nargs='?', default=None,
           help='the HWID to decode.\n(required if not running on a DUT)'))
def DecodeHWIDWrapper(options):
  """Decodes HWID."""
  encoded_string = options.hwid if options.hwid else _GetHWIDString()
  identity, bom = hwid_utils.DecodeHWID(options.database, encoded_string)
  print yaml.dump(hwid_utils.ParseDecodedHWID(options.database, bom, identity),
                  default_flow_style=False)


@Command(
    'verify',
    CmdArg('hwid', nargs='?', default=None,
           help='the HWID to verify.\n(required if not running on a DUT)'),
    CmdArg('--probed-results-file', default=None,
           help=('a file with probed results.\n'
                 '(required if not running on a DUT)')),
    CmdArg('--rma-mode', default=False, action='store_true',
           help='whether to enable RMA mode.'),
    *_VPD_COMMON_ARGS)
def VerifyHWIDWrapper(options):
  """Verifies HWID."""
  encoded_string = options.hwid if options.hwid else _GetHWIDString()
  bom = hwid_utils.GenerateBOMFromProbedResults(
      options.database, hwid_utils.GetProbedResults(
          infile=options.probed_results_file))
  vpd = hwid_utils.GetVPDData(options.run_vpd, options.vpd_data_file)
  hwid_utils.VerifyHWID(options.database, encoded_string, bom,
                        vpd=vpd, rma_mode=options.rma_mode,
                        current_phase=options.phase)
  # No exception raised. Verification was successful.
  print 'Verification passed.'


@Command(
    'verify-components',
    CmdArg('--probed-results-file', default=None,
           help=('a file with probed results.\n'
                 '(required if not running on a DUT)')),
    CmdArg('--json_output', action='store_true', default=False,
           help='Output the returned value in json format.'),
    CmdArg('-c', '--components', default=None,
           help='the list of component classes to verify'),
    CmdArg('--no-fast-fw-probe', dest='fast_fw_probe', action='store_false',
           default=True,
           help='(deprecated) probe only firmware and EC version strings'))
def VerifyComponentsWrapper(options):
  """Verifies components."""
  if options.components:
    options.components = [v.strip() for v in options.components.split(',')]

  redirect_stdout = process_utils.DummyFile() if options.json_output else None
  with process_utils.RedirectStandardStreams(stdout=redirect_stdout):
    bom = hwid_utils.GenerateBOMFromProbedResults(
        options.database, hwid_utils.GetProbedResults(
            infile=options.probed_results_file))
    result = hwid_utils.VerifyComponents(options.database, bom,
                                         options.components)
  if options.json_output:
    def _ConvertToDict(obj):
      if isinstance(obj, (ProbedComponentResult, rule.Value)):
        return _ConvertToDict(obj.__dict__)
      if isinstance(obj, list):
        return [_ConvertToDict(item) for item in obj]
      if isinstance(obj, tuple):
        return tuple([_ConvertToDict(item) for item in obj])
      if isinstance(obj, dict):
        return {key: _ConvertToDict(value) for key, value in obj.iteritems()}
      return obj
    new_result = _ConvertToDict(result)
    print json.dumps(new_result)
  else:
    failed = []
    waive_list = []
    if options.fast_fw_probe:
      waive_list = ['key_recovery', 'key_root', 'hash_gbb']
    for comp_cls, comps in result.iteritems():
      if comp_cls in waive_list:
        continue
      for comp_result in comps:
        if comp_result.error:
          failed.append('%s: %s' % (comp_cls, comp_result.error))
    if failed:
      print 'Verification failed for the following components:'
      print '\n'.join(failed)
    else:
      print 'Verification passed.'


@Command(
    'write',
    CmdArg('hwid', help='the encoded HWID string to write'))
def WriteHWIDWrapper(options):
  """Writes HWID to firmware GBB."""
  if sys_utils.InChroot():
    raise ValueError('Cannot write HWID to GBB in chroot.')

  process_utils.CheckOutput(['gooftool', 'write_hwid', options.hwid])
  print 'HWID %r written to firmware GBB.' % options.hwid


@Command('read')
def ReadHWIDWrapper(unused_options):
  """Reads HWID from firmware GBB."""
  if sys_utils.InChroot():
    raise ValueError('Cannot read HWID from GBB in chroot.')

  print _GetHWIDString()


@Command(
    'list-components',
    CmdArg('comp_class', nargs='*', default=None,
           help='the component classes to look up'))
def ListComponentsWrapper(options):
  """Lists components of the given class."""
  components_list = hwid_utils.ListComponents(options.database,
                                              options.comp_class)
  print yaml.safe_dump(components_list, default_flow_style=False)


@Command(
    'enumerate-hwid',
    CmdArg('-i', '--image_id', default=None,
           help='the image ID to enumerate.'),
    CmdArg('-s', '--status', default='supported',
           choices=['supported', 'released', 'all'],
           help='the status of components to enumerate'))
def EnumerateHWIDWrapper(options):
  """Enumerates possible HWIDs."""
  # Enumerating may take a very long time so we want to verbosely make logs.
  logging.debug('Enumerating all HWIDs...')
  hwids = hwid_utils.EnumerateHWID(options.database, options.image_id,
                                   options.status)
  logging.debug('Printing %d sorted HWIDs...', len(hwids))
  for k, v in sorted(hwids.iteritems()):
    print '%s: %s' % (k, v)


@Command('verify-database')
def VerifyHWIDDatabase(options):
  """Verifies the given HWID database."""
  # Do nothing here since all the verifications are done when loading the
  # database with HWID library.
  print 'Database %s verified' % options.project


def ParseOptions(args=None):
  """Parse arguments and generate necessary options."""
  return ParseCmdline('HWID command-line utilities', *_COMMON_ARGS,
                      args_to_parse=args)


def InitializeDefaultOptions(options):
  if not options.hwid_db_path:
    options.hwid_db_path = hwid_utils.GetDefaultDataPath()
  if options.project is None:
    if sys_utils.InChroot():
      print 'Argument -j/--project is required'
      sys.exit(1)
    options.project = hwid_utils.ProbeProject()

  # Build database doesn't need to initialize the database.
  if options.command_name in ['build-database']:
    return

  # Create the Database object here since it's common to all functions.
  logging.debug('Loading database file %s/%s...', options.hwid_db_path,
                options.project.upper())
  options.database = database.Database.LoadFile(
      os.path.join(options.hwid_db_path, options.project.upper()),
      verify_checksum=(not options.no_verify_checksum))

  phase.OverridePhase(options.phase)


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
