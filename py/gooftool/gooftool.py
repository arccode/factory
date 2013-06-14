#!/usr/bin/python
# pylint: disable=E1101
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Google Factory Tool.

This tool is indended to be used on factory assembly lines.  It
provides all of the Google required test functionality and must be run
on each device as part of the assembly process.
"""

import collections
import logging
import os
import pipes
import re
import sys
import time
import xmlrpclib
import yaml

from tempfile import gettempdir

import factory_common  # pylint: disable=W0611

from cros.factory import event_log
from cros.factory.common import Error, SetupLogging, Shell
from cros.factory.common import YamlWrite
from cros.factory.gooftool import Gooftool
from cros.factory.gooftool import crosfw
from cros.factory.gooftool import report_upload
from cros.factory.gooftool.probe import Probe, PROBEABLE_COMPONENT_CLASSES
from cros.factory.gooftool.probe import ReadRoVpd, ReadRwVpd
from cros.factory.gooftool.vpd_data import KNOWN_VPD_FIELD_DATA
from cros.factory.hacked_argparse import CmdArg, Command, ParseCmdline
from cros.factory.hacked_argparse import verbosity_cmd_arg
from cros.factory.hwdb import hwid_tool
from cros.factory.test.factory import FACTORY_LOG_PATH
from cros.factory.utils.process_utils import Spawn
from cros.factory.privacy import FilterDict


# TODO(tammo): Replace calls to sys.exit with raise Exit, and maybe
# treat that specially (as a smoot exit, as opposed to the more
# verbose output for generic Error).


def GetGooftool(options):
  if options.hwid_version == 2:
    hwdb_path = getattr(options, 'hwdb_path', None)
    component_db = (
        hwid_tool.HardwareDb(options.hwdb_path).comp_db if hwdb_path else None)
    return Gooftool(hwid_version=2, component_db=component_db)
  elif options.hwid_version == 3:
    board = getattr(options, 'board', None)
    hwdb_path = getattr(options, 'hwdb_path', None)
    return Gooftool(hwid_version=3, board=board, hwdb_path=hwdb_path)
  else:
    raise Error, 'Invalid HWID version: %r' % options.hwid_version


@Command('write_hwid',
         CmdArg('hwid', metavar='HWID', help='HWID string'))
def WriteHWID(options):
  """Write specified HWID value into the system BB."""

  logging.info('writing hwid string %r', options.hwid)
  GetGooftool(options).WriteHWID(options.hwid)
  event_log.Log('write_hwid', hwid=options.hwid)
  print 'Wrote HWID: %r' % options.hwid


_board_cmd_arg = CmdArg(
    '--board', metavar='BOARD',
    default=None, help='Board name to test.')

_hwdb_path_cmd_arg = CmdArg(
    '--hwdb_path', metavar='PATH',
    default=hwid_tool.DEFAULT_HWID_DATA_PATH,
    help='Path to the HWID database.')

_hwid_status_list_cmd_arg = CmdArg(
  '--status', nargs='*', default=['supported'],
  help='allow only HWIDs with these status values')

_probe_results_cmd_arg = CmdArg(
    '--probe_results', metavar='RESULTS.yaml',
    help=('Output from "gooftool probe" (used instead of '
          'probing this system).'))

_device_info_cmd_arg = CmdArg(
    '--device_info', metavar='DEVICE_INFO.yaml', default=None,
    help='A dict of device info to use instead of fetching from shopfllor '
    'server.')

_hwid_cmd_arg = CmdArg(
    '--hwid', metavar='HWID',
    help='HWID to verify (instead of the currently set HWID of this system).')


@Command('best_match_hwids',
         _hwdb_path_cmd_arg,
         CmdArg('-b', '--board', metavar='BOARD',
                help='optional BOARD name, needed only if data is present '
                'for more than one'),
         CmdArg('--bom', metavar='BOM', help='BOM name'),
         CmdArg('--variant', metavar='VARIANT', help='VARIANT code'),
         CmdArg('--optimistic', action='store_true',
                help='do not probe; assume singletons match'),
         CmdArg('--comps', nargs='*', default=[],
                help='list of canonical component names'),
         CmdArg('--missing', nargs='*', default=[],
                help='list component classes to be assumed missing'),
         CmdArg('--status', nargs='*', default=['supported'],
                help='consider only HWIDs within this list of status values'))
def BestMatchHwids(options):
  """Determine a list of possible HWIDs using provided args and probeing.

  VOLATILE can always be determined by probing.  To get a unique
  result, VARIANT must be specified for all cases where the matching
  BOM has more than one associated variant code, otherwise all HWID
  variants will be returned.  Both VARIANT and BOM information can
  alternatively be specified using the --stdin_comps argument, which
  allows specifying a list of canonical names (one per line) on stdin,
  one per line.  Based on what is known from BOM and stdin_comps,
  determine a list of components to probe for, and use those probe
  results to resolve a list of matching HWIDs.  If no boms,
  components, or variant codes are specified, then a list of all HWIDs
  that match probeable components will be returned.

  Returns (on stdout): A list of HWIDs that match the available probe
  results and argument contraints, one per line.

  Example:

  // Three ways to specify a keyboard (assuming it is a variant component)
  gooftool best_match_hwids --missing keyboard
  gooftool best_match_hwids --variant A or
  gooftool best_match_hwids --comps us_kbd
  """

  map(hwid_tool.Validate.Status, options.status)
  hw_db = hwid_tool.HardwareDb(options.hwdb_path)
  comp_db = hw_db.comp_db
  device = hw_db.GetDevice(options.board)
  component_spec = hwid_tool.ComponentSpec.New()
  if options.bom:
    device.BomExists(options.bom)
    component_spec = hwid_tool.CombineComponentSpecs(
      component_spec, device.boms[options.bom].primary)
  if options.variant:
    device.VariantExists(options.variant)
    variant_spec = device.variants[options.variant]
    if hwid_tool.ComponentSpecsConflict(component_spec, variant_spec):
      sys.exit('ERROR: multiple specifications for these components:\n%s'
               % YamlWrite(sorted(
                   hwid_tool.ComponentSpecClasses(component_spec) &
                   hwid_tool.ComponentSpecClasses(variant_spec))))
    component_spec = hwid_tool.CombineComponentSpecs(
      component_spec, variant_spec)
  if options.comps or options.missing:
    map(comp_db.CompExists, options.comps)
    map(comp_db.CompClassExists, options.missing)
    extra_comp_spec = comp_db.CreateComponentSpec(
      components=options.comps,
      missing=options.missing)
    print 'cmdline asserted components:\n%s' % extra_comp_spec.Encode()
    if hwid_tool.ComponentSpecsConflict(component_spec, extra_comp_spec):
      sys.exit('ERROR: multiple specifications for these components:\n%s'
               % YamlWrite(sorted(
                   hwid_tool.ComponentSpecClasses(component_spec) &
                   hwid_tool.ComponentSpecClasses(extra_comp_spec))))
    component_spec = hwid_tool.CombineComponentSpecs(
      component_spec, extra_comp_spec)
  spec_classes = hwid_tool.ComponentSpecClasses(component_spec)
  missing_classes = set(comp_db.all_comp_classes) - spec_classes
  if missing_classes and not options.optimistic:
    non_probeable_missing = missing_classes - PROBEABLE_COMPONENT_CLASSES
    if non_probeable_missing:
      sys.exit('FAILURE: these classes are necessary, were not specified '
               'as inputs, and cannot be probed for:\n%s'
               'This problem can often be addressed by specifying all of '
               'the missing components on the command line (see the command '
               'help).' % YamlWrite(list(non_probeable_missing)))
    print 'probing for missing classes:'
    print YamlWrite(list(missing_classes))
    probe_results = Probe(target_comp_classes=list(missing_classes),
                          probe_volatile=False, probe_initial_config=False)
    cooked_components = comp_db.MatchComponentProbeValues(
      probe_results.found_probe_value_map)
    if cooked_components.unmatched:
      sys.exit('ERROR: some probed components are unrecognized:\n%s'
               % YamlWrite(cooked_components.unmatched))
    probed_comp_spec = comp_db.CreateComponentSpec(
      components=cooked_components.matched,
      missing=probe_results.missing_component_classes)
    component_spec = hwid_tool.CombineComponentSpecs(
      component_spec, probed_comp_spec)
  print YamlWrite({'component data used for matching': {
        'missing component classes': component_spec.classes_missing,
        'found components': component_spec.components}})
  component_data = hwid_tool.ComponentData(
    extant_components=hwid_tool.ComponentSpecCompClassMap(
      component_spec).keys(),
    classes_missing=component_spec.classes_missing)
  match_tree = device.BuildMatchTree(component_data)
  if not match_tree:
    sys.exit('FAILURE: NO matching BOMs found')
  print 'potential BOMs/VARIANTs:'
  potential_variants = set()
  potential_volatiles = set()
  for bom_name, variant_tree in match_tree.items():
    print '  BOM: %-8s   VARIANTS: %s' % (
      bom_name, ', '.join(sorted(variant_tree)))
    for variant_code in variant_tree:
      potential_variants.add(variant_code)
      for volatile_code in device.volatiles:
        status = device.GetHwidStatus(bom_name, variant_code, volatile_code)
        if status in options.status:
          potential_volatiles.add(volatile_code)
  print ''
  if len(potential_variants) == 0:
    sys.exit('FAILURE: no matching VARIANTs found')
  if len(potential_volatiles) == 0:
    sys.exit('FAILURE: no VOLATILEs found for potential matching BOMs/VARIANTS '
             '(with specified status)')
  if (options.optimistic and
      len(match_tree) == 1 and
      len(potential_variants) == 1 and
      len(potential_volatiles) == 1):
    print ('MATCHING HWID: %s' % device.FmtHwid(match_tree.keys().pop(),
                                                potential_variants.pop(),
                                                potential_volatiles.pop()))
    return
  print ('probing VOLATILEs to resolve potential matches: %s\n' %
         ', '.join(sorted(potential_volatiles)))
  vol_probe_results = Probe(
    target_comp_classes=[],
    probe_volatile=True,
    probe_initial_config=False)
  cooked_volatiles = device.MatchVolatileValues(
    vol_probe_results.found_volatile_values)
  match_tree = device.BuildMatchTree(
    component_data, cooked_volatiles.matched_tags)
  matched_hwids = device.GetMatchTreeHwids(match_tree)
  if matched_hwids:
    for hwid in matched_hwids:
      if matched_hwids[hwid] in options.status:
        print 'MATCHING HWID: %s' % hwid
    return
  print 'exact HWID matching failed, but the following BOMs match: %s' % (
    ', '.join(sorted(match_tree)))
  if options.optimistic and len(match_tree) == 1:
    bom_name = set(match_tree).pop()
    bom = device.boms[bom_name]
    variant_matches = match_tree[bom_name]
    if len(variant_matches) == 1:
      var_code = set(variant_matches).pop()
    elif len(bom.variants) == 1:
      var_code = set(bom.variants).pop()
    else:
      sys.exit('FAILURE: NO matching HWIDs found; optimistic matching failed  '
               'because there were too many variants to choose from for BOM %r'
               % bom_name)
    hwids = [device.FmtHwid(bom_name, var_code, vol_code)
             for vol_code in device.volatiles
             if device.GetHwidStatus(bom_name, var_code, vol_code)
             in options.status]
    for hwid in hwids:
      print 'MATCHING HWID: %s' % hwid
    return
  else:
    print ('optimistic matching not attempted because either it was '
           'not requested, or because the number of BOMs was <> 1\n')
  sys.exit('FAILURE: NO matching HWIDs found')


@Command('probe',
         CmdArg('--comps', nargs='*',
                help='List of keys from the component_db registry.'),
         CmdArg('--fast_fw_probe', action='store_true',
                help='Do a fast probe for EC and main firmware versions only. '
                'This implies --no_vol and --no_ic.'),
         CmdArg('--no_vol', action='store_true',
                help='Do not probe volatile data.'),
         CmdArg('--no_ic', action='store_true',
                help='Do not probe initial_config data.'),
         CmdArg('--include_vpd', action='store_true',
                help='Include VPD data in volatiles.'))
def RunProbe(options):
  """Print yaml-formatted breakdown of probed device properties."""
  print GetGooftool(options).Probe(
      target_comp_classes=options.comps,
      fast_fw_probe=options.fast_fw_probe,
      probe_volatile=not options.no_vol,
      probe_initial_config=not options.no_ic,
      probe_vpd=options.include_vpd).Encode()


@Command('verify_components',
         _hwdb_path_cmd_arg,
         CmdArg('target_comps', nargs='*'))
def VerifyComponents(options):
  """Verify that probeable components all match entries in the component_db.

  Probe for each component class in the target_comps and verify
  that a corresponding match exists in the component_db -- make sure
  that these components are present, that they have been approved, but
  do not check against any specific BOM/HWID configurations.
  """

  try:
    result = GetGooftool(options).VerifyComponents(
        options.target_comps)
  except ValueError, e:
    sys.exit(e)

  PrintVerifyComponentsResults(result)


def PrintVerifyComponentsResults(result):
  """Prints out the results of VerifyComponents method call.

  Groups the results into two groups: 'matches' and 'errors', and prints out
  their values.
  """
  # group by matches and errors
  matches = []
  errors = []
  for result_list in result.values():
    for component_name, _, error in result_list:
      if component_name:
        matches.append(component_name)
      else:
        errors.append(error)

  if matches:
    print 'found probeable components:\n  %s' % '\n  '.join(matches)
  if errors:
    print '\nerrors:\n  %s' % '\n  '.join(errors)
    sys.exit('\ncomponent verification FAILURE')
  else:
    print "\ncomponent verification SUCCESS"


@Command('verify_hwid',
         _hwid_status_list_cmd_arg,
         _hwdb_path_cmd_arg,
         _probe_results_cmd_arg,
         _hwid_cmd_arg)
def VerifyHwid(options):
  """Verify system HWID properties match probed device properties.

  First probe components, volatile and initial_config parameters for
  the DUT.  Then use the available device data to produce a list of
  candidate HWIDs.  Then verify the HWID from the DUT is present in
  that list.  Then verify that the DUT initial config values match
  those specified for its HWID.  Finally, verify that VPD contains all
  the necessary fields as specified by the board data, and when
  possible verify that values are legitimate.
  """

  def VerifyVpd(ro_vpd_keys, rw_vpd_keys):
    for key in ro_vpd_keys:
      if key not in ro_vpd:
        sys.exit('Missing required RO VPD field: %s' % key)
      known_valid_values = KNOWN_VPD_FIELD_DATA.get(key, None)
      value = ro_vpd[key]
      if (known_valid_values is not None) and (value not in known_valid_values):
        sys.exit('Invalid RO VPD entry : key %r, value %r' % (key, value))
    for key in rw_vpd_keys:
      if key not in rw_vpd:
        sys.exit('Missing required RW VPD field: %s' % key)
      known_valid_values = KNOWN_VPD_FIELD_DATA.get(key, None)
      value = rw_vpd[key]
      if (known_valid_values is not None) and (value not in known_valid_values):
        sys.exit('Invalid RW VPD entry : key %r, value %r' % (key, value))
    event_log.Log('vpd', ro_vpd=FilterDict(ro_vpd), rw_vpd=FilterDict(rw_vpd))
  map(hwid_tool.Validate.Status, options.status)

  if not options.hwid or not options.probe_results:
    main_fw_file = crosfw.LoadMainFirmware().GetFileName()

  if options.hwid:
    hwid_str = options.hwid
  else:
    gbb_result = Shell('gbb_utility -g --hwid %s' % main_fw_file).stdout
    hwid_str = re.findall(r'hardware_id:(.*)', gbb_result)[0].strip()
  hwid = hwid_tool.ParseHwid(hwid_str)
  hw_db = hwid_tool.HardwareDb(options.hwdb_path)
  print 'Verifying HWID: %r\n' % hwid.hwid
  device = hw_db.GetDevice(hwid.board)
  hwid_status = device.GetHwidStatus(hwid.bom, hwid.variant, hwid.volatile)
  if hwid_status not in options.status:
    sys.exit('HWID status must be one of [%s], found %r' %
             (', '.join(options.status), hwid_status))
  if options.probe_results:
    # Pull in probe results (including VPD data) from the given file
    # rather than probing the current system.
    probe_results = hwid_tool.ProbeResults.Decode(
        open(options.probe_results).read())
    ro_vpd = {}
    rw_vpd = {}
    for k, v in probe_results.found_volatile_values.items():
      match = re.match('^vpd\.(ro|rw)\.(\w+)$', k)
      if match:
        del probe_results.found_volatile_values[k]
        (ro_vpd if match.group(1) == 'ro' else rw_vpd)[match.group(2)] = v
  else:
    probe_results = Probe()
    ro_vpd = ReadRoVpd(main_fw_file)
    rw_vpd = ReadRwVpd(main_fw_file)
  cooked_components = hw_db.comp_db.MatchComponentProbeValues(
    probe_results.found_probe_value_map)
  cooked_volatiles = device.MatchVolatileValues(
    probe_results.found_volatile_values)
  cooked_initial_configs = device.MatchInitialConfigValues(
    probe_results.initial_configs)
  component_data = hwid_tool.ComponentData(
    extant_components=cooked_components.matched,
    classes_missing=probe_results.missing_component_classes)
  match_tree = device.BuildMatchTree(
    component_data, cooked_volatiles.matched_tags)
  matched_hwids = device.GetMatchTreeHwids(match_tree)
  print 'HWID status: %s\n' % hwid_status
  print 'probed system components:'
  print YamlWrite(cooked_components.__dict__)
  print 'missing component classes:'
  print YamlWrite(probe_results.missing_component_classes)
  print 'probed volatiles:'
  print YamlWrite(cooked_volatiles.__dict__)
  print 'probed initial_configs:'
  print YamlWrite(cooked_initial_configs)
  print 'hwid match tree:'
  print YamlWrite(match_tree)
  event_log.Log(
    'probe',
    found_components=cooked_components.__dict__,
    missing_component_classes=probe_results.missing_component_classes,
    volatiles=cooked_volatiles.__dict__,
    initial_configs=cooked_initial_configs)
  if hwid.hwid not in matched_hwids:
    err_msg = 'HWID verification FAILED.\n'
    if cooked_components.unmatched:
      sys.exit(err_msg + 'some components could not be indentified:\n%s' %
               YamlWrite(cooked_components.unmatched))
    if not match_tree:
      sys.exit(err_msg + 'no matching boms were found for components:\n%s' %
               component_data.Encode())
    if hwid.bom not in match_tree:
      sys.exit(err_msg + 'matching boms [%s] do not include target bom %r' %
               (', '.join(sorted(match_tree)), hwid.bom))
    err_msg += 'target bom %r matches components' % hwid.bom
    if hwid.bom not in device.IntersectBomsAndInitialConfigs(
      cooked_initial_configs):
      sys.exit(err_msg + ', but failed initial config verification')
    matched_variants = match_tree.get(hwid.bom, {})
    if hwid.variant not in matched_variants:
      sys.exit(err_msg + ', but target variant_code %r did not match' %
               hwid.variant)
    matched_volatiles = matched_variants.get(hwid.variant, {})
    if hwid.volatile not in matched_volatiles:
      sys.exit(err_msg + ', but target volatile_code %r did not match' %
               hwid.volatile)
    found_status = matched_volatiles.get(hwid.volatile, None)
    sys.exit(err_msg + ', but hwid status %r was unacceptable' % found_status)
  VerifyVpd(device.vpd_ro_fields, device.vpd_rw_fields)
  event_log.Log('verified_hwid', hwid=hwid)
  print 'Verification SUCCESS!'


@Command('verify_keys')
def VerifyKeys(options):  # pylint: disable=W0613
  """Verify keys in firmware and SSD match."""

  return GetGooftool(options).VerifyKeys()


@Command('set_fw_bitmap_locale')
def SetFirmwareBitmapLocale(options):  # pylint: disable=W0613
  """Use VPD locale value to set firmware bitmap default language."""

  (index, locale) = GetGooftool(options).SetFirmwareBitmapLocale()
  logging.info('Firmware bitmap initial locale set to %d (%s).',
               index, locale)


@Command('verify_system_time')
def VerifySystemTime(options):  # pylint: disable=W0613
  """Verify system time is later than release filesystem creation time."""

  return GetGooftool(options).VerifySystemTime()


@Command('verify_rootfs')
def VerifyRootFs(options):  # pylint: disable=W0613
  """Verify rootfs on SSD is valid by checking hash."""

  return GetGooftool(options).VerifyRootFs()


@Command('verify_switch_wp')
def VerifyWPSwitch(options):  # pylint: disable=W0613
  """Verify hardware write protection switch is enabled."""

  GetGooftool(options).VerifyWPSwitch()


@Command('verify_switch_dev')
def VerifyDevSwitch(options):  # pylint: disable=W0613
  """Verify developer switch is disabled."""

  if GetGooftool(options).CheckDevSwitchForDisabling():
    logging.warn('VerifyDevSwitch: No physical switch.')
    event_log.Log('switch_dev', type='virtual switch')


@Command('write_protect')
def EnableFwWp(options):  # pylint: disable=W0613
  """Enable then verify firmware write protection."""

  def CalculateLegacyRange(fw_type, length, section_data,
                           section_name):
    ro_size = length / 2
    ro_a = int(section_data[0] / ro_size)
    ro_b = int((section_data[0] + section_data[1] - 1) / ro_size)
    if ro_a != ro_b:
      raise Error("%s firmware section %s has illegal size" %
                  (fw_type, section_name))
    ro_offset = ro_a * ro_size
    return (ro_offset, ro_size)

  def WriteProtect(fw_file_path, fw_type, legacy_section):
    """Calculate protection size, then invoke flashrom.

    Our supported chips only allow write protecting half their total
    size, so we parition the flash chipset space accordingly.
    """

    raw_image = open(fw_file_path, 'rb').read()
    wp_section = 'WP_RO'
    image = crosfw.FirmwareImage(raw_image)
    if image.has_section(wp_section):
      section_data = image.get_section_area(wp_section)
      ro_offset = section_data[0]
      ro_size = section_data[1]
    elif image.has_section(legacy_section):
      section_data = image.get_section_area(legacy_section)
      (ro_offset, ro_size) = CalculateLegacyRange(
          fw_type, len(raw_image), section_data, legacy_section)
    else:
      raise Error('could not find %s firmware section %s or %s' %
                  (fw_type, wp_section, legacy_section))

    logging.debug('write protecting %s [off=%x size=%x]', fw_type,
                  ro_offset, ro_size)
    crosfw.Flashrom(fw_type).EnableWriteProtection(ro_offset, ro_size)

  WriteProtect(crosfw.LoadMainFirmware().GetFileName(), 'main', 'RO_SECTION')
  event_log.Log('wp', fw='main')
  ec_fw_file = crosfw.LoadEcFirmware().GetFileName()
  if ec_fw_file is not None:
    WriteProtect(ec_fw_file, 'ec', 'EC_RO')
    event_log.Log('wp', fw='ec')
  else:
    logging.warning('EC not write protected (seems there is no EC flash).')


@Command('clear_gbb_flags')
def ClearGBBFlags(options):  # pylint: disable=W0613
  """Zero out the GBB flags, in preparation for transition to release state.

  No GBB flags are set in release/shipping state, but they are useful
  for factory/development.  See "gbb_utility --flags" for details.
  """

  GetGooftool(options).ClearGBBFlags()
  event_log.Log('clear_gbb_flags')


@Command('clear_factory_vpd_entries')
def ClearFactoryVPDEntries(options):  # pylint: disable=W0613
  """Clears factory.* items in the RW VPD."""
  entries = GetGooftool(options).ClearFactoryVPDEntries()
  event_log.Log('clear_factory_vpd_entries', entries=FilterDict(entries))


@Command('prepare_wipe',
         CmdArg('--fast', action='store_true',
                help='use non-secure but faster wipe method.'))
def PrepareWipe(options):
  """Prepare system for transition to release state in next reboot."""

  GetGooftool(options).PrepareWipe(options.fast)

@Command('verify',
         CmdArg('--no_write_protect', action='store_true',
                help='Do not check write protection switch state.'),
         _hwid_status_list_cmd_arg,
         _hwdb_path_cmd_arg,
         _board_cmd_arg,
         _probe_results_cmd_arg,
         _hwid_cmd_arg)
def Verify(options):
  """Verifies if whole factory process is ready for finalization.

  This routine performs all the necessary checks to make sure the
  device is ready to be finalized, but does not modify state.  These
  checks include dev switch, firmware write protection switch, hwid,
  system time, keys, and root file system.
  """

  if not options.no_write_protect:
    VerifyWPSwitch(options)
  VerifyDevSwitch(options)
  if options.hwid_version == 2:
    VerifyHwid(options)
  elif options.hwid_version == 3:
    VerifyHwidV3(options)
  else:
    raise Error, 'Invalid HWID version: %r' % options.hwid_version
  VerifySystemTime(options)
  VerifyKeys(options)
  VerifyRootFs(options)


@Command('log_system_details')
def LogSystemDetails(options):  # pylint: disable=W0613
  """Write miscellaneous system details to the event log."""

  event_log.Log('system_details', **Gooftool(
      hwid_version=options.hwid_version).GetSystemDetails())


def CreateReportArchiveBlob(*args, **kwargs):
  """Creates a report archive and returns it as a blob.

  Args:
    See CreateReportArchive.

  Returns:
    An xmlrpclib.Binary object containing a .tar.xz file.
  """
  with open(CreateReportArchive(*args, **kwargs)) as f:
    return xmlrpclib.Binary(f.read())


def CreateReportArchive(device_sn=None, add_file=None):
  """Creates a report archive in a temporary directory.

  Args:
    device_sn: The device serial number (optional).
    add_file: A list of files to add (optional).

  Returns:
    Path to the archive.
  """
  def NormalizeAsFileName(token):
    return re.sub(r'\W+', '', token).strip()

  target_name = '%s%s.tar.xz' % (
      time.strftime('%Y%m%dT%H%M%SZ',
                    time.gmtime()),
      ("" if device_sn is None else
       "_" + NormalizeAsFileName(device_sn)))
  target_path = os.path.join(gettempdir(), target_name)

  # Intentionally ignoring dotfiles in EVENT_LOG_DIR.
  tar_cmd = 'cd %s ; tar cJf %s *' % (event_log.EVENT_LOG_DIR, target_path)
  tar_cmd += ' --add-file %s' % FACTORY_LOG_PATH
  if add_file:
    for f in add_file:
      # Require absolute paths since the tar command may change the
      # directory.
      if not f.startswith('/'):
        raise Error('Not an absolute path: %s' % f)
      if not os.path.exists(f):
        raise Error('File does not exist: %s' % f)
      tar_cmd += ' --add-file %s' % pipes.quote(f)
  cmd_result = Shell(tar_cmd)

  if ((cmd_result.status == 1) and
      all((x == '' or
           'file changed as we read it' in x or
           "Removing leading `/' from member names" in x)
          for x in cmd_result.stderr.split('\n'))):
    # That's OK.  Make sure it's valid though.
    Spawn(['tar', 'tfJ', target_path], check_call=True, log=True,
          ignore_stdout=True)
  elif not cmd_result.success:
    raise Error('unable to tar event logs, cmd %r failed, stderr: %r' %
                (tar_cmd, cmd_result.stderr))

  return target_path

_upload_method_cmd_arg = CmdArg(
    '--upload_method', metavar='METHOD:PARAM',
    help=('How to perform the upload.  METHOD should be one of '
          '{ftp, shopfloor, ftps, cpfe}.'))
_add_file_cmd_arg = CmdArg(
    '--add_file', metavar='FILE', action='append',
    help='Extra file to include in report (must be an absolute path)')

@Command('upload_report',
         _upload_method_cmd_arg,
         _add_file_cmd_arg)
def UploadReport(options):
  """Create a report containing key device details."""
  ro_vpd = ReadRoVpd(crosfw.LoadMainFirmware().GetFileName())
  device_sn = ro_vpd.get('serial_number', None)
  if device_sn is None:
    logging.warning('RO_VPD missing device serial number')
    device_sn = 'MISSING_SN_' + event_log.TimedUuid()
  target_path = CreateReportArchive(device_sn)

  if options.upload_method is None or options.upload_method == 'none':
    logging.warning('REPORT UPLOAD SKIPPED (report left at %s)', target_path)
    return
  method, param = options.upload_method.split(':', 1)
  if method == 'shopfloor':
    report_upload.ShopFloorUpload(target_path, param)
  elif method == 'ftp':
    report_upload.FtpUpload(target_path, 'ftp:' + param)
  elif method == 'ftps':
    report_upload.CurlUrlUpload(target_path, '--ftp-ssl-reqd ftp:%s' % param)
  elif method == 'cpfe':
    report_upload.CpfeUpload(target_path, pipes.quote(param))
  else:
    raise Error('unknown report upload method %r', method)


@Command('finalize',
         CmdArg('--no_write_protect', action='store_true',
                help='Do not enable firmware write protection.'),
         CmdArg('--fast', action='store_true',
                help='use non-secure but faster wipe method.'),
         _hwdb_path_cmd_arg,
         _hwid_status_list_cmd_arg,
         _upload_method_cmd_arg,
         _add_file_cmd_arg,
         _board_cmd_arg,
         _probe_results_cmd_arg,
         _hwid_cmd_arg)
def Finalize(options):
  """Verify system readiness and trigger transition into release state.

  This routine does the following:
  - Verifies system state (see verify command)
  - Modifies firmware bitmaps to match locale
  - Clears all factory-friendly flags from the GBB
  - Removes factory-specific entries from RW_VPD (factory.*)
  - Enables firmware write protection (cannot rollback after this)
  - Uploads system logs & reports
  - Sets the necessary boot flags to cause wipe of the factory image on the
    next boot.
  """
  Verify(options)
  SetFirmwareBitmapLocale(options)
  ClearGBBFlags(options)
  ClearFactoryVPDEntries(options)
  if options.no_write_protect:
    logging.warn('WARNING: Firmware Write Protection is SKIPPED.')
    event_log.Log('wp', fw='both', status='skipped')
  else:
    EnableFwWp({})
  LogSystemDetails(options)
  UploadReport(options)
  PrepareWipe(options)


@Command('verify_components_v3',
         _board_cmd_arg,
         _hwdb_path_cmd_arg,
         CmdArg('target_comps', nargs='*'))
def VerifyComponentsV3(options):
  """Verify that probeable components all match entries in the component_db.

  This method uses the HWIDv3 component database to verify components.

  Probe for each component class in the target_comps and verify
  that a corresponding match exists in the component_db -- make sure
  that these components are present, that they have been approved, but
  do not check against any specific BOM/HWID configurations.
  """

  result = GetGooftool(options).VerifyComponentsV3(options.target_comps)
  PrintVerifyComponentsResults(result)


@Command('generate_hwid_v3',
         _board_cmd_arg,
         _hwdb_path_cmd_arg,
         _probe_results_cmd_arg,
         _device_info_cmd_arg)
def GenerateHwidV3(options):
  """Generates the HWID of the DUT.

  The HWID is generated based on the given device info and the probe results
  retrieved by probing the DUT. If there are conflits of component information
  between device info and probe result, priority is given to device info.
  """
  try:
    with open(options.device_info) as f:
      device_info = yaml.load(f.read())
  except Exception, e:
    raise Error, 'Invalid device_info: %s' % e
  if options.probe_results:
    with open(options.probe_results) as f:
      probe_results = hwid_tool.ProbeResults.Decode(f.read())
  else:
    probe_results = Probe()
  print 'device_info:'
  print device_info
  print 'probe results:'
  print probe_results.Encode()

  # Do not log device_info for now until we're sure that it does not contain
  # any sensitive infomation.
  # TODO(jcliang): Add logging for device_info when appropriate.

  event_log.Log(
    'probe',
    found_components=probe_results.found_probe_value_map,
    missing_component_classes=probe_results.missing_component_classes,
    volatiles=probe_results.found_volatile_values,
    initial_configs=probe_results.initial_configs)

  hwid_object = GetGooftool(options).GenerateHwidV3(
      device_info, probe_results)

  final_bom = {}
  for component_class, component_values in (
      hwid_object.bom.components.iteritems()):
    final_bom[component_class] = [v.probed_values for v in component_values]
  event_log.Log(
    'final_bom',
    final_bom=final_bom)
  event_log.Log(
    'generated_hwid',
    encoded_string=hwid_object.encoded_string,
    binary_string=hwid_object.binary_string)
  print 'Encoded HWID string:', hwid_object.encoded_string
  print 'Binary HWID string:', hwid_object.binary_string


@Command('verify_hwid_v3',
         _board_cmd_arg,
         _hwdb_path_cmd_arg,
         _probe_results_cmd_arg,
         _hwid_cmd_arg)
def VerifyHwidV3(options):
  """Verify system HWID properties match probed device properties.

  First probe components, volatile and initial_config parameters for
  the DUT.  Then use the available device data to produce a list of
  candidate HWIDs.  Then verify the HWID from the DUT is present in
  that list.  Then verify that the DUT initial config values match
  those specified for its HWID.  Finally, verify that VPD contains all
  the necessary fields as specified by the board data, and when
  possible verify that values are legitimate.
  """
  if not options.probe_results:
    main_fw_file = crosfw.LoadMainFirmware().GetFileName()
  if options.hwid:
    hwid_str = options.hwid
  else:
    gbb_result = Shell('gbb_utility -g --hwid %s' % main_fw_file).stdout
    hwid_str = re.findall(r'hardware_id:(.*)', gbb_result)[0].strip()
  print 'Verifying HWID: %r\n' % hwid_str
  if options.probe_results:
    # Pull in probe results (including VPD data) from the given file
    # rather than probing the current system.
    with open(options.probe_results) as f:
      probe_results = hwid_tool.ProbeResults.Decode(f.read())
    probed_ro_vpd = {}
    probed_rw_vpd = {}
    for k, v in probe_results.found_volatile_values.items():
      # Use items(), not iteritems(), since we will be modifying the dict in the
      # loop.
      match = re.match('^vpd\.(ro|rw)\.(\w+)$', k)
      if match:
        del probe_results.found_volatile_values[k]
        (probed_ro_vpd if match.group(1) == 'ro'
            else probed_rw_vpd)[match.group(2)] = v
  else:
    probe_results = Probe()
    probed_ro_vpd = ReadRoVpd(main_fw_file)
    probed_rw_vpd = ReadRwVpd(main_fw_file)
  print 'probe result:'
  print probe_results.Encode()
  event_log.Log(
    'probe',
    found_components=probe_results.found_probe_value_map,
    missing_component_classes=probe_results.missing_component_classes,
    volatiles=probe_results.found_volatile_values,
    initial_configs=probe_results.initial_configs)
  event_log.Log('vpd', probed_ro_vpd=FilterDict(probed_ro_vpd),
                 probed_rw_vpd=FilterDict(probed_rw_vpd))

  GetGooftool(options).VerifyHwidV3(
      hwid_str, probe_results, probed_ro_vpd, probed_rw_vpd)

  event_log.Log('verified_hwid', hwid=hwid_str)
  print 'Verification SUCCESS!'


def ParseDecodedHWID(hwid):
  """Parse the HWID object into a more compact dict.

  Args:
    hwid: A decoded HWID object.

  Returns:
    A dict containing the board name, the binary string, and the list of
    components.
  """
  results = {}
  results['board'] = hwid.database.board
  results['binary_string'] = hwid.binary_string
  results['components'] = collections.defaultdict(list)
  components = hwid.bom.components
  for comp_cls in sorted(components):
    for (comp_name, probed_values, _) in sorted(components[comp_cls]):
      if not probed_values:
        db_components = hwid.database.components
        probed_values = db_components.GetComponentAttributes(
            comp_cls, comp_name).get('values')
      results['components'][comp_cls].append(
          {comp_name: probed_values if probed_values else None})
  # Convert defaultdict to dict.
  results['components'] = dict(results['components'])
  return results


@Command('decode_hwid_v3',
         _board_cmd_arg,
         _hwdb_path_cmd_arg,
         _hwid_cmd_arg)
def DecodeHwidV3(options):
  """Decodes the given v3 HWID and prints out decoded information.

  If no HWID is given, the HWID stored on the device will be loaded and used
  instead.
  """
  decoded_hwid_context = Gooftool(hwid_version=3, board=options.board,
                                  hwdb_path=options.hwdb_path).DecodeHwidV3(
                                      options.hwid)
  print yaml.dump(ParseDecodedHWID(decoded_hwid_context),
                  default_flow_style=False)


def Main():
  """Run sub-command specified by the command line args."""

  options = ParseCmdline(
      'Perform Google required factory tests.',
      CmdArg('-l', '--log', metavar='PATH',
             help='Write logs to this file.'),
      CmdArg('--suppress-event-logs', action='store_true',
             help='Suppress event logging.'),
      CmdArg('-i', '--hwid-version', default=3, choices=[2, 3], type=int,
             help='Version of HWID to operate on.'),
      verbosity_cmd_arg)
  SetupLogging(options.verbosity, options.log)
  event_log.SetGlobalLoggerDefaultPrefix('gooftool')
  event_log.GetGlobalLogger().suppress = options.suppress_event_logs
  logging.debug('gooftool options: %s', repr(options))
  try:
    logging.debug('GOOFTOOL command %r', options.command_name)
    options.command(options)
    logging.info('GOOFTOOL command %r SUCCESS', options.command_name)
  except Error, e:
    logging.exception(e)
    sys.exit('GOOFTOOL command %r ERROR: %s' % (options.command_name, e))
  except Exception, e:
    logging.exception(e)
    sys.exit('UNCAUGHT RUNTIME EXCEPTION %s' % e)


if __name__ == '__main__':
  Main()
