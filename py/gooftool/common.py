# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import pipes
import re
from subprocess import PIPE
from subprocess import Popen

from cros.factory.test.env import paths
from cros.factory.utils import sys_interface as sys_interface_module
from cros.factory.utils import sys_utils
from cros.factory.utils.type_utils import Error
from cros.factory.utils.type_utils import Obj


def Shell(cmd, stdin=None, log=True, sys_interface=None):
  """Run cmd in a shell, return Obj containing stdout, stderr, and status.

  The cmd stdout and stderr output is debug-logged.

  Args:
    cmd: Full shell command line as a string or list, which can contain
      redirection (pipes, etc).
    stdin: String that will be passed as stdin to the command.
    log: log command and result.
    sys_interface: The SystemInterface of the device. If set to None, use Popen.
  """
  if not isinstance(cmd, str):
    cmd = ' '.join(pipes.quote(param) for param in cmd)
  if sys_interface is None:
    process = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True,
                    encoding='utf-8')
  else:
    process = sys_interface.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
  stdout, stderr = process.communicate(input=stdin)
  if log:
    logging.debug('running %s' % repr(cmd) +
                  (', stdout: %s' % repr(stdout.strip()) if stdout else '') +
                  (', stderr: %s' % repr(stderr.strip()) if stderr else ''))
  status = process.poll()
  return Obj(stdout=stdout, stderr=stderr, status=status, success=(status == 0))


def ExecFactoryPar(*args):
  """Use os.execl to execute a command (given by args) provided by factory PAR.

  This function will execute "/path/to/factory.par arg0 arg1 ..." using
  os.exec. Current process will be replaced, therefore this function won't
  return if there is no exception.

  Example::

    >>> ExecFactoryPar(['gooftool', 'wipe_in_place', ...])

    will execute /path/to/factory.par gooftool wipe_in_place ...
    current process will be replaced by new process.
  """

  factory_par = paths.GetFactoryPythonArchivePath()
  # There are two factory_par in the argument because os.execl's function
  # signature is: os.execl(exec_path, arg0, arg1, ...)
  logging.debug('exec: %s %s', factory_par, args)
  os.execl(factory_par, factory_par, *args)


class Util:
  """A collection of util functions that Gooftool needs."""

  def __init__(self):
    self.shell = Shell
    # TODO(cyueh): Remove self.sys_interface after we moving cbi_utils into
    # gooftool/.
    self.sys_interface = sys_interface_module.SystemInterface()

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

  def GetKeyHashFromFutil(self, fw_file):
    """Gets the pubkey hash from `futility show` output.

    Args:
      fw_file: The path to the firmware blob

    Returns:
      The public key hash of the specified firmware file
    """

    futil_out = self.shell(['futility', 'show', '--type', 'rwsig', fw_file])
    if not futil_out.success:
      raise Error('Failed to get EC pubkey hash: %s' % futil_out.stderr)
    # A typical example of the output from `futility show` is:
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
    key_hash = re.search(r'\n\s*ID:\s*([a-z0-9]*)', futil_out.stdout).group(1)
    return key_hash

  def GetPrimaryDevicePath(self, partition=None):
    """Gets the path for the primary device, which is the only non-removable
    device in the system.

    Args:
      partition: The index of the partition on primary device.

    Returns:
      The path to the primary device. If partition is specified, the path
      points to that partition of the primary device. e.g. /dev/sda1
    """

    dev_path = self.shell('rootdev -s -d').stdout.strip()
    if not self._IsDeviceFixed(os.path.basename(dev_path)):
      raise Error('%s is not a fixed device' % dev_path)
    if partition is None:
      return dev_path
    fmt_str = '%sp%d' if dev_path[-1].isdigit() else '%s%d'
    return fmt_str % (dev_path, partition)

  def GetPartitionDevice(self, path):
    """Returns a device path string from partition path.

    /dev/sda1 => /dev/sda.
    /dev/mmcblk0p2 => /dev/mmcblk0.
    """
    return ''.join(re.findall(
        r'(.*[^0-9][0-9]+)p[0-9]+|(.*[^0-9])[0-9]+', path)[0])

  def GetDevicePartition(self, device, partition):
    """Returns a partition path from device path string.

    /dev/sda, 1 => /dev/sda1.
    /dev/mmcblk0p, 2 => /dev/mmcblk0p2.
    """
    return ('%sp%s' if device[-1].isdigit() else '%s%s') % (device, partition)


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
      The result of execution.

    Raises:
      Error if execution failed.
    """

    assert not post_opts or isinstance(post_opts, list)
    assert not pre_opts or isinstance(pre_opts, list)

    script = self.FindScript(script_name)
    cmd = '%s %s %s' % (' '.join(pre_opts) if pre_opts else '',
                        script,
                        ' '.join(post_opts) if post_opts else '')
    result = self.shell(cmd.strip())
    if not result.success:
      raise Error('%r failed, stderr: %r' % (cmd, result.stderr))

    return result

  def GetReleaseRootPartitionPath(self):
    """Gets the path for release root partition."""

    return self.GetPrimaryDevicePath(5)

  def GetReleaseKernelPartitionPath(self):
    """Gets the path for release kernel partition."""

    return self.GetPrimaryDevicePath(4)

  def GetReleaseKernelPathFromRootPartition(self, rootfs_path):
    """Gets the path for release kernel from given rootfs path.

    This function assumes kernel partition is always located before rootfs.
    """
    device = self.GetPartitionDevice(rootfs_path)
    kernel_index = int(rootfs_path[-1]) - 1
    return self.GetDevicePartition(device, kernel_index)

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
    for k, v in attrs.items():
      if curr_attrs.get(k) == v:
        continue
      if not self.shell('cgpt add %s -i %s -A %s' % (device, k, v)).success:
        raise Error('Failed to set device config: %s#%s=%s' % (device, k, v))

  def InvokeChromeOSPostInstall(self, root_dev=None):
    """Invokes the ChromeOS post-install script (/postinst)."""
    if root_dev is None:
      root_dev = self.GetReleaseRootPartitionPath()

    logging.info('Running ChromeOS post-install on %s...', root_dev)

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

  def IsLegacyChromeOSFirmware(self):
    """Returns if the system is running legacy ChromeOS firmware."""
    r = self.shell('crossystem mainfw_type')
    return not r.success or r.stdout.strip() == 'nonchrome'

  def EnableReleasePartition(self, root_dev):
    """Enables a release image partition on disk."""
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
      if self.IsLegacyChromeOSFirmware():
        self.InvokeChromeOSPostInstall(root_dev)
      self.shell('crossystem disable_dev_request=1')
      self.DisableKernel(device, factory_no)
      self.EnableKernel(device, release_no)
      # Enforce a sync and wait for underlying hardware to flush.
      logging.info('Syncing disks...')
      self.shell('sync; sleep 3')
      logging.info('Enable release partition: Complete.')
    except Exception:
      logging.error('FAIL: Failed to enable release partition.')
      self.shell('crossystem disable_dev_request=0')
      self.SetCgptAttributes(curr_attrs, device)
