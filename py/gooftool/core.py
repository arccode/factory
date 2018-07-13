# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

from collections import namedtuple
from contextlib import contextmanager
import datetime
from distutils.version import LooseVersion
import logging
import os
import re
import sys
import tempfile
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.gooftool.bmpblk import unpack_bmpblock
from cros.factory.gooftool.common import Util
from cros.factory.gooftool import crosfw
from cros.factory.gooftool import vpd_data
from cros.factory.gooftool import wipe
from cros.factory.hwid.v2 import hwid_tool
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.test.l10n import regions
from cros.factory.test.rules import phase
from cros.factory.test.rules.privacy import FilterDict
from cros.factory.test.rules import registration_codes
from cros.factory.test.rules.registration_codes import RegistrationCode
from cros.factory.utils import file_utils
from cros.factory.utils import service_utils
from cros.factory.utils import sys_utils
from cros.factory.utils.type_utils import Error

# The mismatch result tuple.
Mismatch = namedtuple('Mismatch', ['expected', 'actual'])


class Gooftool(object):
  """A class to perform hardware probing and verification and to implement
  Google required tests.

  Properties:
    db: The HWID DB.  This is lazily loaded the first time it is used.
    _db_creator: The function used to create the db object the first time
      it is used.
  """
  # TODO(andycheng): refactor all other functions in gooftool.py to this.

  def __init__(self, hwid_version=2,
               hardware_db=None, component_db=None,
               project=None, hwdb_path=None):
    """Constructor.

    Args:
      hwid_version: The HWID version to operate on. Currently there are only two
        options: 2 or 3.
      hardware_db: The hardware db to use. If not specified, the one in
        hwid_tool.DEFAULT_HWID_DATA_PATH is used.
      component_db: The component db to use for both component names and
        component classes lookup. If not specified,
        hardware_db.component.db is used.
      project: A string indicating which project-specific component database to
        load. If not specified, the project name will be detected with
        cros.factory.hwid.ProbeProject(). Used for HWID v3 only.
      hwdb_path: The path to load the project-specific component database from.
        If not specified, cros.factory.hwid.hwid_utils.GetDefaultDataPath() will
        be used.  Used for HWID v3 only.
    """
    self._hwid_version = hwid_version
    if hwid_version == 2:
      self._hardware_db = (
          hardware_db or
          hwid_tool.HardwareDb(hwid_tool.DEFAULT_HWID_DATA_PATH))
      self._db_creator = lambda: component_db or self._hardware_db.comp_db
    elif hwid_version == 3:
      self._project = project or hwid_utils.ProbeProject()
      self._hwdb_path = hwdb_path or hwid_utils.GetDefaultDataPath()
      self._db_creator = lambda: Database.LoadFile(
          os.path.join(self._hwdb_path, self._project.upper()))
    else:
      raise ValueError('Invalid HWID version: %r' % hwid_version)

    self._util = Util()
    self._crosfw = crosfw
    self._vpd = sys_utils.VPDTool()
    self._unpack_bmpblock = unpack_bmpblock
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
        futil_out = self._util.shell(
            'futility show --type rwsig %s' % tmp_ec_bin.name)
        if not futil_out.success:
          raise Error('Failed to get EC pubkey hash: %s' % futil_out.stderr)
        # The pattern output of the futility show is:
        # Public Key file:       /tmp/ec_binasdf1234
        #    Vboot API:           2.1
        #    Desc:                ""
        #    Signature Algorithm: 7 RSA3072EXP3
        #    Hash Algorithm:      2 SHA256
        #    Version:             0x00000001
        #    ID:                  c80def123456789058e140bbc44c692cc23ecb4d
        #  Signature:             /tmp/ec_binasdf1234
        #    Vboot API:           2.1
        #    Desc:                ""
        #    Signature Algorithm: 7 RSA3072EXP3
        #    Hash Algorithm:      2 SHA256
        #    Total size:          0x1b8 (440)
        #    ID:                  c80def123456789058e140bbc44c692cc23ecb4d
        #    Data size:           0x17164 (94564)
        #  Signature verification succeeded.
        live_ec_hash = re.search(r'\n\s*ID:\s*[a-z0-9]*',
                                 futil_out.stdout).group(0).split()[1]
        if live_ec_hash != pubkey_hash:
          raise Error('Failed to verify EC key: expects (%s) got (%s)' %
                      (pubkey_hash, live_ec_hash))
      else:
        raise ValueError('All arguments are None.')

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
                             f.read(64 * 1048576))
      logging.debug('extract firmware from %s', firmware_path)
      for section in ('GBB', 'FW_MAIN_A', 'FW_MAIN_B', 'VBLOCK_A', 'VBLOCK_B'):
        file_utils.WriteFile(os.path.join(tmpdir, section),
                             firmware_image.get_section(section))

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
        logging.warn('YOU ARE TRYING TO FINALIZE WITH DEV ROOTKEY.')

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

  def VerifySystemTime(self, release_rootfs=None, system_time=None):
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
      raise Error('System time (%s) earlier than file system (%s) creation '
                  'time (%s)' % (system_time, release_rootfs, created_time))

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
    for key, value in expected_status.iteritems():
      if open(os.path.join(tpm_root, key)).read().strip() != value:
        raise Error('TPM is not cleared.')

  def VerifyManagementEngineLocked(self):
    """Verify Management Engine is locked."""
    mainfw = self._crosfw.LoadMainFirmware().GetFirmwareImage()
    if not mainfw.has_section('SI_ME'):
      logging.info('System does not have Management Engine.')
      return
    # If ME is locked, it should contain only 0xFFs.
    data = mainfw.get_section('SI_ME').strip(chr(0xFF))
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
      else:
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
      for k, v in data.iteritems():
        if k in known:
          checked.append(MatchWhole(k, known[k], v))
        else:
          # Try if matches optional_re
          for rk, rv in optional_re.iteritems():
            if MatchWhole(k, rk, k, raise_exception=False):
              checked.append(MatchWhole(k, rv, v))
              break
          else:
            raise KeyError('Unexpected %s VPD: %s=%s.' % (section, k, v))

      missing_keys = set(required).difference(checked)
      if missing_keys:
        raise Error('Missing required %s VPD values: %s' %
                    (section, ','.join(missing_keys)))

    # Check required data
    ro_vpd = self._vpd.GetAllData(partition=self._vpd.RO_PARTITION)
    rw_vpd = self._vpd.GetAllData(partition=self._vpd.RW_PARTITION)
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

    for type_prefix in ['UNIQUE', 'GROUP']:
      vpd_field_name = type_prefix[0].lower() + 'bind_attribute'
      type_name = getattr(RegistrationCode.Type, type_prefix + '_CODE')
      try:
        registration_codes.CheckRegistrationCode(
            rw_vpd[vpd_field_name], type=type_name, device=self._project)
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
                  station_ip=None, station_port=None, wipe_finish_token=None):
    """Start transition to release state directly without reboot.

    Args:
      is_fast: Whether or not to apply fast wipe.
    """
    wipe.WipeInTmpFs(is_fast, shopfloor_url,
                     station_ip, station_port, wipe_finish_token)

  def WipeInit(self, wipe_args, shopfloor_url, state_dev,
               release_rootfs, root_disk, old_root, station_ip, station_port,
               wipe_finish_token):
    """Start wiping test image."""
    wipe.WipeInit(wipe_args, shopfloor_url, state_dev,
                  release_rootfs, root_disk, old_root, station_ip, station_port,
                  wipe_finish_token)

  def WriteVPDForRLZPing(self, embargo_offset=7):
    """Write VPD values related to RLZ ping into VPD."""

    if embargo_offset < 7:
      raise Error('embargo end date offset cannot less than 7 (days)')

    embargo_date = datetime.date.today()
    embargo_date += datetime.timedelta(days=embargo_offset)

    self._vpd.UpdateData({
        'should_send_rlz_ping': '1',
        'rlz_embargo_end_date': embargo_date.isoformat(),
    }, partition=self._vpd.RW_PARTITION)

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

  def VerifyWPSwitch(self):
    """Verifies hardware write protection switch is enabled.

    Raises:
      Error when there is an error.
    """

    if self._util.shell('crossystem wpsw_cur').stdout.strip() != '1':
      raise Error('write protection switch is disabled')

  def CheckDevSwitchForDisabling(self):
    """Checks if the developer switch is ready for disabling.

    It checks the developer switch is either already disabled or is virtual so
    it could be disabled programmatically.

    Returns:
      Whether or not the developer switch is virtual.

    Raises:
      Error, if the developer switch is not ready for disabling. i.e. it is not
      disabled and it is not virtual.
    """

    VBSD_HONOR_VIRT_DEV_SWITCH = 0x400
    if (self._util.GetVBSharedDataFlags() & VBSD_HONOR_VIRT_DEV_SWITCH) != 0:
      # Note when the system is using virtual developer switch. It could be
      # disabled by "crossystem disable_dev_request=1", which is exactly what
      # it does in prepare_wipe.sh.
      return True

    if self._util.GetCurrentDevSwitchPosition() == 0:
      return False

    raise Error('developer mode is not disabled')

  def GetBitmapLocales(self, image_file):
    """Get bitmap locales

    Args:
      image_file: Path to the image file where locales are searched.

    Returns:
      List of language codes supported by the image
    """
    bitmap_locales = []
    with self._named_temporary_file() as f:
      self._util.shell('cbfstool %s extract -n locales -f %s -r COREBOOT' %
                       (image_file, f.name))
      bitmap_locales = f.read()
      # We reach here even if cbfstool command fails
      if bitmap_locales:
        return bitmap_locales.split('\n')
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
    ro_vpd = self._vpd.GetAllData(partition=self._vpd.RO_PARTITION)
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

    # Note: Handle the shell commands with care since unit tests cannot
    # ensure the correctness of commands executed in shell.
    return {
        'platform_name': self._util.shell('mosys platform name').stdout.strip(),
        'crossystem': self._util.GetCrosSystem(),
        'modem_status': self._util.shell('modem status').stdout.splitlines(),
        'ec_wp_status': self._util.shell(
            'flashrom -p ec --get-size 2>/dev/null && '
            'flashrom -p ec --wp-status || '
            'echo "EC is not available."').stdout,
        'bios_wp_status': self._util.shell(
            'flashrom -p host --wp-status').stdout}

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

    rw_vpd = self._vpd.GetAllData(partition=self._vpd.RW_PARTITION)
    dot_entries = dict((k, v) for k, v in rw_vpd.iteritems() if '.' in k)
    entries = dict((k, v) for k, v in dot_entries.iteritems()
                   if _IsFactoryVPD(k))
    unknown_keys = set(dot_entries) - set(entries)
    if unknown_keys:
      raise Error('Found unexpected RW VPD(s): %r' % unknown_keys)

    logging.info('Removing VPD entries %s', FilterDict(entries))
    if entries:
      try:
        self._vpd.UpdateData(dict((k, None) for k in entries.keys()),
                             partition=self._vpd.RW_PARTITION)
      except Exception as e:
        raise Error('Failed to remove VPD entries: %r' % e)

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
        raise Error, cause, exc_traceback

    with scrub_exceptions('Error generating device secret'):
      # Generate the stable device secret and write it to VPD. Turn off logging,
      # so the generated secret doesn't leak to the logs.
      secret = self._util.shell('tpm-manager get_random 32',
                                log=False).stdout.strip()

    with scrub_exceptions('Error validating device secret'):
      secret_bytes = secret.decode('hex')
      if len(secret_bytes) != 32:
        raise Error

    with scrub_exceptions('Error writing device secret to VPD'):
      self._vpd.UpdateData(
          {'stable_device_secret_DO_NOT_SHARE': secret_bytes.encode('hex')},
          partition=self._vpd.RO_PARTITION)


  def Cr50SetBoardId(self):
    """Set the board id and flag on the Cr50 chip.

    The Cr50 image need to be lock down for a certain subset of devices for
    security reason. To achieve this, we need to tell the Cr50 which board
    it is running on, and which phase is it, during the factory flow.

    A script located at /usr/share/cros/cr50-set-board-id.sh helps us
    to set the board id and phase to the Cr50 ship.

    To the detail design of the lock-down mechanism, please refer to
    go/cr50-boardid-lock for more details.
    """

    script_path = '/usr/share/cros/cr50-set-board-id.sh'
    disable_services = ['trunksd']

    if not os.path.exists(script_path):
      logging.warn('The Cr50 script is not found, there should be no '
                   'Cr50 on this device.')
      return

    if phase.GetPhase() >= phase.PVT_DOGFOOD:
      arg_phase = 'pvt'
    else:
      arg_phase = 'dev'

    # TODO(hungte) Remove the service management once cr50-set-board-id.sh
    # has been changed to use '-a' (any) method.
    service_mgr = service_utils.ServiceManager()

    try:
      service_mgr.SetupServices(disable_services=disable_services)

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
        else:
          logging.error(error_msg)
      else:  # General errors.
        raise Error('Failed to set board ID and flag on Cr50. '
                    '(args=%s)' % arg_phase)

    except Exception:
      logging.exception('Failed to set Cr50 Board ID.')
      raise

    finally:
      # Restart stopped service even if something went wrong.
      service_mgr.RestoreServices()


  def Cr50DisableFactoryMode(self):
    """Disable Cr50 Factory mode.

    Cr50 factory mode might be enabled in the factory and RMA center in order to
    open ccd capabilities. Before finalizing the DUT, factory mode MUST be
    disabled.
    """
    def _GetCr50Version():
      cmd = ['gsctool', '-a', '-f']
      return re.search(r'^RW\s*(\d+\.\d+\.\d+)',
                       self._util.shell(cmd).stdout,
                       re.MULTILINE).group(1)

    def _IsCCDInfoMandatory():
      cr50_verion = _GetCr50Version()
      # If second number is odd in version then it is prod version.
      is_prod = (1 == int(cr50_verion.split('.')[1]) % 2)

      res = True
      if is_prod and LooseVersion(cr50_verion) < LooseVersion('0.3.5'):
        res = False
      elif not is_prod and LooseVersion(cr50_verion) < LooseVersion('0.4.5'):
        res = False

      return res

    gsctool_path = '/usr/sbin/gsctool'
    if not os.path.exists(gsctool_path):
      raise Error('gsctool is not available in path - %s.' % gsctool_path)

    factory_mode_disabled = False
    cmd = ['gsctool', '-a', '-F', 'disable']
    result = self._util.shell(cmd)
    if result.success:
      factory_mode_disabled = True

    if not _IsCCDInfoMandatory():
      logging.warn('Command of disabling factory mode %s and can not get CCD '
                   'info so there is no way to make sure factory mode status. '
                   'cr50 version RW %s',
                   'succeeds' if factory_mode_disabled else 'fails',
                   _GetCr50Version())
      return

    ccd_info_cmd = ['gsctool', '-a', '-I']
    result = self._util.shell(ccd_info_cmd)
    if not result.success:
      raise Error('Getting ccd info fails in cr50 RW %s' % _GetCr50Version())

    info = result.stdout
    # The pattern of output is:
    # State: Locked
    # Password: None
    # Flags: 000000
    # Capabilities, current and default:
    #   ...
    # CCD caps bitmap: 0x1ffff
    if re.search("^CCD caps bitmap: 0x1ffff$", info, re.MULTILINE):
      raise Error('Failed to disable Cr50 factory mode. CCD info:\n%s' % info)
