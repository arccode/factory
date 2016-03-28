#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import logging
import os
import re
import sys
import time

from collections import namedtuple
from contextlib import contextmanager
from distutils.version import LooseVersion
from tempfile import NamedTemporaryFile

import factory_common  # pylint: disable=W0611
from cros.factory.hwid.v2 import hwid_tool
from cros.factory.hwid.v3 import common as hwid3_common
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3.decoder import Decode
from cros.factory.gooftool import crosfw
from cros.factory.gooftool.bmpblk import unpack_bmpblock
from cros.factory.gooftool.common import Shell
from cros.factory.gooftool.probe import DeleteRwVpd
from cros.factory.gooftool.probe import Probe
from cros.factory.gooftool.probe import ReadRoVpd
from cros.factory.gooftool.probe import ReadRwVpd
from cros.factory.gooftool.probe import UpdateRoVpd
from cros.factory.test.l10n import regions
from cros.factory.test.rules import branding
from cros.factory.test.rules import phase
from cros.factory.test.rules.privacy import FilterDict
from cros.factory.utils import file_utils
from cros.factory.utils import sys_utils
from cros.factory.utils.type_utils import Error

# A named tuple to store the probed component name and the error if any.
ProbedComponentResult = namedtuple('ProbedComponentResult',
                                   ['component_name', 'probed_string', 'error'])

# The mismatch result tuple.
Mismatch = namedtuple('Mismatch', ['expected', 'actual'])


class Util(object):
  """A collection of util functions that Gooftool needs."""

  def __init__(self):
    self.shell = Shell

  def _IsDeviceFixed(self, dev):
    """Check if a device is a fixed device, i.e. not a removable device.

    Args:
      dev: A device string under /sys/block.

    Returns:
      True if the given device is fixed, and false if it is not.
    """

    sysfs_path = '/sys/block/%s/removable' % dev
    return (os.path.exists(sysfs_path) and
            open(sysfs_path).read().strip() == '0')

  def GetPrimaryDevicePath(self, partition=None):
    """Gets the path for the primary device, which is the only non-removable
    device in the system.

    Args:
      partition: The index of the partition on primary device.

    Returns:
      The path to the primary device. If partition is specified, the path
      points to that partition of the primary device. e.g. /dev/sda1
    """

    alpha_re = re.compile(r'^/dev/([a-zA-Z]+)[0-9]+$')
    alnum_re = re.compile(r'^/dev/([a-zA-Z]+[0-9]+)p[0-9]+$')
    matched_alnum = False
    dev_set = set()
    for path in self.shell('cgpt find -t rootfs').stdout.strip().split():
      for dev in alpha_re.findall(path):
        if self._IsDeviceFixed(dev):
          dev_set.add(dev)
          matched_alnum = False
      for dev in alnum_re.findall(path):
        if self._IsDeviceFixed(dev):
          dev_set.add(dev)
          matched_alnum = True
    if len(dev_set) != 1:
      raise Error('zero or multiple primary devs: %s' % dev_set)
    dev_path = os.path.join('/dev', dev_set.pop())
    if partition is None:
      return dev_path
    fmt_str = '%sp%d' if matched_alnum else '%s%d'
    return fmt_str % (dev_path, partition)

  def GetPartitionDevice(self, path):
    """Returns a device path string from partition path.

    /dev/sda1 => /dev/sda.
    /dev/mmcblk0p2 => /dev/mmcblk0.
    """
    return ''.join(re.findall(
        r'(.*[^0-9][0-9]+)p[0-9]+|(.*[^0-9])[0-9]+', path)[0])

  def FindScript(self, script_name):
    """Finds the script under /usr/local/factory/sh

    Args:
      script_name: The name of the script to look for.

    Returns:
      The path of the found script.

    Raises:
      Error if the script is not found.
    """

    # __file__ is in /usr/local/factory/py/gooftool/__init__.py
    factory_base = os.path.realpath(os.path.join(
        os.path.dirname(os.path.realpath(__file__)), '..', '..'))
    script_path = os.path.join(factory_base, 'sh', script_name)
    if not os.path.isfile(script_path):
      raise Error('Needed script %s does not exist.' % script_path)
    return script_path

  def FindAndRunScript(self, script_name, post_opts=None, pre_opts=None):
    """Finds and runs the script with given options.

    Args:
      script_name: The name of the script to look up and run.
      post_opts: A list of strings that will be appended in the command after
        the script's name.
      pre_opts: A list of strings that will be prepended in the command before
        the script's name.

    Returns:
      The result of execusion.

    Raises:
      Error if execusion failed.
    """

    assert not post_opts or isinstance(post_opts, list)
    assert not pre_opts or isinstance(pre_opts, list)

    script = self.FindScript(script_name)
    cmd = '%s %s %s' % (' '.join(pre_opts) if pre_opts else '',
                        script,
                        ' '.join(post_opts) if post_opts else '')
    result = self.shell(cmd.strip())
    if not result.success:
      raise Error, '%r failed, stderr: %r' % (cmd, result.stderr)

    return result

  def GetReleaseRootPartitionPath(self):
    """Gets the path for release root partition."""

    return self.GetPrimaryDevicePath(5)

  def GetReleaseKernelPartitionPath(self):
    """Gets the path for release kernel partition."""

    return self.GetPrimaryDevicePath(4)

  def GetReleaseImageLsbData(self):
    """Gets the /etc/lsb-release content from release image partition.

    Returns:
      A dictionary containing the key-value pairs in lsb-release.
    """
    lsb_content = sys_utils.MountDeviceAndReadFile(
        self.GetReleaseRootPartitionPath(), 'etc/lsb-release')
    return dict(re.findall('^(.+)=(.+)$', lsb_content, re.MULTILINE))

  def GetAllowedReleaseImageChannels(self):
    """Returns a list of channels allowed for release image."""
    return ['dev', 'beta', 'stable']

  def GetReleaseImageChannel(self):
    """Returns the channel of current release image."""
    return self.GetReleaseImageLsbData().get('CHROMEOS_RELEASE_TRACK')

  def GetReleaseImageVersion(self):
    """Returns the current release image version."""
    return self.GetReleaseImageLsbData().get('GOOGLE_RELEASE')

  def GetVBSharedDataFlags(self):
    """Gets VbSharedData flags.

    Returns:
      An integer representation of the flags.
    """

    return int(self.shell('crossystem vdat_flags').stdout.strip(), 0)

  def GetCurrentDevSwitchPosition(self):
    """Gets the position for the current developer switch.

    Returns:
      An integer representation of the current developer switch position.
    """
    return int(self.shell('crossystem devsw_cur').stdout.strip(), 0)

  def GetCrosSystem(self):
    """Gets the output of 'crossystem'.

    Returns:
      A dict for key-value pairs for the output of 'crossystem'.
      e.g. {'flag_name': 'flag_value'}
    """
    crossystem_result = self.shell('crossystem').stdout.strip().splitlines()
    # The crossytem output contains many lines like:
    # 'key = value  # description'
    # Use regexps to pull out the key-value pairs and build a dict.
    # Note that value could also contain equal signs.
    output = {}
    for entry in crossystem_result:
      # Any unrecognized format should fail here.
      key, value = re.findall(r'\A(\S+)\s+=\s+(.*)#.*\Z', entry)[0]
      output[key] = value.strip()

    return output

  def GetCgptAttributes(self, device=None):
    if device is None:
      device = self.GetPrimaryDevicePath()

    attrs = {}
    for line in self.shell('cgpt show %s -q' % device).stdout.splitlines():
      # format: offset size no name
      part_no = line.split()[2]
      attrs[part_no] = self.shell('cgpt show %s -i %s -A' %
                                  (device, part_no)).stdout.strip()
    return attrs

  def SetCgptAttributes(self, attrs, device=None):
    if device is None:
      device = self.GetPrimaryDevicePath()

    curr_attrs = self.GetCgptAttributes()
    for k, v in attrs.iteritems():
      if curr_attrs.get(k) == v:
        continue
      if not self.shell('cgpt add %s -i %s -A %s' % (device, k, v)).success:
        raise Error('Failed to set device config: %s#%s=%s' % (device, k, v))

  def InvokeChromeOSPostInstall(self, root_dev=None):
    """Invokes the ChromeOS post-install script (/postinst)."""
    if root_dev is None:
      root_dev = self._util.GetReleaseRootPartitionPath()

    logging.info('Running ChromeOS post-install on %s...' % root_dev)

    # Some compatible and experimental fs (e.g., ext4) may be buggy and still
    # try to write the file system even if we mount it with "ro" (ex, when
    # seeing journaling error in ext3, or s_kbytes_written in ext4). It is
    # safer to always mount the partition with legacy ext2. (ref:
    # chrome-os-partner:3940)
    with sys_utils.MountPartition(root_dev, fstype='ext2') as mount_path:
      # IS_FACTORY_INSTALL is used to prevent postinst trying to update firmare.
      command = ('IS_FACTORY_INSTALL=1 IS_INSTALL=1 "%s"/postinst %s' %
                 (mount_path, root_dev))
      result = self.shell(command)
      if not result.success:
        raise Error('chromeos-postinst on %s failed with error: code=%s. %s' %
                    (root_dev, result.status, result.stderr))

  def EnableKernel(self, device, part_no):
    """Enables the kernel partition from GPT."""
    logging.info('Enabling kernel on %s#%s...', device, part_no)
    r = self.shell('cgpt add -i %s -P 3 -S 1 -T 0 %s' % (part_no, device))
    if not r.success:
      raise Error('Failed to enable kernel on %s#%s' % (device, part_no))

  def DisableKernel(self, device, part_no):
    """Disables the kernel partition from GPT."""
    logging.info('Disabling kernel on %s#%s...', device, part_no)
    r = self.shell('cgpt add -i %s -P 0 -S 0 -T 0 %s' % (part_no, device))
    if not r.success:
      raise Error('Failed to disable kernel on %s#%s' % (device, part_no))

  def IsChromeOSFirmware(self):
    """Returns if the system is running ChromeOS firmware."""
    r = self.shell('crossystem mainfw_type')
    return r.success and r.stdout.strip() != 'nonchrome'

  def EnableReleasePartition(self, root_dev):
    """Enables a release image partition on disk."""
    # TODO(hungte) replce sh/enable_release_partition.sh
    release_no = int(root_dev[-1]) - 1
    factory_map = {2: 4, 4: 2}
    if release_no not in factory_map:
      raise ValueError('EnableReleasePartition: Cannot identify kernel %s' %
                       root_dev)

    factory_no = factory_map[release_no]
    device = self.GetPartitionDevice(root_dev)
    curr_attrs = self.GetCgptAttributes(device)
    try:
      # When booting with legacy firmware, we need to update the legacy boot
      # loaders to activate new kernel; on a real ChromeOS firmware, only CGPT
      # header is used, and postinst is already performed in verify_rootfs.
      if self.IsChromeOSFirmware():
        self.InvokeChromeOSPostInstall(root_dev)
      self.shell('crossystem disable_dev_request=1')
      self.DisableKernel(device, factory_no)
      self.EnableKernel(device, release_no)
      # Enforce a sync and wait for underlying hardware to flush.
      logging.info('Syncing disks...')
      self.shell('sync; sleep 3')
      logging.info('Enable release partition: Complete.')
    except:
      logging.error('FAIL: Failed to enable release partition.')
      self.shell('crossystem disable_dev_request=0')
      self.SetCgptAttributes(curr_attrs, device)


class Gooftool(object):
  """A class to perform hardware probing and verification and to implement
  Google required tests.

  Properties:
    db: The HWID DB.  This is lazily loaded the first time it is used.
    _db_creator: The function used to create the db object the first time
      it is used.
  """
  # TODO(andycheng): refactor all other functions in gooftool.py to this.

  def __init__(self, probe=None, hwid_version=2,
               hardware_db=None, component_db=None,
               board=None, hwdb_path=None):
    """Constructor.

    Args:
      probe: The probe to use for detecting installed components. If not
        specified, cros.factory.gooftool.probe.Probe is used.
      hwid_version: The HWID version to operate on. Currently there are only two
        options: 2 or 3.
      hardware_db: The hardware db to use. If not specified, the one in
        hwid_tool.DEFAULT_HWID_DATA_PATH is used.
      component_db: The component db to use for both component names and
        component classes lookup. If not specified,
        hardware_db.component.db is used.
      board: A string indicating which board-specific component database to
        load. If not specified, the board name will be detected with
        cros.factory.hwid.ProbeBoard(). Used for HWID v3 only.
      hwdb_path: The path to load the board-specific component database from. If
        not specified, cros.factory.hwid.DEFAULT_HWID_DATA_PATH will be used.
        Used for HWID v3 only.
    """
    self._hwid_version = hwid_version
    if hwid_version == 2:
      self._hardware_db = (
          hardware_db or
          hwid_tool.HardwareDb(hwid_tool.DEFAULT_HWID_DATA_PATH))
      self._db_creator = lambda: component_db or self._hardware_db.comp_db
    elif hwid_version == 3:
      self._board = board or hwid3_common.ProbeBoard()
      self._hwdb_path = hwdb_path or hwid3_common.DEFAULT_HWID_DATA_PATH
      self._db_creator = lambda: Database.LoadFile(
          os.path.join(self._hwdb_path, self._board.upper()))
    else:
      raise ValueError('Invalid HWID version: %r' % hwid_version)

    self._probe = probe or Probe
    self._util = Util()
    self._crosfw = crosfw
    self._read_ro_vpd = ReadRoVpd
    self._read_rw_vpd = ReadRwVpd
    self._delete_rw_vpd = DeleteRwVpd
    self._update_ro_vpd = UpdateRoVpd
    self._hwid_decode = Decode
    self._unpack_bmpblock = unpack_bmpblock
    self._named_temporary_file = NamedTemporaryFile
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

  def VerifyComponents(self, component_list):
    """Verifies the given component list against the component db to ensure
    the installed components are correct.

    Args:
      component_list: A list of components to verify.
        (e.g., ['camera', 'cpu'])

    Returns:
      A dict from component class to a list of one or more
      ProbedComponentResult tuples.
      {component class: [ProbedComponentResult(
          component_name,  # The component name if found in the db, else None.
          probed_string,   # The actual probed string. None if probing failed.
          error)]}         # The error message if there is one.
    """
    probeable_classes = self.db.probeable_components.keys()
    if not component_list:
      raise ValueError('No component classes specified;\n' +
                       'Possible choices: %s' % probeable_classes)

    unknown_class = [component_class for component_class in component_list
                     if component_class not in probeable_classes]
    if unknown_class:
      raise ValueError(('Invalid component classes specified: %s\n' +
                        'Possible choices: %s') %
                       (unknown_class, probeable_classes))

    probe_results = self._probe(
        target_comp_classes=component_list,
        probe_volatile=False, probe_initial_config=False)
    result = {}
    for comp_class in sorted(component_list):
      probe_vals = probe_results.found_probe_value_map.get(comp_class, None)

      if probe_vals is not None:
        if isinstance(probe_vals, str):
          # Force cast probe_val to be a list so it is easier to process later
          probe_vals = [probe_vals]

        result_tuples = []
        for val in probe_vals:
          comp_name = self.db.result_name_map.get(val, None)
          if comp_name is not None:
            result_tuples.append(ProbedComponentResult(comp_name, val, None))
          else:
            result_tuples.append(ProbedComponentResult(None, val, (
                'unsupported %r component found with probe result'
                ' %r (no matching name in the component DB)' %
                (comp_class, val))))
        result[comp_class] = result_tuples
      else:
        result[comp_class] = [ProbedComponentResult(None, None, (
            'missing %r component' % comp_class))]

    return result

  def FindBOMMismatches(self, board, bom_name, probed_comps):
    """Finds mismatched components for a BOM.

    Args:
      board: The name of the board containing a list of BOMs .
      bom_name: The name of the BOM listed in the hardware database.
      probed_comps: A named tuple for probed results.
        Format: (component_name, probed_string, error)

    Returns:
      A dict of mismatched component list for the given BOM.
      {component class: [Mismatch(
        expected,  # The expected result.
        actual)]}  # The actual probed result.
    """

    if board not in self._hardware_db.devices:
      raise ValueError('Unable to find BOMs for board %r' % board)

    boms = self._hardware_db.devices[board].boms
    if not bom_name or not probed_comps:
      raise ValueError('both bom_name and probed components must be specified')

    if bom_name not in boms:
      raise ValueError('BOM %r not found. Available BOMs: %s' % (
          bom_name, boms.keys()))

    primary = boms[bom_name].primary
    mismatches = {}

    for comp_class, results in probed_comps.items():
      if comp_class in primary.classes_dontcare:  # skip don't care components
        continue

      # If a component is expected to be missing, then empty probed result
      # is expected.
      if comp_class in primary.classes_missing and (
          not any(result.probed_string for result in results)):
        continue

      if comp_class not in primary.components:
        mismatches[comp_class] = Mismatch(None, results)
        continue

      # Since the component names could be either str or list of str,
      # detect its type before converting to a set.
      expected_names = primary.components[comp_class]
      if isinstance(expected_names, str):
        expected_names = [expected_names]
      expected_names = set(expected_names)

      probed_comp_names = set([result.component_name for result in results])

      if probed_comp_names != expected_names:
        mismatches[comp_class] = Mismatch(expected_names, probed_comp_names)

    return mismatches

  def VerifyKeys(self, kernel_dev=None, firmware_path=None, _tmpexec=None):
    """Verify keys in firmware and SSD match.

    Args:
      kernel_dev: A string for kernel device path.
      firmware_path: A string for firmware image file path.
      _tmpexec: A function for overriding execution inside temp folder.
    """

    if kernel_dev is None:
      kernel_dev = self._util.GetReleaseKernelPartitionPath()
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
               'gbb_utility -g --rootkey %s  --recoverykey %s GBB' %
               (key_root, key_recovery))
      rootkey_hash = _TmpExec(
          'unpack rootkey', 'vbutil_key --unpack %s' % key_root,
          regex=r'(?<=Key sha1sum:).*').strip()
      _TmpExec('unpack recoverykey', 'vbutil_key --unpack %s' % key_recovery)

      # Pre-scan for well-known problems.
      if rootkey_hash == 'b11d74edd286c144e1135b49e7f0bc20cf041f10':
        raise Error('YOU ARE TRYING TO FINALIZE WITH DEV ROOTKEY.')

      _TmpExec('verify firmware A with root key',
               'vbutil_firmware --verify VBLOCK_A --signpubkey %s '
               ' --fv FW_MAIN_A --kernelkey %s' % (key_root, key_normal_a))
      _TmpExec('verify firmware B with root key',
               'vbutil_firmware --verify VBLOCK_B --signpubkey %s '
               ' --fv FW_MAIN_B --kernelkey %s' % (key_root, key_normal_b))

      # Unpack keys and keyblocks
      _TmpExec('unpack kernel keyblock',
               'vbutil_keyblock --unpack %s' % blob_kern)
      try:
        for key in key_normal_a, key_normal_b:
          _TmpExec('unpack %s' % key, 'vbutil_key --unpack %s' % key)
          _TmpExec('verify kernel by %s' % key,
                   'vbutil_kernel --verify %s --signpubkey %s' %
                   (blob_kern, key))

      except Error as e:
        _TmpExec('check recovery key signed image',
                 '! vbutil_kernel --verify %s --signpubkey %s' %
                 (blob_kern, key_recovery),
                 'YOU ARE USING A RECOVERY KEY SIGNED IMAGE.')

        for key in key_normal, key_recovery:
          _TmpExec('check dev-signed image <%s>' % key,
                   '! vbutil_kernel --verify %s --signpubkey %s/%s' %
                   (blob_kern, dir_devkeys, key),
                   'YOU ARE FINALIZING WITH DEV-SIGNED iMAGE <%s>' %
                   key)

    logging.info('SUCCESS: Verification completed.')

  def VerifySystemTime(self, root_dev=None, system_time=None):
    """Verify system time is later than release filesystem creation time."""
    if root_dev is None:
      root_dev = self._util.GetReleaseRootPartitionPath()
    if system_time is None:
      system_time = time.time()

    e2header = self._util.shell('dumpe2fs -h %s' % root_dev)
    if not e2header.success:
      raise Error('Failed to read file system: %s, %s' %
                  (root_dev, e2header.stderr))
    matched = re.findall(r'^Filesystem created: *(.*)', e2header.stdout,
                         re.MULTILINE)
    if not matched:
      raise Error('Failed to find file system creation time: %s' % root_dev)
    created_time = time.mktime(time.strptime(matched[0]))
    logging.debug('Comparing system time <%s> and filesystem time <%s>',
                  system_time, created_time)
    if system_time < created_time:
      raise Error('System time (%s) earlier than file system (%s) creation '
                  'time (%s)' % (system_time, root_dev, created_time))

  def VerifyRootFs(self, root_dev=None):
    """Verify rootfs on SSD is valid by checking hash."""
    if root_dev is None:
      root_dev = self._util.GetReleaseRootPartitionPath()
    device = self._util.GetPartitionDevice(root_dev)

    # TODO(hungte) Using chromeos_invoke_postinst here is leaving a window
    # where unexpected reboot or test exit may cause the system to boot into
    # the release image. Currently "cgpt" is very close to the last step of
    # postinst so it may be OK, but we should seek for better method for this,
    # for example adding a "--nochange_boot_partition" to chromeos-postinst.
    try:
      # Always rollback GPT changes.
      curr_attrs = self._util.GetCgptAttributes(device)
      self._util.InvokeChromeOSPostInstall(root_dev)
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
        raise Error, 'TPM is not cleared.'

  def VerifyManagementEngineLocked(self):
    """Verify Managment Engine is locked."""
    mainfw = self._crosfw.LoadMainFirmware().GetFirmwareImage()
    if not mainfw.has_section('SI_ME'):
      logging.info('System does not have Management Engine.')
      return True
    # If ME is locked, it should contain only 0xFFs.
    data = mainfw.get_section('SI_ME').strip(chr(0xFF))
    if len(data) != 0:
      raise Error, 'ME (ManagementEngine) firmware may be not locked.'
    # TODO(hungte) In future we may add more checks using ifdtool. See
    # crosbug.com/p/30283 for more information.
    logging.info('Management Engine is locked.')

  def VerifyBranding(self):
    """Verify that branding fields are properly set.

    Returns:
      A dictionary containing rlz_brand_code and customization_id fields,
      for testing.
    """
    ro_vpd = self._read_ro_vpd()
    customization_id = ro_vpd.get('customization_id')
    logging.info('RO VPD customization_id: %r', customization_id)
    if customization_id is not None:
      if not branding.CUSTOMIZATION_ID_REGEXP.match(customization_id):
        raise ValueError(
            'Bad format for customization_id %r in RO VPD '
            '(expected it to match regexp %r)' %
            (customization_id, branding.CUSTOMIZATION_ID_REGEXP.pattern))

    rlz_brand_code = ro_vpd.get('rlz_brand_code')

    logging.info('RO VPD rlz_brand_code: %r', rlz_brand_code)
    if rlz_brand_code is None:
      # It must be present as BRAND_CODE_PATH in rootfs.
      with sys_utils.MountPartition(
          self._util.GetReleaseRootPartitionPath()) as mount_path:
        path = os.path.join(mount_path, branding.BRAND_CODE_PATH.lstrip('/'))
        if not os.path.exists(path):
          raise ValueError('rlz_brand_code is not present in RO VPD, and %s '
                           'does not exist in release rootfs' % (
                               branding.BRAND_CODE_PATH))
        with open(path) as f:
          rlz_brand_code = f.read().strip()
          logging.info('rlz_brand_code from rootfs: %r', rlz_brand_code)
      rlz_brand_code_source = 'release_rootfs'
    else:
      rlz_brand_code_source = 'RO VPD'

    if not branding.RLZ_BRAND_CODE_REGEXP.match(rlz_brand_code):
      raise ValueError('Bad format for rlz_brand_code %r in %s '
                       '(expected it to match regexp %r)' % (
                           rlz_brand_code, rlz_brand_code_source,
                           branding.CUSTOMIZATION_ID_REGEXP.pattern))

    phase.AssertStartingAtPhase(
        phase.DVT,
        rlz_brand_code not in branding.TEST_BRAND_CODES,
        'Brand code is %r, but test brand codes are not allowed' %
        rlz_brand_code)

    return dict(rlz_brand_code=rlz_brand_code,
                customization_id=customization_id)

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
    for factory/development.  See "gbb_utility --flags" for details.
    """

    result = self._util.shell('/usr/share/vboot/bin/set_gbb_flags.sh 0 2>&1')
    if not result.success:
      raise Error('Failed setting GBB flags: %s' % result.stdout)

  def _VerifyCutoffArgs(self, cutoff_args):
    """Verify the cutoff args passed to battery_cutoff.sh.

    Raises:
      Error when format is not correct.
    """

    args = cutoff_args.split()
    args_len = len(args)
    if args_len % 2 != 0:
      raise ValueError('Invalid arguments number in cutoff_args')

    for i in range(0, args_len, 2):
      if '--method' == args[i]:
        if args[i + 1] not in (
            'shutdown', 'reboot', 'battery_cutoff',
            'battery_cutoff_at_shutdown'):
          raise ValueError('Invalid value for %s: %s' % (args[i], args[i + 1]))
      elif '--check-ac' == args[i]:
        if args[i + 1] not in ('remove_ac', 'connect_ac'):
          raise ValueError('Invalid value for %s: %s' % (args[i], args[i + 1]))
      elif args[i] in (
          '--min-battery-percent', '--max-battery-percent',
          '--min-battery-voltage', '--max-battery-voltage'):
        try:
          int(args[i + 1])
        except ValueError:
          raise ValueError('Invalid value for %s: %s' % (args[i], args[i + 1]))
      else:
        raise ValueError('Unknown argument in cutoff_args: %s' % args[i])

  def WipeInPlace(self, is_fast=None, cutoff_args=None, shopfloor_url=None):
    """Start transition to release state directly without reboot.

    Args:
      is_fast: Whether or not to apply fast wipe.

      cutoff_args: Args to be passed to battery_cutoff.sh after wiping.
    """
    args = ''
    if is_fast:
      args += 'FAST_WIPE=true\n'

    if cutoff_args:
      self._VerifyCutoffArgs(cutoff_args)
      args += 'CUTOFF_ARGS=%s\n' % cutoff_args

    if shopfloor_url:
      args += 'SHOPFLOOR_URL=%s\n' % shopfloor_url

    if args:
      file_utils.WriteFile('/tmp/factory_wipe_args', args)
    os.system('start factory-wipe')

  def PrepareWipe(self, is_fast=None):
    """Prepare system for transition to release state in next reboot.

    Args:
      is_fast: Whether or not to apply fast wipe.
    """

    self._util.FindAndRunScript(
        'prepare_wipe.sh',
        [self._util.GetReleaseRootPartitionPath()],
        ['FACTORY_WIPE_TAGS=fast'] if is_fast else [])

  def Probe(self, target_comp_classes, fast_fw_probe=False, probe_volatile=True,
            probe_initial_config=True, probe_vpd=False):
    """Returns probed results for device components, hash, and initial config
    data.

    This method is essentially a wrapper for probe.Probe. Please refer to
    probe.Probe for more detailed description.

    Args:
      target_comp_classes: Which component classes to probe for.  A None value
        implies all classes.
      fast_fw_probe: Only probes for firmware versions.
      probe_volatile: On False, do not probe for volatile data and
        return None for the corresponding field.
      probe_initial_config: On False, do not probe for initial_config
        data and return None for the corresponding field.
      probe_vpd: On True, include vpd data in the volatiles.

    Returns:
      cros.factory.hwdb.hwid_tool.ProbeResults object containing the probed
      results.
    """

    return self._probe(target_comp_classes=target_comp_classes,
                       fast_fw_probe=fast_fw_probe,
                       probe_volatile=probe_volatile,
                       probe_initial_config=probe_initial_config,
                       probe_vpd=probe_vpd)

  def WriteHWID(self, hwid=None):
    """Writes specified HWID value into the system BB.

    Args:
      hwid: The HWID string to be written to the device.
    """

    assert hwid
    main_fw = self._crosfw.LoadMainFirmware()
    self._util.shell('gbb_utility --set --hwid="%s" "%s"' %
                     (hwid, main_fw.GetFileName()))
    main_fw.Write(sections=['GBB'])

  def VerifyWPSwitch(self):  # pylint: disable=W0613
    """Verifes hardware write protection switch is enabled.

    Raises:
      Error when there is an error.
    """

    if self._util.shell('crossystem wpsw_cur').stdout.strip() != '1':
      raise Error, 'write protection switch is disabled'

  def CheckDevSwitchForDisabling(self):  # pylint: disable=W0613
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

    raise Error, 'developer mode is not disabled'

  def GetBitmapLocales(self, image_file):
    """Get bitmap locales

    Args:
      image_file: Path to the image file where locales are searched.

    Returns:
      List of language codes supported by the image
    """
    bitmap_locales = []
    with self._named_temporary_file() as f:
      self._util.shell(
          'cbfstool %s extract -n locales -f %s -r COREBOOT' % (image_file, f.name))
      bitmap_locales = f.read()
      # We reach here even if cbfstool command fails
      if bitmap_locales:
        return bitmap_locales.split('\n')
      # Looks like image does not have locales file. Do the old-fashioned way
      self._util.shell('gbb_utility -g --bmpfv=%s %s' % (f.name, image_file))
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
    region = self._read_ro_vpd().get('region', None)
    if region is None:
      raise Error, 'Missing VPD "region".'
    # Use the primary initial locale for the firmware bitmap.
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

    raise Error, ('Firmware bitmaps do not contain support for the specified '
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
    """Clears factory.* items in the RW VPD.

    Returns:
      A dict of the removed entries.
    """
    rw_vpd = self._read_rw_vpd()
    entries = dict((k, v) for k, v in rw_vpd.items()
                   if k.startswith('factory.'))
    logging.info('Removing VPD entries %s', FilterDict(entries))
    if entries:
      if not self._delete_rw_vpd(entries):
        raise Error('Failed to remove VPD entries: %s' % entries.keys())

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
    if not release_image_version >= LooseVersion('6887.0.0'):
      raise Error, 'Release image version can\'t handle stable device secret!'

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
      except:
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
      if not self._update_ro_vpd({
          'stable_device_secret_DO_NOT_SHARE': secret_bytes.encode('hex')}):
        raise Error
