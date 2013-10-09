#!/bin/env python
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import collections
import logging
import os
import re
import yaml

import factory_common # pylint: disable=W0611
from cros.factory import common as factory_common_utils
from cros.factory import rule
from cros.factory.gooftool import crosfw, probe
from cros.factory.hwid import common, database, decoder, encoder
from cros.factory.test import shopfloor, utils
from cros.factory.utils import process_utils


_OPTION_PARSER = argparse.ArgumentParser(description='HWID tools')
_SUBPARSERS = _OPTION_PARSER.add_subparsers(
    title='subcommands', help='Valid subcommands.', dest='subcommand')
_SUBCOMMANDS = {}


class Arg(object):
  """A simple class to store arguments passed to the add_argument method of
  argparse module.
  """
  def __init__(self, *args, **kwargs):
    self.args = args
    self.kwargs = kwargs


def Command(name, help, args=None): # pylint: disable=W0622
  """A decorator to set up args and register a subcommand.

  Args:
    name: The subcommand name.
    help: Help message of the subcommand.
    args: An optional list of Arg objects listing the arguments of the
        subcommand.
  """
  def Wrapped(fn):
    subparser = _SUBPARSERS.add_parser(name, help=help)
    if args:
      for arg in args:
        subparser.add_argument(*arg.args, **arg.kwargs)
    _SUBCOMMANDS[name] = fn
  return Wrapped


def _HWIDMode(rma_mode):
  if rma_mode:
    return common.HWID.OPERATION_MODE.rma
  return common.HWID.OPERATION_MODE.normal


def GenerateHWID(db, probed_results, device_info, vpd, rma_mode):
  """Generates a version 3 HWID from the given data.

  The HWID is generated based on the given device info and probed results. If
  there are conflits of component information between device_info and
  probed_results, priority is given to device_info.

  Args:
    db: A Database object to be used.
    probed_results: A dict containing the probe results to be used.
    device_info: A dict of component infomation keys to their corresponding
        values. The format is device-specific and the meanings of each key and
        value vary from device to device. The valid keys and values should be
        specified in board-specific component database.
    vpd: A dict of RO and RW VPD values.
    rma_mode: Whether to verify components status in RMA mode.

  Returns:
    The generated HWID object.
  """
  hwid_mode = _HWIDMode(rma_mode)
  probed_results_yaml = yaml.dump(probed_results)
  # Construct a base BOM from probe_results.
  device_bom = db.ProbeResultToBOM(probed_results_yaml)
  hwid = encoder.Encode(db, device_bom, mode=hwid_mode, skip_check=True)

  # Verify the probe result with the generated HWID to make sure nothing is
  # mis-configured after setting default values to unprobeable encoded fields.
  hwid.VerifyProbeResult(probed_results_yaml)

  # Update unprobeable components with rules defined in db before verification.
  context = rule.Context(hwid=hwid, device_info=device_info, vpd=vpd)
  db.rules.EvaluateRules(context, namespace='device_info.*')
  hwid.VerifyComponentStatus()
  return hwid


def DecodeHWID(db, encoded_string):
  """Decodes the given version 3 HWID encoded string and returns the decoded
  info.

  Args:
    db: A Database object to be used.
    encoded_string: A encoded HWID string to test. If not specified,
        use gbb_utility to get HWID.

  Returns:
    The decoded HWIDv3 context object.
  """
  return decoder.Decode(db, encoded_string)


def ParseDecodedHWID(hwid):
  """Parse the HWID object into a more compact dict.

  This function returns the board name and binary string from the HWID object,
  along with a generated dict of components to their probed values decoded in
  the HWID object.

  Args:
    hwid: A decoded HWID object.

  Returns:
    A dict containing the board name, the binary string, and the list of
    components.
  """
  output_components = collections.defaultdict(list)
  components = hwid.bom.components
  db_components = hwid.database.components
  for comp_cls in sorted(components):
    for (comp_name, probed_values, _) in sorted(components[comp_cls]):
      if not probed_values:
        probed_values = db_components.GetComponentAttributes(
            comp_cls, comp_name).get('values')
      output_components[comp_cls].append(
          {comp_name: probed_values if probed_values else None})
  return {'board': hwid.database.board,
          'binary_string': hwid.binary_string,
          'components': dict(output_components)}


def VerifyHWID(db, encoded_string, probed_results, vpd, rma_mode):
  """Verifies the given encoded version 3 HWID string against the component
  db.

  A HWID context is built with the encoded HWID string and the board-specific
  component database. The HWID context is used to verify that the probed
  results match the infomation encoded in the HWID string.

  RO and RW VPD are also loaded and checked against the required values stored
  in the board-specific component database.

  Args:
    db: A Database object to be used.
    encoded_string: A encoded HWID string to test. If not specified,
        defaults to the HWID read from GBB on DUT.
    probed_results: A dict containing the probe results to be used.
    vpd: A dict of RO and RW VPD values.
    rma_mode: True for RMA mode to allow deprecated components. Defaults to
        False.

  Raises:
    HWIDException if verification fails.
  """
  hwid_mode = _HWIDMode(rma_mode)
  hwid = decoder.Decode(db, encoded_string, mode=hwid_mode)
  hwid.VerifyProbeResult(yaml.dump(probed_results))
  hwid.VerifyComponentStatus()
  context = rule.Context(hwid=hwid, vpd=vpd)
  db.rules.EvaluateRules(context, namespace="verify.*")


def ListComponents(db, comp_class=None):
  """Lists the components of the given component class.

  Args:
    db: A Database object to be used.
    comp_class: An optional list of component classes to look up. If not given,
        the function will list all the components of all component classes in
        the database.

  Returns:
    A dict of component classes to the component items of that class.
  """
  if not comp_class:
    comp_class_to_lookup = db.components.components_dict.keys()
  else:
    comp_class_to_lookup = factory_common_utils.MakeList(comp_class)

  output_components = collections.defaultdict(list)
  for comp_cls in comp_class_to_lookup:
    if comp_cls not in db.components.components_dict:
      raise ValueError('Invalid component class %r' % comp_cls)
    output_components[comp_cls].extend(
        db.components.components_dict[comp_cls]['items'].keys())

  # Convert defaultdict to dict.
  return dict(output_components)

def GetProbedResults(infile=None):
  """Get probed results either from the given file or by probing the DUT.

  Args:
    infile: A file containing the probed results in YAML format.

  Returns:
    A dict of probed results.
  """
  if infile:
    with open(infile, 'r') as f:
      probed_results = yaml.load(f.read())
  else:
    if utils.in_chroot():
      raise ValueError('Cannot probe components in chroot. Please specify '
                       'probed results with --probed_results_file')
    probed_results = yaml.load(probe.Probe(probe_vpd=True).Encode())
  return probed_results


def GetDeviceInfo(infile=None):
  """Get device info either from the given file or shopfloor server.

  Args:
    infile: A file containing the device info in YAML format. For example:

        component.has_cellular: True
        component.keyboard: US_API
        ...

  Returns:
    A dict of device info.
  """
  if infile:
    with open(infile, 'r') as f:
      device_info = yaml.load(f.read())
  else:
    if utils.in_chroot():
      raise ValueError('Cannot get device info from shopfloor in chroot. '
                       'Please specify device info with --device_info_file')
    device_info = shopfloor.GetDeviceData()
  return device_info


def GetHWIDString():
  """Get HWID string from GBB on a DUT."""
  if utils.in_chroot():
    raise ValueError('Cannot read HWID from GBB in chroot. Please specify '
                     'a HWID encoded string to decode.')
  main_fw_file = crosfw.LoadMainFirmware().GetFileName()
  gbb_result = process_utils.CheckOutput(
      ['gbb_utility', '-g', '--hwid', '%s' % main_fw_file])
  return re.findall(r'hardware_id:(.*)', gbb_result)[0].strip()


def GetVPD(probed_results):
  """Strips VPD from the given probed results and returns the VPD.

  Args:
    probed_results: A dict of probed results. On a DUT, run

            gooftool probe --include_vpd

        to get the probed results with VPD values on it.

  Returns:
    A dict of RO and RW VPD values.
  """
  vpd = {'ro': {}, 'rw': {}}
  if not probed_results.get('found_volatile_values'):
    return vpd

  for k, v in probed_results['found_volatile_values'].items():
    # Use items(), not iteritems(), since we will be modifying the dict in the
    # loop.
    match = re.match('^vpd\.(ro|rw)\.(\w+)$', k)
    if match:
      del probed_results['found_volatile_values'][k]
      vpd[match.group(1)][match.group(2)] = v
  return vpd


@Command('generate', help='Generate HWID.', args=[
    Arg('--probed_results_file', default=None,
        help='A file with probed results. Required if not running on DUT.'),
    Arg('--device_info_file', default=None,
        help='A file with device info. Required if not running on DUT.'),
    Arg('--rma_mode', default=False, action='store_true',
        help='Whether to enable RMA mode.')])
def GenerateHWIDWrapper(options):
  probed_results = GetProbedResults(options.probed_results_file)
  device_info = GetDeviceInfo(options.device_info_file)
  vpd = GetVPD(probed_results)

  verbose_output = {
      'device_info': device_info,
      'probed_results': probed_results,
      'vpd': vpd
  }
  logging.debug(yaml.dump(verbose_output, default_flow_style=False))
  hwid = GenerateHWID(options.database, probed_results, device_info, vpd,
                      options.rma_mode)
  print 'Encoded HWID string: %s' % hwid.encoded_string
  print 'Binary HWID string: %s' % hwid.binary_string


@Command('decode', help='Decode HWID.', args=[
    Arg('hwid', nargs='?', default=None,
        help='The HWID to decode. Required if not running on DUT.')])
def DecodeHWIDWrapper(options):
  encoded_string = options.hwid if options.hwid else GetHWIDString()
  decoded_hwid = DecodeHWID(options.database, encoded_string)
  print yaml.dump(ParseDecodedHWID(decoded_hwid), default_flow_style=False)


@Command('verify', help='Verify HWID.', args=[
    Arg('hwid', nargs='?', default=None,
        help='The HWID to decode. Required if not running on DUT.'),
    Arg('--probed_results_file', default=None,
        help='A file with probed results. Required if not running on DUT.'),
    Arg('--rma_mode', default=False, action='store_true',
        help='Whether to enable RMA mode.')])
def VerifyHWIDWrapper(options):
  encoded_string = options.hwid if options.hwid else GetHWIDString()
  probed_results = GetProbedResults(options.probed_results_file)
  vpd = GetVPD(probed_results)
  VerifyHWID(options.database, encoded_string, probed_results, vpd,
             options.rma_mode)
  # No exception raised. Verification was successful.
  print 'Verification passed.'


@Command('list_components', help='List components of the given class', args=[
    Arg('comp_class', nargs='*', default=None,
        help='The component classes to look up.')])
def ListComponentsWrapper(options):
  components_list = ListComponents(options.database, options.comp_class)
  print yaml.safe_dump(components_list, default_flow_style=False)


def ParseOptions():
  """Parse arguments and generate necessary options."""
  _OPTION_PARSER.add_argument(
      '-p', '--hwid_db_path', default=None,
      help='Path to the HWID database directory.')
  _OPTION_PARSER.add_argument(
      '-b', '--board', default=None,
      help='Board name of the HWID database to load. '
           'Required if not running on DUT')
  _OPTION_PARSER.add_argument(
      '-v', '--verbose', default=False, action='store_true',
      help='Enable verbose output.')

  options = _OPTION_PARSER.parse_args()
  if not options.hwid_db_path:
    options.hwid_db_path = common.DEFAULT_HWID_DATA_PATH
  if not options.board:
    options.board = common.ProbeBoard()

  # Create the Database object here since it's common to all functions.
  options.database = database.Database.LoadFile(
      os.path.join(options.hwid_db_path, options.board.upper()))
  return options


def Main():
  """Parses options, sets up logging, and runs the given subcommand."""
  options = ParseOptions()
  if options.verbose:
    logging.basicConfig(level=logging.DEBUG)

  _SUBCOMMANDS[options.subcommand](options)


if __name__ == '__main__':
  Main()
