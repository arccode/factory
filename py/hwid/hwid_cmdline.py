#!/bin/env python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Command-line interface for HWID v3 utilities."""

import logging
import os
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.hacked_argparse import Command, CmdArg, ParseCmdline
from cros.factory.hwid import common
from cros.factory.hwid import database
from cros.factory.hwid import hwid_utils
from cros.factory.tools import build_board


_COMMON_ARGS = [
    CmdArg('-p', '--hwid-db-path', default=None,
           help='path to the HWID database directory'),
    CmdArg('-b', '--board', default=None,
           help=('board name of the HWID database to load.\n'
                 '(required if not running on a DUT)')),
    CmdArg('-v', '--verbose', default=False, action='store_true',
           help='enable verbose output'),
    CmdArg('--no-verify-checksum', default=False, action='store_true',
           help='do not check database checksum')
]


class Arg(object):
  """A simple class to store arguments passed to the add_argument method of
  argparse module.
  """

  def __init__(self, *args, **kwargs):
    self.args = args
    self.kwargs = kwargs


@Command(
    'generate',
    CmdArg('--probed-results-file', default=None,
           help=('a file with probed results.\n'
                 '(required if not running on a DUT)')),
    CmdArg('--device-info-file', default=None,
           help=('a file with device info.\n'
                 '(required if not running on a DUT.)\n'
                 'example content of this file:\n'
                 '    component.antenna: ACN\n'
                 '    component.has_cellular: True\n'
                 '    component.keyboard: US_API\n')),
    CmdArg('--rma-mode', default=False, action='store_true',
           help='whether to enable RMA mode'))
def GenerateHWIDWrapper(options):
  """Generates HWID."""
  probed_results = hwid_utils.GetProbedResults(options.probed_results_file)
  device_info = hwid_utils.GetDeviceInfo(options.device_info_file)
  vpd = hwid_utils.GetVPD(probed_results)

  verbose_output = {
      'device_info': device_info,
      'probed_results': probed_results,
      'vpd': vpd
  }
  logging.debug(yaml.dump(verbose_output, default_flow_style=False))
  hwid = hwid_utils.GenerateHWID(options.database, probed_results, device_info,
                                 vpd, options.rma_mode)
  print 'Encoded HWID string: %s' % hwid.encoded_string
  print 'Binary HWID string: %s' % hwid.binary_string


@Command(
    'decode',
    CmdArg('hwid', nargs='?', default=None,
           help='the HWID to decode.\n(required if not running on a DUT)'))
def DecodeHWIDWrapper(options):
  """Decodes HWID."""
  encoded_string = options.hwid if options.hwid else hwid_utils.GetHWIDString()
  decoded_hwid = hwid_utils.DecodeHWID(options.database, encoded_string)
  print yaml.dump(hwid_utils.ParseDecodedHWID(decoded_hwid),
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
    CmdArg('--phase', default=None,
           help=('override phase for phase checking (defaults to the current '
                 'as returned by the "factory phase" command)')))
def VerifyHWIDWrapper(options):
  """Verifies HWID."""
  encoded_string = options.hwid if options.hwid else hwid_utils.GetHWIDString()
  probed_results = hwid_utils.GetProbedResults(options.probed_results_file)
  vpd = hwid_utils.GetVPD(probed_results)
  hwid_utils.VerifyHWID(options.database, encoded_string, probed_results, vpd,
                        options.rma_mode, options.phase)
  # No exception raised. Verification was successful.
  print 'Verification passed.'


@Command(
    'verify-components',
    CmdArg('--probed-results-file', default=None,
           help=('a file with probed results.\n'
                 '(required if not running on a DUT)')),
    CmdArg('-c', '--components', default=None,
           help='the list of component classes to verify'),
    CmdArg('--no-fast-fw-probe', dest='fast_fw_probe', action='store_false',
           default=True, help='probe only firmware and EC version strings'))
def VerifyComponentsWrapper(options):
  """Verifies components."""
  if not options.components:
    probed_results = hwid_utils.GetProbedResults(
        infile=options.probed_results_file,
        fast_fw_probe=options.fast_fw_probe)
  else:
    options.components = [v.strip() for v in options.components.split(',')]
    if set(['ro_ec_firmware', 'ro_main_firmware']) & set(options.components):
      probe_volatile = True
    else:
      probe_volatile = False
    probed_results = hwid_utils.GetProbedResults(
        infile=options.probed_results_file,
        target_comp_classes=options.components,
        fast_fw_probe=options.fast_fw_probe,
        probe_volatile=probe_volatile, probe_initial_config=False)
  result = hwid_utils.VerifyComponents(options.database, probed_results,
                                       options.components)
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
  hwid_utils.WriteHWID(options.hwid)
  print 'HWID %r written to firmware GBB.' % options.hwid


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
  for k, v in sorted(hwid_utils.EnumerateHWID(
      options.database, options.image_id, options.status).items()):
    print '%s: %s' % (k, v)


@Command('verify-database')
def VerifyHWIDDatabase(options):
  """Verifies the given HWID database."""
  # Do nothing here since all the verifications are done when loading the
  # database with HWID library.
  print 'Database %s verified' % options.board


def ParseOptions(args=None):
  """Parse arguments and generate necessary options."""
  return ParseCmdline('HWID command-line utilities', *_COMMON_ARGS,
                      args_to_parse=args)


def InitializeDefaultOptions(options):
  if not options.hwid_db_path:
    options.hwid_db_path = common.DEFAULT_HWID_DATA_PATH
  if not options.board:
    options.board = common.ProbeBoard()

  board = build_board.BuildBoard(options.board).base
  board_variant = build_board.BuildBoard(options.board).variant
  # Use the variant specific HWID db if one exists, else reuse the one
  # from the base board.
  if board_variant and os.path.exists(
      os.path.join(options.hwid_db_path, board_variant.upper())):
    board = board_variant

  # Create the Database object here since it's common to all functions.
  options.database = database.Database.LoadFile(
      os.path.join(options.hwid_db_path, board.upper()),
      verify_checksum=(not options.no_verify_checksum))


def Main():
  """Parses options, sets up logging, and runs the given subcommand."""
  options = ParseOptions()
  if options.verbose:
    logging.basicConfig(level=logging.DEBUG)
  else:
    logging.basicConfig(level=logging.INFO)

  InitializeDefaultOptions(options)

  options.command(options)


if __name__ == '__main__':
  Main()
