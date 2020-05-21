#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Google Factory Tool.

This tool is intended to be used on factory assembly lines.  It
provides all of the Google required test functionality and must be run
on each device as part of the assembly process.
"""

from __future__ import print_function

import logging
import os
import pipes
import re
import sys
from tempfile import gettempdir
import threading
import time
import xmlrpc.client

from cros.factory.gooftool.common import ExecFactoryPar
from cros.factory.gooftool.common import Shell
from cros.factory.gooftool.core import Gooftool
from cros.factory.gooftool import crosfw
from cros.factory.gooftool import report_upload
from cros.factory.gooftool import vpd
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.probe.functions import chromeos_firmware
from cros.factory.test.env import paths
from cros.factory.test import event_log
from cros.factory.test.rules import phase
from cros.factory.test.rules.privacy import FilterDict
from cros.factory.test import state
from cros.factory.utils import argparse_utils
from cros.factory.utils.argparse_utils import CmdArg
from cros.factory.utils.argparse_utils import ParseCmdline
from cros.factory.utils.argparse_utils import VERBOSITY_CMD_ARG
from cros.factory.utils.debug_utils import SetupLogging
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils import sys_utils
from cros.factory.utils import time_utils
from cros.factory.utils.type_utils import Error


# TODO(tammo): Replace calls to sys.exit with raise Exit, and maybe
# treat that specially (as a smoot exit, as opposed to the more
# verbose output for generic Error).

_global_gooftool = None
_gooftool_lock = threading.Lock()
_has_fpmcu = None


def GetGooftool(options):
  global _global_gooftool  # pylint: disable=global-statement

  if _global_gooftool is None:
    with _gooftool_lock:
      if _global_gooftool is None:
        project = getattr(options, 'project', None)
        hwdb_path = getattr(options, 'hwdb_path', None)
        _global_gooftool = Gooftool(hwid_version=3, project=project,
                                    hwdb_path=hwdb_path)

  return _global_gooftool

def HasFpmcu():
  global _has_fpmcu  # pylint: disable=global-statement

  if _has_fpmcu is None:
    FPMCU_PATH = '/dev/cros_fp'
    has_fpmcu_path = os.path.exists(FPMCU_PATH)
    has_cros_config_fpmcu = False
    cros_config_output = Shell(['cros_config', '/fingerprint', 'board'])
    if cros_config_output.success and cros_config_output.stdout:
      has_cros_config_fpmcu = True

    if has_fpmcu_path is False and has_cros_config_fpmcu is True:
      raise Error('FPMCU found in cros_config but missing in %s.' % FPMCU_PATH)
    if has_fpmcu_path is True and has_cros_config_fpmcu is False:
      raise Error('FPMCU found in %s but missing in cros_config.' % FPMCU_PATH)

    _has_fpmcu = has_fpmcu_path

  return _has_fpmcu

def Command(cmd_name, *args, **kwargs):
  """Decorator for commands in gooftool.

  This is similar to argparse_utils.Command, but all gooftool commands
  can be waived during `gooftool finalize` or `gooftool verify` using
  --waive_list or --skip_list option.
  """
  def Decorate(fun):
    def CommandWithWaiveSkipCheck(options):
      waive_list = vars(options).get('waive_list', [])
      skip_list = vars(options).get('skip_list', [])
      if phase.GetPhase() >= phase.PVT_DOGFOOD and (
          waive_list != [] or skip_list != []):
        raise Error(
            'waive_list and skip_list should be empty for phase %s' %
            phase.GetPhase())

      if cmd_name not in skip_list:
        try:
          fun(options)
        except Exception as e:
          if cmd_name in waive_list:
            logging.exception(e)
          else:
            raise

    return argparse_utils.Command(cmd_name, *args, **kwargs)(
        CommandWithWaiveSkipCheck)
  return Decorate


@Command('write_hwid',
         CmdArg('hwid', metavar='HWID', help='HWID string'))
def WriteHWID(options):
  """Write specified HWID value into the system BB."""

  logging.info('writing hwid string %r', options.hwid)
  GetGooftool(options).WriteHWID(options.hwid)
  event_log.Log('write_hwid', hwid=options.hwid)
  print('Wrote HWID: %r' % options.hwid)


@Command('read_hwid')
def ReadHWID(options):
  """Read the HWID string from GBB."""

  logging.info('reading the hwid string')
  print(GetGooftool(options).ReadHWID())


_project_cmd_arg = CmdArg(
    '--project', metavar='PROJECT',
    default=None, help='Project name to test.')

_hwdb_path_cmd_arg = CmdArg(
    '--hwdb_path', metavar='PATH',
    default=hwid_utils.GetDefaultDataPath(),
    help='Path to the HWID database.')

_hwid_status_list_cmd_arg = CmdArg(
    '--status', nargs='*', default=['supported'],
    help='allow only HWIDs with these status values')

_probe_results_cmd_arg = CmdArg(
    '--probe_results', metavar='RESULTS.json',
    help=('Output from "hwid probe" (used instead of probing this system).'))

_device_info_cmd_arg = CmdArg(
    '--device_info', metavar='DEVICE_INFO.yaml', default=None,
    help='A dict of device info to use instead of fetching from shopfloor '
    'server.')

_hwid_cmd_arg = CmdArg(
    '--hwid', metavar='HWID',
    help='HWID to verify (instead of the currently set HWID of this system).')

_hwid_run_vpd_cmd_arg = CmdArg(
    '--hwid-run-vpd', action='store_true',
    help=('Specify the hwid utility to obtain the vpd data by running the '
          '`vpd` commandline tool.'))

_hwid_vpd_data_file_cmd_arg = CmdArg(
    '--hwid-vpd-data-file', metavar='FILE.json', type=str, default=None,
    help=('Specify the hwid utility to obtain the vpd data from the specified '
          'file.'))

_rma_mode_cmd_arg = CmdArg(
    '--rma_mode', action='store_true',
    help='Enable RMA mode, do not check for deprecated components.')

_cros_core_cmd_arg = CmdArg(
    '--cros_core', action='store_true',
    help='Finalize for ChromeOS Core devices (may add or remove few test '
         'items. For example, registration codes or firmware bitmap '
         'locale settings).')

_has_ec_pubkey_cmd_arg = CmdArg(
    '--has_ec_pubkey', action='store_true', default=None,
    help='The device has EC public key for EFS and need to run VerifyECKey.')

_enforced_release_channels_cmd_arg = CmdArg(
    '--enforced_release_channels', nargs='*', default=None,
    help='Enforced release image channels.')

_ec_pubkey_path_cmd_arg = CmdArg(
    '--ec_pubkey_path',
    default=None,
    help='Path to public key in vb2 format. Verify EC key with pubkey file.')

_ec_pubkey_hash_cmd_arg = CmdArg(
    '--ec_pubkey_hash',
    default=None,
    help='A string for public key hash. Verify EC key with the given hash.')

_release_rootfs_cmd_arg = CmdArg(
    '--release_rootfs', help='Location of release image rootfs partition.')

_firmware_path_cmd_arg = CmdArg(
    '--firmware_path', help='Location of firmware image partition.')

_shopfloor_url_args_cmd_arg = CmdArg(
    '--shopfloor_url',
    help='Shopfloor server url to be informed when wiping is done. '
         'After wiping, a XML-RPC request will be sent to the '
         'given url to indicate the completion of wiping.')

_station_ip_cmd_arg = CmdArg(
    '--station_ip',
    help='IP of remote station')

_station_port_cmd_arg = CmdArg(
    '--station_port',
    help='Port on remote station')

_wipe_finish_token_cmd_arg = CmdArg(
    '--wipe_finish_token',
    help='Required token when notifying station after wipe finished')

_keep_developer_mode_flag_after_clobber_state_cmd_arg = CmdArg(
    # The argument name is super long because you should never use it by
    # yourself when using command line tools.
    '--keep_developer_mode_flag_after_clobber_state',
    action='store_true', default=None,
    help='After clobber-state, do not delete .developer_mode')

_waive_list_cmd_arg = CmdArg(
    '--waive_list', nargs='*', default=[], metavar='SUBCMD',
    help='A list of waived checks, separated by whitespace. '
         'Each item should be a sub-command of gooftool. '
         'e.g. "gooftool verify --waive_list verify_tpm clear_gbb_flags".')

_skip_list_cmd_arg = CmdArg(
    '--skip_list', nargs='*', default=[], metavar='SUBCMD',
    help='A list of skipped checks, separated by whitespace. '
         'Each item should be a sub-command of gooftool. '
         'e.g. "gooftool verify --skip_list verify_tpm clear_gbb_flags".')

_test_umount_cmd_arg = CmdArg(
    '--test_umount', action='store_true',
    help='(For testing only) Only umount rootfs and stateful partition '
         'instead of running full wiping and cutoff process.')

_rlz_embargo_end_date_offset_cmd_arg = CmdArg(
    '--embargo_offset', type=int, default=7, choices=list(range(7, 15)),
    help='Change the offset of embargo end date, cannot less than 7 days or '
         'more than 14 days.')

_no_ectool_cmd_arg = CmdArg(
    '--no_ectool', action='store_false', dest='has_ectool',
    help='There is no ectool utility so tests rely on ectool should be '
         'skipped.')

_no_generate_mfg_date_cmd_arg = CmdArg(
    '--no_generate_mfg_date', action='store_false', dest='generate_mfg_date',
    help='Do not generate manufacturing date nor write mfg_date into VPD.')

_enable_zero_touch_cmd_arg = CmdArg(
    '--enable_zero_touch', action='store_true',
    help='Set attested_device_id for zero-touch feature.')


@Command(
    'verify_ec_key',
    _ec_pubkey_path_cmd_arg,
    _ec_pubkey_hash_cmd_arg)
def VerifyECKey(options):
  """Verify EC key."""
  return GetGooftool(options).VerifyECKey(
      options.ec_pubkey_path, options.ec_pubkey_hash)


@Command('verify_keys',
         _release_rootfs_cmd_arg,
         _firmware_path_cmd_arg)
def VerifyKeys(options):
  """Verify keys in firmware and SSD match."""
  return GetGooftool(options).VerifyKeys(
      options.release_rootfs, options.firmware_path)


@Command('set_fw_bitmap_locale')
def SetFirmwareBitmapLocale(options):
  """Use VPD locale value to set firmware bitmap default language."""

  (index, locale) = GetGooftool(options).SetFirmwareBitmapLocale()
  logging.info('Firmware bitmap initial locale set to %d (%s).',
               index, locale)


@Command('verify_system_time',
         _release_rootfs_cmd_arg,
         _rma_mode_cmd_arg)
def VerifySystemTime(options):
  """Verify system time is later than release filesystem creation time."""

  return GetGooftool(options).VerifySystemTime(options.release_rootfs,
                                               rma_mode=options.rma_mode)


@Command('verify_rootfs',
         _release_rootfs_cmd_arg)
def VerifyRootFs(options):
  """Verify rootfs on SSD is valid by checking hash."""

  return GetGooftool(options).VerifyRootFs(options.release_rootfs)


@Command('verify_tpm')
def VerifyTPM(options):
  """Verify TPM is cleared."""

  return GetGooftool(options).VerifyTPM()


@Command('verify_me_locked')
def VerifyManagementEngineLocked(options):
  """Verify Management Engine is locked."""

  return GetGooftool(options).VerifyManagementEngineLocked()


@Command('verify_switch_wp',
         _no_ectool_cmd_arg)
def VerifyWPSwitch(options):
  """Verify hardware write protection switch is enabled."""

  GetGooftool(options).VerifyWPSwitch(options.has_ectool)


@Command('verify_vpd')
def VerifyVPD(options):
  """Verify that VPD values are properly set.

  Check if mandatory fields are set, and deprecated fields don't exist.
  """
  return GetGooftool(options).VerifyVPD()


@Command('verify_release_channel',
         _enforced_release_channels_cmd_arg)
def VerifyReleaseChannel(options):
  """Verify that release image channel is correct.

  ChromeOS has four channels: canary, dev, beta and stable.
  The last three channels support image auto-updates, checks
  that release image channel is one of them.
  """
  return GetGooftool(options).VerifyReleaseChannel(
      options.enforced_release_channels)


@Command('verify_cros_config')
def VerifyCrosConfig(options):
  """Verify entries in cros config make sense."""
  return GetGooftool(options).VerifyCrosConfig()


@Command('verify-sn-bits',
         _enable_zero_touch_cmd_arg)
def VerifySnBits(options):
  if options.enable_zero_touch:
    GetGooftool(options).VerifySnBits()


@Command('write_protect')
def EnableFwWp(options):
  """Enable then verify firmware write protection."""
  del options  # Unused.

  def WriteProtect(fw):
    """Calculate protection size, then invoke flashrom.

    The region (offset and size) to write protect may be different per chipset
    and firmware layout, so we have to read the WP_RO section from FMAP to
    decide that.
    """
    wp_section = 'WP_RO'

    fmap_image = fw.GetFirmwareImage(
        sections=(['FMAP'] if fw.target == crosfw.TARGET_MAIN else None))
    if not fmap_image.has_section(wp_section):
      raise Error('Could not find %s firmware section: %s' %
                  (fw.target.upper(), wp_section))

    section_data = fw.GetFirmwareImage(
        sections=[wp_section]).get_section_area(wp_section)
    ro_offset, ro_size = section_data[0:2]

    logging.debug('write protecting %s [off=%x size=%x]', fw.target.upper(),
                  ro_offset, ro_size)
    crosfw.Flashrom(fw.target).EnableWriteProtection(ro_offset, ro_size)

  if HasFpmcu():
    # TODO(b/143991572): Implement enable_fpmcu_write_protection in gooftool.
    cmd = os.path.join(
        paths.FACTORY_DIR, 'sh', 'enable_fpmcu_write_protection.sh')
    cmd_result = Shell(cmd)
    if not cmd_result.success:
      raise Error(
          'Failed to enable FPMCU write protection, stdout=%r, stderr=%r' %
          (cmd_result.stdout, cmd_result.stderr))

  WriteProtect(crosfw.LoadMainFirmware())
  event_log.Log('wp', fw='main')

  # Some EC (mostly PD) does not support "RO_NOW". Instead they will only set
  # "RO_AT_BOOT" when you request to enable RO (These platforms consider
  # --wp-range with right range identical to --wp-enable), and requires a
  # 'ectool reboot_ec RO at-shutdown; reboot' to let the RO take effect.
  # After reboot, "flashrom -p host --wp-status" will return protected range.
  # If you don't reboot, returned range will be (0, 0), and running command
  # "ectool flashprotect" will not have RO_NOW.
  # generic_common.test_list.json provides "EnableECWriteProtect" test group
  # which can be run individually before finalization. Try that out if you're
  # having trouble enabling RO_NOW flag.

  for fw in [crosfw.LoadEcFirmware(), crosfw.LoadPDFirmware()]:
    if fw.GetChipId() is None:
      logging.warning('%s not write protected (seems there is no %s flash).',
                      fw.target.upper(), fw.target.upper())
      continue
    WriteProtect(fw)
    event_log.Log('wp', fw=fw.target)


@Command('clear_gbb_flags')
def ClearGBBFlags(options):
  """Zero out the GBB flags, in preparation for transition to release state.

  No GBB flags are set in release/shipping state, but they are useful
  for factory/development.  See "futility gbb --flags" for details.
  """

  GetGooftool(options).ClearGBBFlags()
  event_log.Log('clear_gbb_flags')


@Command('clear_factory_vpd_entries')
def ClearFactoryVPDEntries(options):
  """Clears factory.* items in the RW VPD."""
  entries = GetGooftool(options).ClearFactoryVPDEntries()
  event_log.Log('clear_factory_vpd_entries', entries=FilterDict(entries))


@Command('generate_stable_device_secret')
def GenerateStableDeviceSecret(options):
  """Generates a fresh stable device secret and stores it in the RO VPD."""
  GetGooftool(options).GenerateStableDeviceSecret()
  event_log.Log('generate_stable_device_secret')


@Command('cr50_set_sn_bits_and_board_id',
         _rma_mode_cmd_arg)
def Cr50SetSnBitsAndBoardId(options):
  """Deprecated: use Cr50WriteFlashInfo instead."""
  logging.warning('This function is renamed to Cr50WriteFlashInfo')
  Cr50WriteFlashInfo(options)


@Command('cr50_write_flash_info',
         _rma_mode_cmd_arg,
         _enable_zero_touch_cmd_arg)
def Cr50WriteFlashInfo(options):
  """Set the serial number bits, board id and flags on the Cr50 chip."""
  GetGooftool(options).Cr50WriteFlashInfo(
      options.enable_zero_touch, options.rma_mode)
  event_log.Log('cr50_write_flash_info')


@Command('cr50_write_whitelabel_flags')
def Cr50WriteWhitelabelFlags(options):
  GetGooftool(options).Cr50WriteWhitelabelFlags()
  event_log.Log('cr50_write_whitelabel_flags')


@Command('cr50_disable_factory_mode')
def Cr50DisableFactoryMode(options):
  """Reset Cr50 state back to default state after RMA."""
  return GetGooftool(options).Cr50DisableFactoryMode()


@Command('enable_release_partition',
         CmdArg('--release_rootfs',
                help=('path to the release rootfs device. If not specified, '
                      'the default (5th) partition will be used.')))
def EnableReleasePartition(options):
  """Enables a release image partition on the disk."""
  GetGooftool(options).EnableReleasePartition(options.release_rootfs)


@Command('wipe_in_place',
         CmdArg('--fast', action='store_true',
                help='use non-secure but faster wipe method.'),
         _shopfloor_url_args_cmd_arg,
         _station_ip_cmd_arg,
         _station_port_cmd_arg,
         _wipe_finish_token_cmd_arg,
         _test_umount_cmd_arg)
def WipeInPlace(options):
  """Start factory wipe directly without reboot."""

  GetGooftool(options).WipeInPlace(options.fast,
                                   options.shopfloor_url,
                                   options.station_ip,
                                   options.station_port,
                                   options.wipe_finish_token,
                                   options.test_umount)

@Command('wipe_init',
         CmdArg('--wipe_args', help='arguments for clobber-state'),
         CmdArg('--state_dev', help='path to stateful partition device'),
         CmdArg('--root_disk', help='path to primary device'),
         CmdArg('--old_root', help='path to old root'),
         _shopfloor_url_args_cmd_arg,
         _release_rootfs_cmd_arg,
         _station_ip_cmd_arg,
         _station_port_cmd_arg,
         _wipe_finish_token_cmd_arg,
         _keep_developer_mode_flag_after_clobber_state_cmd_arg,
         _test_umount_cmd_arg)
def WipeInit(options):
  GetGooftool(options).WipeInit(
      options.wipe_args,
      options.shopfloor_url,
      options.state_dev,
      options.release_rootfs,
      options.root_disk,
      options.old_root,
      options.station_ip,
      options.station_port,
      options.wipe_finish_token,
      options.keep_developer_mode_flag_after_clobber_state,
      options.test_umount)


@Command('verify',
         CmdArg('--no_write_protect', action='store_true',
                help='Do not check write protection switch state.'),
         _hwid_status_list_cmd_arg,
         _hwdb_path_cmd_arg,
         _project_cmd_arg,
         _probe_results_cmd_arg,
         _hwid_cmd_arg,
         _hwid_run_vpd_cmd_arg,
         _hwid_vpd_data_file_cmd_arg,
         _rma_mode_cmd_arg,
         _cros_core_cmd_arg,
         _has_ec_pubkey_cmd_arg,
         _ec_pubkey_path_cmd_arg,
         _ec_pubkey_hash_cmd_arg,
         _release_rootfs_cmd_arg,
         _firmware_path_cmd_arg,
         _enforced_release_channels_cmd_arg,
         _waive_list_cmd_arg,
         _skip_list_cmd_arg,
         _no_ectool_cmd_arg,
         _enable_zero_touch_cmd_arg)
def Verify(options):
  """Verifies if whole factory process is ready for finalization.

  This routine performs all the necessary checks to make sure the
  device is ready to be finalized, but does not modify state.  These
  checks include dev switch, firmware write protection switch, hwid,
  system time, keys, and root file system.
  """

  if not options.no_write_protect:
    VerifyWPSwitch(options)
    VerifyManagementEngineLocked(options)
  VerifyHWID(options)
  VerifySystemTime(options)
  if options.has_ec_pubkey:
    VerifyECKey(options)
  VerifyKeys(options)
  VerifyRootFs(options)
  VerifyTPM(options)
  VerifyVPD(options)
  VerifyReleaseChannel(options)
  VerifyCrosConfig(options)
  VerifySnBits(options)


@Command('untar_stateful_files')
def UntarStatefulFiles(unused_options):
  """Untars stateful files from stateful_files.tar.xz on stateful partition.

  If that file does not exist (which should only be R30 and earlier),
  this is a no-op.
  """
  # Path to stateful partition on device.
  device_stateful_path = '/mnt/stateful_partition'
  tar_file = os.path.join(device_stateful_path, 'stateful_files.tar.xz')
  if os.path.exists(tar_file):
    Spawn(['tar', 'xf', tar_file], cwd=device_stateful_path,
          log=True, check_call=True)
  else:
    logging.warning('No stateful files at %s', tar_file)


@Command('log_source_hashes')
def LogSourceHashes(options):
  """Logs hashes of source files in the factory toolkit."""
  del options  # Unused.
  # WARNING: The following line is necessary to validate the integrity
  # of the factory software.  Do not remove or modify it.
  #
  # 警告：此行会验证工厂软件的完整性，禁止删除或修改。
  factory_par = sys_utils.GetRunningFactoryPythonArchivePath()
  if factory_par:
    event_log.Log(
        'source_hashes',
        **file_utils.HashPythonArchive(factory_par))
  else:
    event_log.Log(
        'source_hashes',
        **file_utils.HashSourceTree(os.path.join(paths.FACTORY_DIR, 'py')))


@Command('log_system_details')
def LogSystemDetails(options):
  """Write miscellaneous system details to the event log."""

  event_log.Log('system_details', **GetGooftool(options).GetSystemDetails())


def CreateReportArchiveBlob(*args, **kwargs):
  """Creates a report archive and returns it as a blob.

  Args:
    See CreateReportArchive.

  Returns:
    An xmlrpc.client.Binary object containing a .tar.xz file.
  """
  report_archive = CreateReportArchive(*args, **kwargs)
  try:
    return xmlrpc.client.Binary(
        file_utils.ReadFile(report_archive, encoding=None))
  finally:
    os.unlink(report_archive)


def CreateReportArchive(device_sn=None, add_file=None):
  """Creates a report archive in a temporary directory.

  Args:
    device_sn: The device serial number (optional).
    add_file: A list of files to add (optional).

  Returns:
    Path to the archive.
  """
  # Flush Testlog data to DATA_TESTLOG_DIR before creating a report archive.
  result, reason = state.GetInstance().FlushTestlog(
      uplink=False, local=True, timeout=10)
  if not result:
    logging.warning('Failed to flush testlog data: %s', reason)

  def NormalizeAsFileName(token):
    return re.sub(r'\W+', '', token).strip()

  target_name = '%s%s.tar.xz' % (
      time.strftime('%Y%m%dT%H%M%SZ',
                    time.gmtime()),
      ('' if device_sn is None else
       '_' + NormalizeAsFileName(device_sn)))
  target_path = os.path.join(gettempdir(), target_name)

  # Intentionally ignoring dotfiles in EVENT_LOG_DIR.
  tar_cmd = 'cd %s ; tar cJf %s * -C /' % (event_log.EVENT_LOG_DIR, target_path)
  tar_files = [paths.FACTORY_LOG_PATH, paths.DATA_TESTLOG_DIR]
  if add_file:
    tar_files = tar_files + add_file
  for f in tar_files:
    # Require absolute paths since we use -C / to change current directory to
    # root.
    if not f.startswith('/'):
      raise Error('Not an absolute path: %s' % f)
    if not os.path.exists(f):
      raise Error('File does not exist: %s' % f)
    tar_cmd += ' %s' % pipes.quote(f[1:])
  cmd_result = Shell(tar_cmd)

  if cmd_result.status == 1:
    # tar returns 1 when some files were changed during archiving,
    # but that is expected for log files so should ignore such failure
    # if the archive looks good.
    Spawn(['tar', 'tJf', target_path], check_call=True, log=True,
          ignore_stdout=True)
  elif not cmd_result.success:
    raise Error('unable to tar event logs, cmd %r failed, stderr: %r' %
                (tar_cmd, cmd_result.stderr))

  return target_path

_upload_method_cmd_arg = CmdArg(
    '--upload_method', metavar='METHOD:PARAM',
    help=('How to perform the upload.  METHOD should be one of '
          '{ftp, shopfloor, ftps, cpfe, smb}.'))
_upload_max_retry_times_arg = CmdArg(
    '--upload_max_retry_times', type=int, default=0,
    help='Number of tries to upload. 0 to retry infinitely.')
_upload_retry_interval_arg = CmdArg(
    '--upload_retry_interval', type=int, default=None,
    help='Retry interval in seconds.')
_upload_allow_fail_arg = CmdArg(
    '--upload_allow_fail', action='store_true',
    help='Continue finalize if report upload fails.')
_add_file_cmd_arg = CmdArg(
    '--add_file', metavar='FILE', action='append',
    help='Extra file to include in report (must be an absolute path)')


@Command('upload_report',
         _upload_method_cmd_arg,
         _upload_max_retry_times_arg,
         _upload_retry_interval_arg,
         _upload_allow_fail_arg,
         _add_file_cmd_arg)
def UploadReport(options):
  """Create a report containing key device details."""
  ro_vpd = vpd.VPDTool().GetAllData(partition=vpd.VPD_READONLY_PARTITION_NAME)
  device_sn = ro_vpd.get('serial_number', None)
  if device_sn is None:
    logging.warning('RO_VPD missing device serial number')
    device_sn = 'MISSING_SN_' + time_utils.TimedUUID()
  target_path = CreateReportArchive(device_sn, options.add_file)

  if options.upload_method is None or options.upload_method == 'none':
    logging.warning('REPORT UPLOAD SKIPPED (report left at %s)', target_path)
    return
  method, param = options.upload_method.split(':', 1)

  if options.upload_retry_interval is not None:
    retry_interval = options.upload_retry_interval
  else:
    retry_interval = report_upload.DEFAULT_RETRY_INTERVAL

  if method == 'shopfloor':
    report_upload.ShopFloorUpload(
        target_path, param,
        'GRT' if options.command_name == 'finalize' else None,
        max_retry_times=options.upload_max_retry_times,
        retry_interval=retry_interval,
        allow_fail=options.upload_allow_fail)
  elif method == 'ftp':
    report_upload.FtpUpload(target_path, 'ftp:' + param,
                            max_retry_times=options.upload_max_retry_times,
                            retry_interval=retry_interval,
                            allow_fail=options.upload_allow_fail)
  elif method == 'ftps':
    report_upload.CurlUrlUpload(target_path, '--ftp-ssl-reqd ftp:%s' % param,
                                max_retry_times=options.upload_max_retry_times,
                                retry_interval=retry_interval,
                                allow_fail=options.upload_allow_fail)
  elif method == 'cpfe':
    report_upload.CpfeUpload(target_path, pipes.quote(param),
                             max_retry_times=options.upload_max_retry_times,
                             retry_interval=retry_interval,
                             allow_fail=options.upload_allow_fail)
  elif method == 'smb':
    # param should be in form: <dest_path>.
    report_upload.SmbUpload(target_path, 'smb:' + param,
                            max_retry_times=options.upload_max_retry_times,
                            retry_interval=retry_interval,
                            allow_fail=options.upload_allow_fail)
  else:
    raise Error('unknown report upload method %r' % method)


@Command('finalize',
         CmdArg('--no_write_protect', action='store_true',
                help='Do not enable firmware write protection.'),
         CmdArg('--fast', action='store_true',
                help='use non-secure but faster wipe method.'),
         _no_ectool_cmd_arg,
         _shopfloor_url_args_cmd_arg,
         _hwdb_path_cmd_arg,
         _hwid_status_list_cmd_arg,
         _upload_method_cmd_arg,
         _upload_max_retry_times_arg,
         _upload_retry_interval_arg,
         _upload_allow_fail_arg,
         _add_file_cmd_arg,
         _probe_results_cmd_arg,
         _hwid_cmd_arg,
         _hwid_run_vpd_cmd_arg,
         _hwid_vpd_data_file_cmd_arg,
         _rma_mode_cmd_arg,
         _cros_core_cmd_arg,
         _has_ec_pubkey_cmd_arg,
         _ec_pubkey_path_cmd_arg,
         _ec_pubkey_hash_cmd_arg,
         _release_rootfs_cmd_arg,
         _firmware_path_cmd_arg,
         _enforced_release_channels_cmd_arg,
         _station_ip_cmd_arg,
         _station_port_cmd_arg,
         _wipe_finish_token_cmd_arg,
         _rlz_embargo_end_date_offset_cmd_arg,
         _waive_list_cmd_arg,
         _skip_list_cmd_arg,
         _no_generate_mfg_date_cmd_arg,
         _enable_zero_touch_cmd_arg)
def Finalize(options):
  """Verify system readiness and trigger transition into release state.

  This routine does the following:
  - Verifies system state (see verify command)
  - Untars stateful_files.tar.xz, if it exists, in the stateful partition, to
    initialize files such as the CRX cache
  - Modifies firmware bitmaps to match locale
  - Clears all factory-friendly flags from the GBB
  - Removes factory-specific entries from RW_VPD (factory.*)
  - Enables firmware write protection (cannot rollback after this)
  - Initialize Fpmcu entropy
  - Uploads system logs & reports
  - Wipes the testing kernel, rootfs, and stateful partition
  """
  if not options.rma_mode:
    # Write VPD values related to RLZ ping into VPD.
    GetGooftool(options).WriteVPDForRLZPing(options.embargo_offset)
    if options.generate_mfg_date:
      GetGooftool(options).WriteVPDForMFGDate()
  Cr50WriteFlashInfo(options)
  Cr50DisableFactoryMode(options)
  Verify(options)
  LogSourceHashes(options)
  UntarStatefulFiles(options)
  if options.cros_core:
    logging.info('SetFirmwareBitmapLocale is skipped for ChromeOS Core device.')
  else:
    SetFirmwareBitmapLocale(options)
  ClearFactoryVPDEntries(options)
  GenerateStableDeviceSecret(options)
  ClearGBBFlags(options)
  if options.no_write_protect:
    logging.warning('WARNING: Firmware Write Protection is SKIPPED.')
    event_log.Log('wp', fw='both', status='skipped')
  else:
    EnableFwWp(options)
  FpmcuInitializeEntropy(options)
  LogSystemDetails(options)
  UploadReport(options)

  event_log.Log('wipe_in_place')
  wipe_args = []
  if options.shopfloor_url:
    wipe_args += ['--shopfloor_url', options.shopfloor_url]
  if options.fast:
    wipe_args += ['--fast']
  if options.station_ip:
    wipe_args += ['--station_ip', options.station_ip]
  if options.station_port:
    wipe_args += ['--station_port', options.station_port]
  if options.wipe_finish_token:
    wipe_args += ['--wipe_finish_token', options.wipe_finish_token]
  ExecFactoryPar('gooftool', 'wipe_in_place', *wipe_args)


@Command('verify_hwid',
         _probe_results_cmd_arg,
         _hwdb_path_cmd_arg,
         _hwid_cmd_arg,
         _hwid_run_vpd_cmd_arg,
         _hwid_vpd_data_file_cmd_arg,
         _rma_mode_cmd_arg)
def VerifyHWID(options):
  """A simple wrapper that calls out to HWID utils to verify version 3 HWID.

  This is mainly for Gooftool to verify v3 HWID during finalize.  For testing
  and development purposes, please use `hwid` command.
  """
  database = GetGooftool(options).db

  encoded_string = options.hwid or GetGooftool(options).ReadHWID()

  probed_results = hwid_utils.GetProbedResults(infile=options.probe_results)
  device_info = hwid_utils.GetDeviceInfo()
  vpd_data = hwid_utils.GetVPDData(run_vpd=options.hwid_run_vpd,
                                   infile=options.hwid_vpd_data_file)

  event_log.Log('probed_results', probed_results=FilterDict(probed_results))
  event_log.Log('vpd', vpd=FilterDict(vpd_data))

  hwid_utils.VerifyHWID(database, encoded_string, probed_results,
                        device_info, vpd_data, options.rma_mode)

  event_log.Log('verified_hwid', hwid=encoded_string)


@Command('get_firmware_hash',
         CmdArg('--file', required=True, metavar='FILE', help='Firmware File.'))
def GetFirmwareHash(options):
  """Get firmware hash from a file"""
  if os.path.exists(options.file):
    value_dict = chromeos_firmware.CalculateFirmwareHashes(options.file)
    for key, value in value_dict.items():
      print('  %s: %s' % (key, value))
  else:
    raise Error('File does not exist: %s' % options.file)


@Command('fpmcu_initialize_entropy')
def FpmcuInitializeEntropy(options):
  """Initialze entropy of FPMCU."""

  if HasFpmcu():
    GetGooftool(options).FpmcuInitializeEntropy()
  else:
    logging.info('No FPS on this board.')


def main():
  """Run sub-command specified by the command line args."""

  options = ParseCmdline(
      'Perform Google required factory tests.',
      CmdArg('-l', '--log', metavar='PATH',
             help='Write logs to this file.'),
      CmdArg('--suppress-event-logs', action='store_true',
             help='Suppress event logging.'),
      CmdArg('--phase', default=None,
             help=('override phase for phase checking (defaults to the current '
                   'as returned by the "factory phase" command)')),
      VERBOSITY_CMD_ARG)
  SetupLogging(options.verbosity, options.log)
  event_log.SetGlobalLoggerDefaultPrefix('gooftool')
  event_log.GetGlobalLogger().suppress = options.suppress_event_logs
  logging.debug('gooftool options: %s', repr(options))

  phase.OverridePhase(options.phase)
  try:
    logging.debug('GOOFTOOL command %r', options.command_name)
    options.command(options)
    logging.info('GOOFTOOL command %r SUCCESS', options.command_name)
  except Error as e:
    logging.exception(e)
    sys.exit('GOOFTOOL command %r ERROR: %s' % (options.command_name, e))
  except Exception as e:
    logging.exception(e)
    sys.exit('UNCAUGHT RUNTIME EXCEPTION %s' % e)


if __name__ == '__main__':
  main()
