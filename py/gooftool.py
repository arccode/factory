#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Google Factory Tool.

This tool is indended to be used on factory assembly lines.  It
provides all of the Google required test functionality and must be run
on each device as part of the assembly process.
"""


import logging
import os
import re
import sys

import bmpblk
import crosfw
import hwid_tool
import probe
import report
import report_upload
import vpd_data

from common import Error, ParseKeyValueData, SetupLogging, Shell, YamlWrite
from hacked_argparse import CmdArg, Command, ParseCmdline, verbosity_cmd_arg
from tempfile import NamedTemporaryFile


def GetPrimaryDevicePath(partition=None):
  def IsFixed(dev):
    sysfs_path = '/sys/block/%s/removable' % dev
    return (os.path.exists(sysfs_path) and
            open(sysfs_path).read().strip() == '0')
  alpha_re = re.compile(r'^/dev/([a-zA-Z]+)[0-9]+$')
  alnum_re = re.compile(r'^/dev/([a-zA-Z]+[0-9]+)p[0-9]+$')
  matched_alnum = False
  dev_set = set()
  for path in Shell('cgpt find -t rootfs').stdout.strip().split():
    for dev in alpha_re.findall(path):
      if IsFixed(dev):
        dev_set.add(dev)
        matched_alnum = False
    for dev in alnum_re.findall(path):
      if IsFixed(dev):
        dev_set.add(dev)
        matched_alnum = True
  if len(dev_set) != 1:
    raise Error('zero or multiple primary devs: %s' % dev_set)
  dev_path = os.path.join('/dev', dev_set.pop())
  if partition is None:
    return dev_path
  fmt_str = '%sp%d' if matched_alnum else '%s%d'
  return fmt_str % (dev_path, partition)


def GetReleaseRootPartitionPath():
  return GetPrimaryDevicePath(5)


def GetReleaseKernelPartitionPath():
  return GetPrimaryDevicePath(4)


def FindScript(script_name):
  script_path = os.path.join(os.path.dirname(sys.path[0]), 'sh', script_name)
  if not os.path.exists(script_path):
    raise Error('Needed script %s does not exist.' % script_path)
  return script_path


def ReadRoVpd(fw_image_file):
  raw_vpd_data = Shell('vpd -i RO_VPD -l -f %s' % fw_image_file).stdout
  return ParseKeyValueData('"(.*)"="(.*)"$', raw_vpd_data)


@Command('write_hwid',
         CmdArg('hwid', metavar='HWID', help='HWID string'))
def WriteHwid(options):
  """Write specified HWID value into the system BB."""
  logging.debug('writing hwid string %r', options.hwid)
  main_fw = crosfw.LoadMainFirmware()
  Shell('gbb_utility --set --hwid="%s" "%s"' %
        (options.hwid, main_fw.GetFileName()))
  main_fw.Write(sections=['GBB'])


@Command('probe',
         CmdArg('--comps', nargs='*',
                help='List of keys from the component_db registry.'),
         CmdArg('--no_vol', action='store_true',
                help='Do not probe volatile data.'),
         CmdArg('--no_ic', action='store_true',
                help='Do not probe initial_config data.'))
def RunProbe(options):
  """Print yaml-formatted breakdown of probed device properties."""
  probe_results = probe.Probe(target_comp_classes=options.comps,
                              probe_volatile=not options.no_vol,
                              probe_initial_config=not options.no_ic)
  print YamlWrite(probe_results.__dict__)


_hwdb_path_cmd_arg = CmdArg(
    '--hwdb_path', metavar='PATH',
    default=hwid_tool.DEFAULT_HWID_DATA_PATH,
    help='Path to the HWID database.')


@Command('verify_hwid',
         _hwdb_path_cmd_arg)
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
  hwdb = hwid_tool.ReadDatastore(options.hwdb_path)
  main_fw_file = crosfw.LoadMainFirmware().GetFileName()
  gbb_result = Shell('gbb_utility -g --hwid %s' % main_fw_file).stdout
  hwid = re.findall(r'hardware_id:(.*)', gbb_result)[0].strip()
  hwid_properties = hwid_tool.LookupHwidProperties(hwdb, hwid)
  logging.info('Verifying system HWID: %r', hwid_properties.hwid)
  logging.debug('expected system properties:\n%s',
                YamlWrite(hwid_properties.__dict__))
  probe_results = probe.Probe()
  cooked_results = hwid_tool.CookProbeResults(
      hwdb, probe_results, hwid_properties.board)
  logging.debug('found system properties:\n%s',
                YamlWrite(cooked_results.__dict__))
  # TODO(tammo): Output a new-style log event with device details here.
  match_errors = []
  for comp_class, expected_name in hwid_properties.component_map.items():
    if expected_name == 'ANY':
      continue
    if expected_name == cooked_results.matched_components.get(comp_class, None):
      continue
    if comp_class in probe_results.missing_components:
      match_errors.append('  %s component mismatch, expected %s, found nothing'
                          % (comp_class, expected_name))
    else:
      probe_value = probe_results.found_components.get(comp_class, None)
      match_errors.append('  %s component mismatch, expected %s, found  %r' %
                          (comp_class, expected_name, probe_value))
  if match_errors:
    raise Error('HWID verification FAILED.\n%s' % '\n'.join(match_errors))
  if hwid_properties.volatile not in cooked_results.matched_volatile_tags:
    msg = ('  HWID specified volatile %s, but found match only for %s' %
           (hwid_properties.volatile,
            ', '.join(cooked_results.matched_volatile_tags)))
    raise Error('HWID verification FAILED.\n%s' % msg)
  if (hwid_properties.initial_config is not None and
      hwid_properties.initial_config not in
      cooked_results.matched_initial_config_tags):
    msg = ('  HWID specified initial_config %s, but only found match for [%s]' %
           (hwid_properties.initial_config,
            ', '.join(cooked_results.matched_initial_config_tags)))
    raise Error('HWID verification FAILED.\n%s' % msg)
  # TODO(tammo): Verify HWID status is supported (or deprecated for RMA).
  ro_vpd = ReadRoVpd(main_fw_file)
  for field in hwid_properties.vpd_ro_field_list:
    if field not in ro_vpd:
      raise Error('Missing required VPD field: %s' % field)
    known_valid_values = vpd_data.KNOWN_VPD_FIELD_DATA.get(field, None)
    value = ro_vpd[field]
    if known_valid_values is not None and value not in known_valid_values:
      raise Error('Invalid VPD entry : field %r, value %r' % (field, value))


@Command('verify_keys')
def VerifyKeys(options):
  """Verify keys in firmware and SSD match."""
  script = FindScript('verify_keys.sh')
  kernel_device = GetReleaseKernelPartitionPath()
  main_fw_file = crosfw.LoadMainFirmware().GetFileName()
  result = Shell('%s %s %s' % (script, kernel_device, main_fw_file))
  if not result.success:
    raise Error, '%r failed, stderr: %r' % (script, result.stderr)


@Command('set_fw_bitmap_locale')
def SetFirmwareBitmapLocale(options):
  """Use VPD locale value to set firmware bitmap default language."""
  image_file = crosfw.LoadMainFirmware().GetFileName()
  locale = ReadRoVpd(image_file).get('initial_locale', None)
  if locale is None:
    raise Error, 'Missing initial_locale VPD.'
  bitmap_locales = []
  with NamedTemporaryFile() as f:
    Shell('gbb_utility -g --bmpfv=%s %s' % (f.name, image_file))
    bmpblk_data = bmpblk.unpack_bmpblock(f.read())
    bitmap_locales = bmpblk_data.get('locales', bitmap_locales)
  # Some locale values are just a language code and others are a
  # hyphen-separated language code and country code pair.  We care
  # only about the language code part.
  language_code = locale.partition('-')[0]
  if language_code not in bitmap_locales:
    raise Error, ('Firmware bitmaps do not contain support for the specified '
                  'initial locale language %r' % language_code)
  else:
    locale_index = bitmap_locales.index(language_code)
    logging.info('Firmware bitmap initial locale set to %d (%s).',
                 locale_index, bitmap_locales[locale_index])
    Shell('crossystem loc_idx=%d' % locale_index)


@Command('verify_system_time')
def VerifySystemTime(options):
  """Verify system time is later than release filesystem creation time."""
  script = FindScript('verify_system_time.sh')
  rootfs_device = GetReleaseRootPartitionPath()
  result = Shell('%s %s' % (script, rootfs_device))
  if not result.success:
    raise Error, '%r failed, stderr: %r' % (script, result.stderr)


@Command('verify_rootfs')
def VerifyRootFs(options):
  """Verify rootfs on SSD is valid by checking hash."""
  script = FindScript('verify_rootfs.sh')
  rootfs_device = GetReleaseRootPartitionPath()
  result = Shell('%s %s' % (script, rootfs_device))
  if not result.success:
    raise Error, '%r failed, stderr: %r' % (script, result.stderr)


@Command('verify_switch_wp')
def VerifyWpSwitch(options):
  """Verify hardware write protection switch is enabled."""
  if Shell('crossystem wpsw_cur').stdout.strip() != '1':
    raise Error, 'write protection is disabled'


@Command('verify_switch_dev')
def VerifyDevSwitch(options):
  """Verify developer switch is disabled."""
  if Shell('crossystem devsw_cur').stdout.strip() != '0':
    raise Error, 'developer mode is enabled'


@Command('write_protect')
def EnableFwWp(options):
  """Enable then verify firmware write protection."""

  def WriteProtect(fw_file_path, fw_type, section):
    """Calculate protection size, then invoke flashrom.

    Our supported chips only allow write protecting half their total
    size, so we parition the flash chipset space accordingly.
    """
    raw_image = open(fw_file_path, 'rb').read()
    image = crosfw.FirmwareImage(raw_image)
    if not image.has_section(section):
      raise Error('could not find %s firmware section %s' % (fw_type, section))
    section_data = image.get_section_area(section)
    protectable_size = len(raw_image) / 2
    ro_a = int(section_data[0] / protectable_size)
    ro_b = int((section_data[0] + section_data[1] - 1) / protectable_size)
    if ro_a != ro_b:
      raise Error("%s firmware section %s has illegal size" %
                  (fw_type, section))
    ro_offset = ro_a * protectable_size
    logging.debug('write protecting %s', fw_type)
    crosfw.Flashrom(fw_type).EnableWriteProtection(ro_offset, protectable_size)

  WriteProtect(crosfw.LoadMainFirmware().GetFileName(), 'main', 'RO_SECTION')
  ec_fw_file = crosfw.LoadEcFirmware().GetFileName()
  if ec_fw_file is not None:
    WriteProtect(ec_fw_file, 'ec', 'EC_RO')
  else:
    logging.warning('EC not write protected (seems there is no EC flash).')


@Command('clear_gbb_flags')
def ClearGbbFlags(options):
  """Zero out the GBB flags, in preparation for transition to release state.

  No GBB flags are set in release/shipping state, but they are useful
  for factory/development.  See "gbb_utility --flags" for details.
  """
  script = FindScript('clear_gbb_flags.sh')
  result = Shell(script)
  if not result.success:
    raise Error, '%r failed, stderr: %r' % (script, result.stderr)


@Command('prepare_wipe',
         CmdArg('--fast', action='store_true',
                help='use non-secure but faster wipe method.'))
def PrepareWipe(options):
  """Prepare system for transition to release state in next reboot."""
  script = FindScript('prepare_wipe.sh')
  tag = 'fast' if options.fast else ''
  rootfs_device = GetReleaseRootPartitionPath()
  result = Shell('FACTORY_WIPE_TAGS=%s %s %s' % (tag, script, rootfs_device))
  if not result.success:
    raise Error, '%r failed, stderr: %r' % (script, result.stderr)


@Command('verify',
         CmdArg('--dev', action='store_true',
                help='Do not verify switch state (dev mode and fw wp).'),
         _hwdb_path_cmd_arg)
def Verify(options):
  """Verifies if whole factory process is ready for finalization.

  This routine performs all the necessary checks to make sure the
  device is ready to be finalized, but does not modify state.  These
  checks include dev switch, firmware write protection switch, hwid,
  system time, keys, and root file system.
  """
  if not options.dev:
    VerifyDevSwitch({})
    VerifyWpSwitch({})
  VerifyHwid(options)
  VerifySystemTime({})
  VerifyKeys({})
  VerifyRootFs({})


_upload_method_cmd_arg = CmdArg(
    '--upload_method', metavar='METHOD:PARAM',
    help=('How to perform the upload.  METHOD should be one of '
          '{ftp, shopfloor, curl, cpfe, custom}.'))


@Command('upload_report',
         _upload_method_cmd_arg)
def UploadReport(options):
  """Create and a report containing key device details."""
  report_upload.Upload(report.Create(options.log), options.upload_method)


@Command('finalize',
         CmdArg('--dev', action='store_true',
                help='Do not verify or alter write protection or dev mode.'),
         CmdArg('--fast', action='store_true',
                help='use non-secure but faster wipe method.'),
         _hwdb_path_cmd_arg,
         _upload_method_cmd_arg)
def Finalize(options):
  """Verify system readiness and trigger transition into release state.

  This routine first verifies system state (see verify command), then
  clears all of the testing flags from the GBB, then modifies firmware
  bitmaps to match locale.  Then it enables firmware write protection
  and sets the necessary boot flags to cause wipe of the factory image
  on the next boot.
  """
  ClearGbbFlags({})
  Verify(options)
  SetFirmwareBitmapLocale({})
  if not options.dev:
    EnableFwWp({})
  UploadReport(options)
  PrepareWipe(options)


def Main():
  """Run sub-command specified by the command line args."""
  options = ParseCmdline(
      'Perform Google required factory tests.',
      CmdArg('-l', '--log', metavar='PATH',
             help='Write logs to this file.'),
      verbosity_cmd_arg
      )
  SetupLogging(options.verbosity, options.log)
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
