# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import codecs
from collections import namedtuple
from contextlib import contextmanager
import datetime
from distutils.version import LooseVersion
import glob
import logging
import os
import re
import sys
import tempfile
import time

import yaml

from cros.factory.gooftool.common import Util
from cros.factory.gooftool import bmpblk
from cros.factory.gooftool import cros_config as cros_config_module
from cros.factory.gooftool import crosfw
from cros.factory.gooftool import gbb
from cros.factory.gooftool import gsctool as gsctool_module
from cros.factory.gooftool import interval
from cros.factory.gooftool import vpd
from cros.factory.gooftool import vpd_data
from cros.factory.gooftool import wipe
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.test.l10n import regions
from cros.factory.test.rules import phase
from cros.factory.test.rules.privacy import FilterDict
from cros.factory.test.rules import registration_codes
from cros.factory.test.rules.registration_codes import RegistrationCode
from cros.factory.utils import config_utils
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils
from cros.factory.utils import sys_utils
from cros.factory.utils.type_utils import Error

# The mismatch result tuple.
Mismatch = namedtuple('Mismatch', ['expected', 'actual'])


class Gooftool:
  """A class to perform hardware probing and verification and to implement
  Google required tests.

  Properties:
    db: The HWID DB.  This is lazily loaded the first time it is used.
    _db_creator: The function used to create the db object the first time
      it is used.
  """
  # TODO(andycheng): refactor all other functions in gooftool.py to this.

  def __init__(self, hwid_version=3, project=None, hwdb_path=None):
    """Constructor.

    Args:
      hwid_version: The HWID version to operate on. Currently there is only one
        option: 3.
      project: A string indicating which project-specific component database to
        load. If not specified, the project name will be detected with
        cros.factory.hwid.ProbeProject(). Used for HWID v3 only.
      hwdb_path: The path to load the project-specific component database from.
        If not specified, cros.factory.hwid.hwid_utils.GetDefaultDataPath() will
        be used.  Used for HWID v3 only.
    """
    self._hwid_version = hwid_version
    if hwid_version == 3:
      self._project = project or hwid_utils.ProbeProject()
      self._hwdb_path = hwdb_path or hwid_utils.GetDefaultDataPath()
      self._db_creator = lambda: Database.LoadFile(
          os.path.join(self._hwdb_path, self._project.upper()))
    else:
      raise ValueError('Invalid HWID version: %r' % hwid_version)

    self._util = Util()
    self._crosfw = crosfw
    self._vpd = vpd.VPDTool()
    self._unpack_gbb = gbb.UnpackGBB
    self._unpack_bmpblock = bmpblk.unpack_bmpblock
    self._named_temporary_file = tempfile.NamedTemporaryFile
    self._db = None

  @property
  def db(self):
    """Lazy loader for the HWID database."""
    if not self._db:
      self._db = self._db_creator()
      # Hopefully not necessary, but just a safeguard to prevent
      # accidentally loading the DB multiple times.
      del self._db_creator
    return self._db

  def VerifyECKey(self, pubkey_path=None, pubkey_hash=None):
    """Verify EC public key.
    Verify by pubkey_path should have higher priority than pubkey_hash.

    Args:
      pubkey_path: A string for public key path. If not None, it verifies the
          EC with the given pubkey_path.
      pubkey_hash: A string for the public key hash. If not None, it verifies
          the EC with the given pubkey_hash.
    """
    with self._named_temporary_file() as tmp_ec_bin:
      flash_out = self._util.shell('flashrom -p ec -r %s' % tmp_ec_bin.name)
      if not flash_out.success:
        raise Error('Failed to read EC image: %s' % flash_out.stderr)
      if pubkey_path:
        result = self._util.shell('futility show --type rwsig --pubkey %s %s' %
                                  (pubkey_path, tmp_ec_bin.name))
        if not result.success:
          raise Error('Failed to verify EC key with pubkey %s: %s' %
                      (pubkey_path, result.stderr))
      elif pubkey_hash:
        live_ec_hash = self._util.GetKeyHashFromFutil(tmp_ec_bin.name)
        if live_ec_hash != pubkey_hash:
          raise Error('Failed to verify EC key: expects (%s) got (%s)' %
                      (pubkey_hash, live_ec_hash))
      else:
        raise ValueError('All arguments are None.')

  def VerifyFpKey(self):
    """Verify Fingerprint firmware public key.

    Verify the running fingerprint firmware is signed with the same key
    used to sign the fingerprint firmware binary in the release rootfs
    partition.
    """
    fp_board_result = self._util.shell(
        ['cros_config', '/fingerprint', 'board'])
    if not fp_board_result.success:
      raise Error('Failed to probe fingerprint board from cros_config')
    fp_board = fp_board_result.stdout.strip()

    with sys_utils.MountPartition(
        self._util.GetReleaseRootPartitionPath()) as root:
      fp_fw_pattern = os.path.join(root,
                                   'opt/google/biod/fw/%s_v*.bin' % fp_board)
      fp_fw_files = glob.glob(fp_fw_pattern)
      if len(fp_fw_files) != 1:
        raise Error('No uniquely matched fingerprint firmware blob')
      release_key_id = self._util.GetKeyHashFromFutil(fp_fw_files[0])

    key_id_result = self._util.shell(['ectool', '--name=cros_fp', 'rwsig',
                                      'dump', 'key_id'])
    if not key_id_result.success:
      raise Error('Failed to probe fingerprint key_id from ectool')
    live_key_id = key_id_result.stdout.strip()

    if live_key_id != release_key_id:
      raise Error('Failed to verify fingerprint key: expects (%s) got (%s)' %
                  (release_key_id, live_key_id))

  def VerifyKeys(self, release_rootfs=None, firmware_path=None, _tmpexec=None):
    """Verify keys in firmware and SSD match.

    The real partition needed is the kernel partition. However, in order to
    share params with other commands, we use release_rootfs and calculate the
    real kernel location from it.

    Args:
      release_rootfs: A string for release image rootfs path.
      firmware_path: A string for firmware image file path.
      _tmpexec: A function for overriding execution inside temp folder.
    """
    if release_rootfs is None:
      release_rootfs = self._util.GetReleaseRootPartitionPath()

    kernel_dev = self._util.GetReleaseKernelPathFromRootPartition(
        release_rootfs)

    if firmware_path is None:
      firmware_path = self._crosfw.LoadMainFirmware().GetFileName()
      firmware_image = self._crosfw.LoadMainFirmware().GetFirmwareImage()
    else:
      with open(firmware_path, 'rb') as f:
        firmware_image = self._crosfw.FirmwareImage(f.read())

    with file_utils.TempDirectory() as tmpdir:

      def _DefaultTmpExec(message, command, fail_message=None, regex=None):
        """Executes a command inside temp folder (tmpdir).

        If regex is specified, return matched string from stdout.
        """
        logging.debug(message)
        result = self._util.shell('( cd %s; %s )' % (tmpdir, command))
        if not result.success:
          raise Error(fail_message or
                      ('Failed to %s: %s' % (message, result.stderr)))
        if regex:
          matched = re.findall(regex, result.stdout)
          if matched:
            return matched[0]
        return None

      _TmpExec = _tmpexec if _tmpexec else _DefaultTmpExec

      # define key names
      key_normal = 'kernel_subkey.vbpubk'
      key_normal_a = 'kernel_subkey_a.vbpubk'
      key_normal_b = 'kernel_subkey_b.vbpubk'
      key_root = 'rootkey.vbpubk'
      key_recovery = 'recovery_key.vbpubk'
      blob_kern = 'kern.blob'
      dir_devkeys = '/usr/share/vboot/devkeys'

      logging.debug('dump kernel from %s', kernel_dev)
      with open(kernel_dev, 'rb') as f:
        # The kernel is usually 8M or 16M, but let's read more.
        file_utils.WriteFile(os.path.join(tmpdir, blob_kern),
                             f.read(64 * 1048576), encoding=None)
      logging.debug('extract firmware from %s', firmware_path)
      for section in ('GBB', 'FW_MAIN_A', 'FW_MAIN_B', 'VBLOCK_A', 'VBLOCK_B'):
        file_utils.WriteFile(os.path.join(tmpdir, section),
                             firmware_image.get_section(section), encoding=None)

      _TmpExec('get keys from firmware GBB',
               'futility gbb -g --rootkey %s  --recoverykey %s GBB' %
               (key_root, key_recovery))
      rootkey_hash = _TmpExec(
          'unpack rootkey', 'futility vbutil_key --unpack %s' % key_root,
          regex=r'(?<=Key sha1sum:).*').strip()
      _TmpExec('unpack recoverykey',
               'futility vbutil_key --unpack %s' % key_recovery)

      # Pre-scan for well-known problems.
      if rootkey_hash == 'b11d74edd286c144e1135b49e7f0bc20cf041f10':
        logging.warning('YOU ARE TRYING TO FINALIZE WITH DEV ROOTKEY.')

      _TmpExec('verify firmware A with root key',
               'futility vbutil_firmware --verify VBLOCK_A --signpubkey %s '
               ' --fv FW_MAIN_A --kernelkey %s' % (key_root, key_normal_a))
      _TmpExec('verify firmware B with root key',
               'futility vbutil_firmware --verify VBLOCK_B --signpubkey %s '
               ' --fv FW_MAIN_B --kernelkey %s' % (key_root, key_normal_b))

      # Unpack keys and keyblocks
      _TmpExec('unpack kernel keyblock',
               'futility vbutil_keyblock --unpack %s' % blob_kern)
      try:
        for key in key_normal_a, key_normal_b:
          _TmpExec('unpack %s' % key, 'vbutil_key --unpack %s' % key)
          _TmpExec('verify kernel by %s' % key,
                   'futility vbutil_kernel --verify %s --signpubkey %s' %
                   (blob_kern, key))

      except Error:
        _TmpExec('check recovery key signed image',
                 '! futility vbutil_kernel --verify %s --signpubkey %s' %
                 (blob_kern, key_recovery),
                 'YOU ARE USING A RECOVERY KEY SIGNED IMAGE.')

        for key in key_normal, key_recovery:
          _TmpExec('check dev-signed image <%s>' % key,
                   '! futility vbutil_kernel --verify %s --signpubkey %s/%s' %
                   (blob_kern, dir_devkeys, key),
                   'YOU ARE FINALIZING WITH DEV-SIGNED IMAGE <%s>' %
                   key)
        raise

    logging.info('SUCCESS: Verification completed.')

  def VerifySystemTime(self, release_rootfs=None, system_time=None,
                       rma_mode=False):
    """Verify system time is later than release filesystem creation time."""
    if release_rootfs is None:
      release_rootfs = self._util.GetReleaseRootPartitionPath()
    if system_time is None:
      system_time = time.time()

    e2header = self._util.shell('dumpe2fs -h %s' % release_rootfs)
    if not e2header.success:
      raise Error('Failed to read file system: %s, %s' %
                  (release_rootfs, e2header.stderr))
    matched = re.findall(r'^Filesystem created: *(.*)', e2header.stdout,
                         re.MULTILINE)
    if not matched:
      raise Error('Failed to find file system creation time: %s' %
                  release_rootfs)
    created_time = time.mktime(time.strptime(matched[0]))
    logging.debug('Comparing system time <%s> and filesystem time <%s>',
                  system_time, created_time)
    if system_time < created_time:
      if not rma_mode:
        raise Error('System time (%s) earlier than file system (%s) creation '
                    'time (%s)' % (system_time, release_rootfs, created_time))
      logging.warning('Set system time to file system creation time (%s)',
                      created_time)
      self._util.shell('toybox date @%d' % int(created_time))

  def VerifyRootFs(self, release_rootfs=None):
    """Verify rootfs on SSD is valid by checking hash."""
    if release_rootfs is None:
      release_rootfs = self._util.GetReleaseRootPartitionPath()
    device = self._util.GetPartitionDevice(release_rootfs)

    # TODO(hungte) Using chromeos_invoke_postinst here is leaving a window
    # where unexpected reboot or test exit may cause the system to boot into
    # the release image. Currently "cgpt" is very close to the last step of
    # postinst so it may be OK, but we should seek for better method for this,
    # for example adding a "--nochange_boot_partition" to chromeos-postinst.
    try:
      # Always rollback GPT changes.
      curr_attrs = self._util.GetCgptAttributes(device)
      self._util.InvokeChromeOSPostInstall(release_rootfs)
    finally:
      self._util.SetCgptAttributes(curr_attrs, device)

  def VerifyTPM(self):
    """Verify TPM is cleared."""
    expected_status = {
        'enabled': '1',
        'owned': '0'
    }
    tpm_root = '/sys/class/tpm/tpm0/device'
    legacy_tpm_root = '/sys/class/misc/tpm0/device'
    # TPM device path has been changed in kernel 3.18.
    if not os.path.exists(tpm_root):
      tpm_root = legacy_tpm_root
    for key, value in expected_status.items():
      if open(os.path.join(tpm_root, key)).read().strip() != value:
        raise Error('TPM is not cleared.')

  def VerifyManagementEngineLocked(self):
    """Verify Management Engine is locked."""
    mainfw = self._crosfw.LoadMainFirmware().GetFirmwareImage()
    if not mainfw.has_section('SI_ME'):
      logging.info('System does not have Management Engine.')
      return
    # If ME is locked, it should contain only 0xFFs.
    data = mainfw.get_section('SI_ME').strip(b'\xff')
    if data:
      raise Error('ME (ManagementEngine) firmware may be not locked.')
    # TODO(hungte) In future we may add more checks using ifdtool. See
    # crosbug.com/p/30283 for more information.
    logging.info('Management Engine is locked.')

  def VerifyVPD(self):
    """Verify that VPD values are set properly."""

    def MatchWhole(key, pattern, value, raise_exception=True):
      if re.match(r'^' + pattern + r'$', value):
        return key
      if raise_exception:
        raise ValueError('Incorrect VPD: %s=%s (expected format: %s)' %
                         (key, value, pattern))
      return None

    def CheckVPDFields(section, data, required, optional, optional_re):
      """Checks if all fields in data fall into given format.

      Args:
        section: a string for VPD section name, 'RO' or 'RW.
        data: a mapping of (key, value) for VPD data.
        required: a mapping of (key, format_RE) for required data.
        optional: a mapping of (key, format_RE) for optional data.
        optional_re: a mapping of (key_re, format_RE) for optional data.

      Returns:
        A list of verified keys.

      Raises:
        ValueError if some value does not match format_RE.
        KeyError if some unexpected VPD key name is found.
      """
      checked = []
      known = required.copy()
      known.update(optional)
      for k, v in data.items():
        if k in known:
          checked.append(MatchWhole(k, known[k], v))
        else:
          # Try if matches optional_re
          for rk, rv in optional_re.items():
            if MatchWhole(k, rk, k, raise_exception=False):
              checked.append(MatchWhole(k, rv, v))
              break
          else:
            raise KeyError('Unexpected %s VPD: %s=%s.' % (section, k, v))

      missing_keys = set(required).difference(checked)
      if missing_keys:
        raise Error('Missing required %s VPD values: %s' %
                    (section, ','.join(missing_keys)))

    def GetDeviceNameForRegistrationCode(project,
                                         config='whitelabel_reg_code'):
      # Load config json file
      try:
        reg_code_config = config_utils.LoadConfig(config, validate_schema=False)
      except Exception:
        return project
      if project not in reg_code_config:
        return project
      # Get the customization from mosys as device name for whitelabel device
      customization = self._util.shell(
          ['mosys', 'platform', 'customization']).stdout.strip()
      if not customization:
        raise Error("No customization code found while checking VPD Reg code")
      if customization not in reg_code_config[project]:
        return project
      if reg_code_config[project][customization]:
        return customization
      return project

    # Check required data
    ro_vpd = self._vpd.GetAllData(partition=vpd.VPD_READONLY_PARTITION_NAME)
    rw_vpd = self._vpd.GetAllData(partition=vpd.VPD_READWRITE_PARTITION_NAME)
    CheckVPDFields(
        'RO', ro_vpd, vpd_data.REQUIRED_RO_DATA, vpd_data.KNOWN_RO_DATA,
        vpd_data.KNOWN_RO_DATA_RE)

    CheckVPDFields(
        'RW', rw_vpd, vpd_data.REQUIRED_RW_DATA, vpd_data.KNOWN_RW_DATA,
        vpd_data.KNOWN_RW_DATA_RE)

    # Check known value contents.
    region = ro_vpd['region']
    if region not in regions.REGIONS:
      raise ValueError('Unknown region: "%s".' % region)

    device_name = GetDeviceNameForRegistrationCode(self._project)

    for type_prefix in ['UNIQUE', 'GROUP']:
      vpd_field_name = type_prefix[0].lower() + 'bind_attribute'
      type_name = getattr(RegistrationCode.Type, type_prefix + '_CODE')
      try:
        # RegCode should be ready since PVT
        registration_codes.CheckRegistrationCode(
            rw_vpd[vpd_field_name], type=type_name, device=device_name,
            allow_dummy=(phase.GetPhase() < phase.PVT_DOGFOOD))
      except registration_codes.RegistrationCodeException as e:
        raise ValueError('%s is invalid: %r' % (vpd_field_name, e))

  def VerifyReleaseChannel(self, enforced_channels=None):
    """Verify that release image channel is correct.

    Args:
      enforced_channels: a list of enforced release image channels, might
          be different per board. It should be the subset or the same set
          of the allowed release channels.
    """
    release_channel = self._util.GetReleaseImageChannel()
    allowed_channels = self._util.GetAllowedReleaseImageChannels()

    if enforced_channels is None:
      enforced_channels = allowed_channels
    elif not all(channel in allowed_channels for channel in enforced_channels):
      raise Error('Enforced channels are incorrect: %s. '
                  'Allowed channels are %s.' % (
                      enforced_channels, allowed_channels))

    if not any(channel in release_channel for channel in enforced_channels):
      raise Error('Release image channel is incorrect: %s. '
                  'Enforced channels are %s.' % (
                      release_channel, enforced_channels))

  def VerifyCrosConfig(self):
    """Verify that entries in cros config make sense."""
    if phase.GetPhase() >= phase.PVT_DOGFOOD:
      # The value actually comes from "cros_config / brand-code", however,
      # most scripts are still using "mosys platform brand" to get the value,
      # so we also check the value by mosys command.
      rlz = self._util.shell(['mosys', 'platform', 'brand']).stdout.strip()
      if not rlz or rlz == 'ZZCR':
        # this is incorrect...
        raise Error('RLZ code "%s" is not allowed in PVT' % rlz)

    model = self._util.shell(['mosys', 'platform', 'model']).stdout.strip()
    if not model:
      raise Error('Model name is empty')

    def _ParseCrosConfig(config_path):
      with open(config_path) as f:
        obj = yaml.load(f)

      # According to https://crbug.com/1070692, 'platform-name' is not a part of
      # identity info.  We shouldn't check it.
      for config in obj['chromeos']['configs']:
        config['identity'].pop('platform-name', None)

      fields = ['name', 'identity', 'brand-code']
      configs = [
          {
              field: config[field] for field in fields
          }
          for config in obj['chromeos']['configs']
          if config['name'] == model
      ]
      configs = {
          # set sort_keys=True to make the result stable.
          json_utils.DumpStr(config, sort_keys=True) for config in configs
      }
      return configs

    # Load config.yaml from release image (FSI) and test image, and compare the
    # fields we cared about.
    config_path = 'usr/share/chromeos-config/yaml/config.yaml'
    test_configs = _ParseCrosConfig(os.path.join('/', config_path))
    with sys_utils.MountPartition(
        self._util.GetReleaseRootPartitionPath()) as root:
      release_configs = _ParseCrosConfig(os.path.join(root, config_path))

    if test_configs != release_configs:
      error = ['Detect different chromeos-config between test image and FSI.']
      error += ['Configs in test image:']
      error += ['\t' + config for config in test_configs]
      error += ['Configs in FSI:']
      error += ['\t' + config for config in release_configs]
      raise Error('\n'.join(error))

  def ClearGBBFlags(self):
    """Zero out the GBB flags, in preparation for transition to release state.

    No GBB flags are set in release/shipping state, but they are useful
    for factory/development.  See "futility gbb --flags" for details.
    """

    result = self._util.shell('/usr/share/vboot/bin/set_gbb_flags.sh 0 2>&1')
    if not result.success:
      raise Error('Failed setting GBB flags: %s' % result.stdout)

  def EnableReleasePartition(self, release_rootfs=None):
    """Enables a release image partition on the disk.

    Args:
      release_rootfs: path to the release rootfs device. If not specified,
          the default (5th) partition will be used.
    """
    if not release_rootfs:
      release_rootfs = Util().GetReleaseRootPartitionPath()
    wipe.EnableReleasePartition(release_rootfs)


  def WipeInPlace(self, is_fast=None, shopfloor_url=None,
                  station_ip=None, station_port=None, wipe_finish_token=None,
                  test_umount=False):
    """Start transition to release state directly without reboot.

    Args:
      is_fast: Whether or not to apply fast wipe.
    """
    # check current GBB flags to determine if we need to keep .developer_mode
    # after clobber-state.
    try:
      main_fw = self._crosfw.LoadMainFirmware()
      fw_filename = main_fw.GetFileName(sections=['GBB'])
      result = self._util.shell('futility gbb --get --flags "%s"' % fw_filename)
      # The output should look like 'flags: 0x00000000'.
      unused_prefix, gbb_flags = result.stdout.strip().split(' ')
      gbb_flags = int(gbb_flags, 16)
    except Exception:
      logging.warning('Failed to get GBB flags, assume it is 0', exc_info=1)
      gbb_flags = 0

    if (not test_umount and
        phase.GetPhase() >= phase.PVT and gbb_flags != 0):
      raise Error('GBB flags should be cleared in PVT (it is 0x%x)' % gbb_flags)

    GBB_FLAG_FORCE_DEV_SWITCH_ON = 0x00000008
    keep_developer_mode_flag = bool(gbb_flags & GBB_FLAG_FORCE_DEV_SWITCH_ON)

    wipe.WipeInTmpFs(is_fast, shopfloor_url,
                     station_ip, station_port, wipe_finish_token,
                     keep_developer_mode_flag, test_umount)

  def WipeInit(self, wipe_args, shopfloor_url, state_dev,
               release_rootfs, root_disk, old_root, station_ip, station_port,
               wipe_finish_token, keep_developer_mode_flag, test_umount):
    """Start wiping test image."""
    wipe.WipeInit(wipe_args, shopfloor_url, state_dev,
                  release_rootfs, root_disk, old_root, station_ip, station_port,
                  wipe_finish_token, keep_developer_mode_flag, test_umount)

  def WriteVPDForRLZPing(self, embargo_offset=7):
    """Write VPD values related to RLZ ping into VPD."""

    if embargo_offset < 7:
      raise Error('embargo end date offset cannot less than 7 (days)')

    embargo_date = datetime.date.today()
    embargo_date += datetime.timedelta(days=embargo_offset)

    self._vpd.UpdateData({
        'should_send_rlz_ping': '1',
        'rlz_embargo_end_date': embargo_date.isoformat(),
    }, partition=vpd.VPD_READWRITE_PARTITION_NAME)

  def WriteVPDForMFGDate(self):
    """Write manufacturing date into VPD."""
    mfg_date = datetime.date.today()
    self._vpd.UpdateData({
        'mfg_date': mfg_date.isoformat()
    }, partition=vpd.VPD_READONLY_PARTITION_NAME)

  def WriteHWID(self, hwid=None):
    """Writes specified HWID value into the system BB.

    Args:
      hwid: The HWID string to be written to the device.
    """

    assert hwid
    main_fw = self._crosfw.LoadMainFirmware()
    fw_filename = main_fw.GetFileName(sections=['GBB'])
    self._util.shell(
        'futility gbb --set --hwid="%s" "%s"' % (hwid, fw_filename))
    main_fw.Write(fw_filename)

  def ReadHWID(self):
    """Reads the HWID string from firmware GBB."""

    fw_filename = self._crosfw.LoadMainFirmware().GetFileName(sections=['GBB'])
    result = self._util.shell('futility gbb -g --hwid "%s"' % fw_filename)
    if not result.success:
      raise Error('Failed to read the HWID string: %s' % result.stderr)

    return re.findall(r'hardware_id:(.*)', result.stdout)[0].strip()

  def VerifyWPSwitch(self, has_ectool=True):
    """Verifies hardware write protection switch is enabled.

    Raises:
      Error when there is an error.
    """

    if self._util.shell('crossystem wpsw_cur').stdout.strip() != '1':
      raise Error('write protection switch of AP is disabled.')

    if not has_ectool:
      return

    ectool_flashprotect = self._util.shell('ectool flashprotect').stdout
    if not re.search('^Flash protect flags:.+wp_gpio_asserted',
                     ectool_flashprotect, re.MULTILINE):
      raise Error('write protectioin switch of EC is disabled.')

  def VerifySnBits(self):
    # Add '-n' to dry run.
    result = self._util.shell(['/usr/share/cros/cr50-set-sn-bits.sh', '-n'])
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    logging.info('status: %d', result.status)
    logging.info('stdout: %s', stdout)
    logging.info('stderr: %s', stderr)

    if result.status != 0:
      # Fail reason, either:
      # - attested_device_id is not set
      # - SN bits has been set differently
      # cr50-set-sn-bits.sh prints errors on stdout instead of stderr.
      raise Error(stdout)

    if 'This device has been RMAed' in stdout:
      logging.warning('SN Bits cannot be set anymore.')
      return

    if 'SN Bits have not been set yet' in stdout:
      if 'BoardID is set' in stdout:
        logging.warning('SN Bits cannot be set anymore.')

  def GetBitmapLocales(self, image_file):
    """Get bitmap locales

    Args:
      image_file: Path to the image file where locales are searched.

    Returns:
      List of language codes supported by the image
    """
    bitmap_locales = []
    with self._named_temporary_file('w+') as f:
      self._util.shell('cbfstool %s extract -n locales -f %s -r COREBOOT' %
                       (image_file, f.name))
      bitmap_locales = f.read()
      # We reach here even if cbfstool command fails
      if bitmap_locales:
        # The line format is "code,rtl". We remove ",rtl" here.
        return re.findall(r'^(\S+?)(?:,\S*)?$', bitmap_locales, re.MULTILINE)
      # Looks like image does not have locales file. Do the old-fashioned way
      self._util.shell('futility gbb -g --bmpfv=%s %s' %
                       (f.name, image_file))
      bmpblk_data = self._unpack_bmpblock(f.read())
      bitmap_locales = bmpblk_data.get('locales', bitmap_locales)
    return bitmap_locales

  def SetFirmwareBitmapLocale(self):
    """Sets firmware bitmap locale to the default value stored in VPD.

    This function ensures the default locale set in VPD is listed in the
    supported locales in the firmware bitmap and sets loc_idx to the default
    locale.

    Returns:
      A tuple of the default locale index and default locale. i.e.
      (index, locale)

      index: The index of the default locale in the bitmap.
      locale: The 2-character-string format of the locale. e.g. "en", "zh"

    Raises:
      Error, if the initial locale is missing in VPD or the default locale is
      not supported.
    """
    image_file = self._crosfw.LoadMainFirmware().GetFileName()
    ro_vpd = self._vpd.GetAllData(
        partition=vpd.VPD_READONLY_PARTITION_NAME)
    region = ro_vpd.get('region')
    if region is None:
      raise Error('Missing VPD "region".')
    if region not in regions.REGIONS:
      raise ValueError('Unknown region: "%s".' % region)
    # Use the primary locale for the firmware bitmap.
    locales = regions.REGIONS[region].language_codes
    bitmap_locales = self.GetBitmapLocales(image_file)

    # Some locale values are just a language code and others are a
    # hyphen-separated language code and country code pair.  We care
    # only about the language code part for some cases. Note some old firmware
    # bitmaps use underscore instead hyphen.
    for locale in locales:
      for language_code in [locale, locale.replace('-', '_'),
                            locale.partition('-')[0]]:
        if language_code in bitmap_locales:
          locale_index = bitmap_locales.index(language_code)
          self._util.shell('crossystem loc_idx=%d' % locale_index)
          return (locale_index, language_code)

    raise Error('Firmware bitmaps do not contain support for the specified '
                'initial locales: %r.\n'
                'Current supported locales are %r.' % (
                    locales, bitmap_locales))

  def GetSystemDetails(self):
    """Gets the system details including: platform name, crossystem,
    modem status, EC write-protect status and bios write-protect status.

    Returns:
      A dict of system details with the following format:
          {Name_of_the_detail: "result of the detail"}
      Note that the outputs could be multi-line strings.
    """
    cros_config = cros_config_module.CrosConfig(self._util.shell)

    # Note: Handle the shell commands with care since unit tests cannot
    # ensure the correctness of commands executed in shell.
    return {
        'platform_name':
            cros_config.GetPlatformName(),
        'crossystem':
            self._util.GetCrosSystem(),
        'modem_status':
            self._util.shell('modem status').stdout.splitlines(),
        'ec_wp_status':
            self._util.shell('flashrom -p ec --flash-size 2>/dev/null && '
                             'flashrom -p ec --wp-status || '
                             'echo "EC is not available."').stdout,
        'bios_wp_status':
            self._util.shell('flashrom -p host --wp-status').stdout,
        'cr50_board_id':
            self._util.shell('gsctool -a -i -M').stdout,
        'cr50_sn_bits':
            self._util.shell('/usr/share/cros/cr50-read-rma-sn-bits.sh').stdout,
    }

  def ClearFactoryVPDEntries(self):
    """Clears factory related VPD entries in the RW VPD.

    All VPD entries with '.' in key name are considered as special.
    We collect all special names and delete entries with known prefixes,
    and fail if there are unknown entries left.

    Returns:
      A dict of the removed entries.
    """
    def _IsFactoryVPD(k):
      # These names are defined in cros.factory.test.device_data
      known_names = ['factory.', 'component.', 'serials.']
      return any(name for name in known_names if k.startswith(name))

    rw_vpd = self._vpd.GetAllData(partition=vpd.VPD_READWRITE_PARTITION_NAME)
    dot_entries = {k: v for k, v in rw_vpd.items() if '.' in k}
    entries = {k: v for k, v in dot_entries.items() if _IsFactoryVPD(k)}
    unknown_keys = set(dot_entries) - set(entries)
    if unknown_keys:
      raise Error('Found unexpected RW VPD(s): %r' % unknown_keys)

    logging.info('Removing VPD entries %s', FilterDict(entries))
    if entries:
      try:
        self._vpd.UpdateData({k: None for k in entries.keys()},
                             partition=vpd.VPD_READWRITE_PARTITION_NAME)
      except Exception as e:
        raise Error('Failed to remove VPD entries: %r' % e)

    return entries

  def GenerateStableDeviceSecret(self):
    """Generates a fresh stable device secret and stores it in RO VPD.

    The stable device secret generated here is a high-entropy identifier that
    is unique to each device. It gets generated at manufacturing time and reset
    during RMA, but is stable under normal operation and notably also across
    recovery image installation.

    The stable device secret is suitable to obtain per-device stable hardware
    identifiers and/or encryption keys. Please never use the secret directly,
    but derive a secret specific for your context like this:

        your_secret = HMAC_SHA256(stable_device_secret,
                                  context_label\0optional_parameters)

    The stable_device_secret acts as the HMAC key. context_label is a string
    that uniquely identifies your usage context, which allows us to generate as
    many per-context secrets as we need. The optional_parameters string can
    contain additional information to further segregate your context, for
    example if there is a need for multiple secrets.

    The resulting secret(s) can be used freely, in particular they may be
    shared with the environment or servers. Before you start generating and
    using a secret in a new context, please always make sure to contact the
    privacy and security teams to check whether your intended usage meets the
    Chrome OS privacy and security guidelines.

    MOST IMPORTANTLY: THE STABLE DEVICE SECRET MUST NOT LEAVE THE DEVICE AT ANY
    TIME. DO NOT INCLUDE IT IN NETWORK COMMUNICATION, AND MAKE SURE IT DOES NOT
    SHOW UP IN DATA THAT GETS SHARED POTENTIALLY (LOGS, ETC.). FAILURE TO DO SO
    MAY BREAK THE SECURITY AND PRIVACY OF ALL OUR USERS. YOU HAVE BEEN WARNED.
    """

    # Ensure that the release image is recent enough to handle the stable
    # device secret key in VPD. Version 6887.0.0 is the first one that has the
    # session_manager change to generate server-backed state keys for forced
    # re-enrollment from the stable device secret.
    release_image_version = LooseVersion(self._util.GetReleaseImageVersion())
    if release_image_version < LooseVersion('6887.0.0'):
      raise Error("Release image version can't handle stable device secret!")

    # A context manager useful for wrapping code blocks that handle the device
    # secret in an exception handler, so the secret value does not leak due to
    # exception handling (for example, the value will be part of the VPD update
    # command, which may get included in exceptions). Chances are that
    # exceptions will prevent the secret value from getting written to VPD
    # anyways, but better safe than sorry.
    @contextmanager
    def scrub_exceptions(operation):
      try:
        yield
      except Exception:
        # Re-raise an exception including type and stack trace for the original
        # exception to facilitate error analysis. Don't include the exception
        # value as it may contain the device secret.
        (exc_type, _, exc_traceback) = sys.exc_info()
        cause = '%s: %s' % (operation, exc_type)
        raise Error(cause).with_traceback(exc_traceback)

    with scrub_exceptions('Error generating device secret'):
      # Generate the stable device secret and write it to VPD. Turn off logging,
      # so the generated secret doesn't leak to the logs.
      secret = self._util.shell('tpm-manager get_random 32',
                                log=False).stdout.strip()

    with scrub_exceptions('Error validating device secret'):
      secret_bytes = codecs.decode(secret, 'hex')
      if len(secret_bytes) != 32:
        raise Error

    with scrub_exceptions('Error writing device secret to VPD'):
      self._vpd.UpdateData(
          {'stable_device_secret_DO_NOT_SHARE':
           codecs.encode(secret_bytes, 'hex').decode('utf-8')},
          partition=vpd.VPD_READONLY_PARTITION_NAME)

  def Cr50SetROHash(self):
    """Set the AP-RO hash on the Cr50 chip.

    Cr50 after 0.5.5 and 0.6.5 supports RO verification, which needs the factory
    to write the RO hash to Cr50 before setting board ID.
    """

    firmware_image = self._crosfw.LoadMainFirmware().GetFirmwareImage()
    ro_offset, ro_size = firmware_image.get_section_area('RO_SECTION')
    ro_vpd_offset, ro_vpd_size = firmware_image.get_section_area('RO_VPD')
    gbb_offset, gbb_size = firmware_image.get_section_area('GBB')
    gbb_content = self._unpack_gbb(firmware_image.get_blob(), gbb_offset)
    hwid = gbb_content.hwid
    hwid_digest = gbb_content.hwid_digest

    # Calculate address intervals of
    # RO_SECTION + GBB - RO_VPD - HWID - HWID_DIGEST.
    include_intervals = [
        interval.Interval(ro_offset, ro_offset + ro_size),
        interval.Interval(gbb_offset, gbb_offset + gbb_size)]
    exclude_intervals = [
        interval.Interval(ro_vpd_offset, ro_vpd_offset + ro_vpd_size),
        interval.Interval(hwid.offset, hwid.offset + hwid.size),
        interval.Interval(hwid_digest.offset,
                          hwid_digest.offset + hwid_digest.size)]
    hash_intervals = interval.MergeAndExcludeIntervals(
        include_intervals, exclude_intervals)

    # ap_ro_hash.py takes offset:size in hex as range parameters.
    cmd = 'ap_ro_hash.py %s' % ' '.join(
        ['%x:%x' % (i.start, i.size) for i in hash_intervals])
    result = self._util.shell(cmd)
    if result.status == 0:
      if 'SUCCEEDED' in result.stdout:
        logging.info('Successfully set AP-RO hash on Cr50.')
      else:
        logging.error(result.stderr)
        raise Error('Failed to set AP-RO hash on Cr50.')
    else:
      raise Error('Failed to run ap_ro_hash.py.')

  def Cr50SetSnBits(self):
    """Set the serial number bits on the Cr50 chip.

    Serial number bits along with the board id allow a device to attest to its
    identity and participate in Chrome OS Zero-Touch.

    A script located at /usr/share/cros/cr50-set-sn-bits.sh helps us
    to set the proper serial number bits in the Cr50 chip.
    """

    script_path = '/usr/share/cros/cr50-set-sn-bits.sh'

    vpd_key = 'attested_device_id'
    has_vpd_key = self._vpd.GetValue(vpd_key) is not None

    # The script exists, Zero-Touch is enabled.
    if not has_vpd_key:
      # TODO(stimim): What if Zero-Touch is enabled on a program (e.g. hatch),
      # but not expected for a project (e.g. kohaku).
      raise Error('Zero-Touch is enabled, but %r is not set' % vpd_key)

    if phase.GetPhase() >= phase.PVT_DOGFOOD:
      arg_phase = 'pvt'
    else:
      arg_phase = 'dev'

    result = self._util.shell([script_path])
    if result.status == 0:
      logging.info('Successfully set serial number bits on Cr50.')
    elif result.status == 2:
      logging.error('Serial number bits have already been set on Cr50!')
    elif result.status == 3:
      error_msg = 'Serial number bits have been set DIFFERENTLY on Cr50!'
      if arg_phase == 'pvt':
        raise Error(error_msg)
      logging.error(error_msg)
    else:  # General errors.
      raise Error('Failed to set serial number bits on Cr50. '
                  '(args=%s)' % arg_phase)

  def Cr50SetBoardId(self, is_whitelabel):
    """Set the board id and flags on the Cr50 chip.

    The Cr50 image need to be lock down for a certain subset of devices for
    security reason. To achieve this, we need to tell the Cr50 which board
    it is running on, and which phase is it, during the factory flow.

    A script located at /usr/share/cros/cr50-set-board-id.sh helps us
    to set the board id and phase to the Cr50 ship.

    To the detail design of the lock-down mechanism, please refer to
    go/cr50-boardid-lock for more details.
    """

    script_path = '/usr/share/cros/cr50-set-board-id.sh'
    if not os.path.exists(script_path):
      logging.warning('The Cr50 script is not found, there should be no '
                      'Cr50 on this device.')
      return

    if is_whitelabel:
      # For whitelabel devices, the phase argument is always 'whitelabel'.
      arg_phase = 'whitelabel'
    elif phase.GetPhase() >= phase.PVT_DOGFOOD:
      arg_phase = 'pvt'
    else:
      arg_phase = 'dev'

    try:
      result = self._util.shell([script_path, arg_phase])
      if result.status == 0:
        logging.info('Successfully set board ID on Cr50 with phase %s.',
                     arg_phase)
      elif result.status == 2:
        logging.error('Board ID has already been set on Cr50!')
      elif result.status == 3:
        error_msg = 'Board ID and/or flag has been set DIFFERENTLY on Cr50!'
        if arg_phase == 'pvt':
          raise Error(error_msg)
        logging.error(error_msg)
      else:  # General errors.
        raise Error('Failed to set board ID and flag on Cr50. '
                    '(args=%s)' % arg_phase)
    except Exception:
      logging.exception('Failed to set Cr50 Board ID.')
      raise

  def Cr50WriteFlashInfo(self, enable_zero_touch=False, rma_mode=False):
    """Write device info into cr50 flash."""
    cros_config = cros_config_module.CrosConfig(self._util.shell)
    is_whitelabel, whitelabel_tag = cros_config.GetWhiteLabelTag()

    if is_whitelabel:
      # If we can't find whitelabel_tag in VPD, this will be None.
      vpd_whitelabel_tag = self._vpd.GetValue('whitelabel_tag')
      if vpd_whitelabel_tag != whitelabel_tag:
        if vpd_whitelabel_tag is None:
          # whitelabel_tag is not set in VPD.  Technically, this is allowed by
          # cros_config. It would be equivalent to whitelabel_tag='' (empty
          # string).  However, it is ambiguous, we don't know if this is
          # intended or not.  Therefore, we enforce the whitelabel_tag should be
          # set explicitly, even if it is an empty string.
          raise Error('This is a whitelabel device, but whitelabel_tag is not '
                      'set in VPD.')
        # whitelabel_tag is set in VPD, but it is different from what is
        # reported by cros_config.  We don't allow this, because whitelabel
        # tag affects RLZ code, and RLZ code will be written to cr50 board ID.
        raise Error('whitelabel_tag reported by cros_config and VPD does not '
                    'match.  Have you reboot the device after updating VPD '
                    'fields?')
    if not rma_mode and enable_zero_touch:
      self.Cr50SetSnBits()
    self.Cr50SetBoardId(is_whitelabel)

  def Cr50WriteWhitelabelFlags(self):
    cros_config = cros_config_module.CrosConfig(self._util.shell)
    is_whitelabel, unused_whitelabel_tag = cros_config.GetWhiteLabelTag()
    if not is_whitelabel:
      raise Error('This is not a whitelabel device.')

    script_path = '/usr/share/cros/cr50-set-board-id.sh'
    if not os.path.exists(script_path):
      logging.warning('The Cr50 script is not found, there should be no '
                      'Cr50 on this device.')
      return

    try:
      result = self._util.shell([script_path, 'whitelabel_flags'])
      if result.status == 0:
        logging.info('Successfully set whitelabel flags.')
      elif result.status == 2:
        logging.error('Whitelabel flags has already been set.')
      elif result.status == 3:
        error_msg = 'Board ID and/or flag has been set DIFFERENTLY on Cr50!'
        raise Error(error_msg)
      else:  # General errors.
        raise Error('Failed to set whitelabel flags.')
    except Exception:
      logging.exception('Failed to set Cr50 whitelabel flags.')
      raise

  def Cr50DisableFactoryMode(self):
    """Disable Cr50 Factory mode.

    Cr50 factory mode might be enabled in the factory and RMA center in order to
    open ccd capabilities. Before finalizing the DUT, factory mode MUST be
    disabled.
    """
    gsctool = gsctool_module.GSCTool(self._util.shell)

    def _IsCCDInfoMandatory():
      cr50_verion = gsctool.GetCr50FirmwareVersion().rw_version
      # If second number is odd in version then it is prod version.
      is_prod = int(cr50_verion.split('.')[1]) % 2

      res = True
      if is_prod and LooseVersion(cr50_verion) < LooseVersion('0.3.9'):
        res = False
      elif not is_prod and LooseVersion(cr50_verion) < LooseVersion('0.4.5'):
        res = False

      return res

    try:
      try:
        board_id = gsctool.GetBoardID()
      except gsctool_module.GSCToolError as e:
        raise Error('Failed to get boardID with gsctool command: %r' % e)

      RLZ = self._util.shell(['mosys', 'platform', 'brand']).stdout.strip()
      if RLZ == '':
        raise Error('RLZ code is empty.')
      if board_id.type != int(codecs.encode(RLZ.encode('ascii'), 'hex'), 16):
        raise Error('RLZ does not match Board ID.')

      try:
        gsctool.SetFactoryMode(False)
        factory_mode_disabled = True
      except gsctool_module.GSCToolError:
        factory_mode_disabled = False

      if not _IsCCDInfoMandatory():
        logging.warning('Command of disabling factory mode %s and can not get '
                        'CCD info so there is no way to make sure factory mode '
                        'status.  cr50 version RW %s',
                        'succeeds' if factory_mode_disabled else 'fails',
                        gsctool.GetCr50FirmwareVersion().rw_version)
        return

      is_factory_mode = gsctool.IsFactoryMode()

    except gsctool_module.GSCToolError as e:
      raise Error('gsctool command fail: %r' % e)

    except Exception as e:
      raise Error('Unknown exception from gsctool: %r' % e)

    if is_factory_mode:
      raise Error('Failed to disable Cr50 factory mode.')

  def FpmcuInitializeEntropy(self):
    """Initialze entropy of FPMCU.

    Verify entropy of FPMCU is not added yet and initialize the entropy in
    FPMCU.
    """

    RBINFO_PATTERN = r'^Rollback block id:\s*(\d)+$'
    RBINFO_REGEX = re.compile(RBINFO_PATTERN, re.MULTILINE)
    RBINFO_CMD = ['ectool', '--name=cros_fp', 'rollbackinfo']
    def get_rbinfo():
      proc = self._util.shell(RBINFO_CMD)
      if not proc.success:
        raise Error('Fail to call %r. Log:\n%s' %
                    (RBINFO_CMD, proc.stderr))
      result = RBINFO_REGEX.search(proc.stdout)
      if result is None:
        raise Error('FPS rollback info not found.\n'\
                    '%r not found in:\n%s' % (RBINFO_PATTERN, proc.stdout))
      return int(result.group(1))

    if get_rbinfo() != 0:
      raise Error('FPMCU entropy should not be initialized already.')
    BIOWASH_CMD = ['bio_wash', '--factory_init']
    biowash = self._util.shell(BIOWASH_CMD)

    if not biowash.success:
      raise Error('Fail to call %r. Log:\n%s' %
                  (BIOWASH_CMD, biowash.stderr))
    if get_rbinfo() != 1:
      raise Error('FPMCU entropy cannot be initialized properly.\n'\
                  'Log of %r:\n%s' % (BIOWASH_CMD, biowash.stderr))
    logging.info('FPMCU entropy initialized successfully.')
