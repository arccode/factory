#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility to manipulate Chrome OS disk & firmware images for manufacturing.

Run "image_tool help" for more info and a list of subcommands.

To add a subcommand, just add a new SubCommand subclass to this file.
"""


from __future__ import print_function

import argparse
import contextlib
import glob
import inspect
import logging
import os
import pipes
import re
import shutil
import subprocess
import sys
import tempfile

# This file needs to run on various environments, for example a fresh Ubuntu
# that does not have Chromium OS source tree nor chroot. So we do want to
# prevent introducing more cros.factory dependency except very few special
# modules (pygpt, fmap, netboot_firmware_settings).
# Please don't add more cros.factory modules.
import factory_common  # pylint: disable=unused-import
from cros.factory.utils import pygpt
from cros.factory.tools import netboot_firmware_settings


# Partition index for Chrome OS stateful partition.
PART_CROS_STATEFUL = 1
# Partition index for Chrome OS rootfs A.
PART_CROS_ROOTFS_A = 3
# Special options to mount Chrome OS rootfs partitions. (-t ext2, -o ro).
FS_TYPE_CROS_ROOTFS = 'ext2'
# Relative path of firmware updater on Chrome OS disk images.
PATH_CROS_FIRMWARE_UPDATER = '/usr/sbin/chromeos-firmwareupdate'
# The name of folder must match /etc/init/cros-payloads.conf.
DIR_CROS_PAYLOADS = 'cros_payloads'
# Mode for new created folder, 0755 = u+rwx, go+rx
MODE_NEW_DIR = 0755
# Regular expression for parsing LSB value, which should be sh compatible.
RE_LSB = re.compile(r'^ *(.*)="?(.*[^"])"?$', re.MULTILINE)
# Key for Chrome OS board name in /etc/lsb-release.
KEY_LSB_CROS_BOARD = 'CHROMEOS_RELEASE_BOARD'
# Key for Chrome OS build version in /etc/lsb-release.
KEY_LSB_CROS_VERSION = 'CHROMEOS_RELEASE_VERSION'
# Regular expression for reading file system information from dumpe2fs.
RE_BLOCK_COUNT = re.compile(r'^Block count: *(.*)$', re.MULTILINE)
RE_BLOCK_SIZE = re.compile(r'^Block size: *(.*)$', re.MULTILINE)
# Regular expression for GPT entry in `write_gpt.sh`.
RE_GPT = re.compile(r'^GPT=""$', re.MULTILINE)
RE_WRITE_GPT_CHECK_BLOCKDEV = re.compile(
    r'if \[ -b "\${target}" ]; then', re.MULTILINE)
# Special argument to indicate None.
STR_NONE = 'none'
# Simple constant(s)
MEGABYTE = 1048576
# The storage industry treat "mega" and "giga" differently.
GIGABYTE_STORAGE = 1000000000


class ArgTypes(object):
  """Helper class to collect all argument type checkers."""

  @staticmethod
  def ExistsPath(path):
    """An argument with existing path."""
    if not os.path.exists(path):
      raise argparse.ArgumentTypeError('Does not exist: %s' % path)
    return path

  @staticmethod
  def GlobPath(pattern):
    """An argument as glob pattern, and solved as single path.

    This is a useful type to specify default values with wildcard.
    If the pattern is prefixed with '-', the value is returned as None without
    raising exceptions.
    """
    allow_none = False
    if pattern.startswith('-'):
      # Special trick to allow defaults.
      pattern = pattern[1:]
      allow_none = True
    found = glob.glob(pattern)
    if len(found) < 1:
      if allow_none:
        return None
      raise argparse.ArgumentTypeError('Does not exist: %s' % pattern)
    if len(found) > 1:
      raise argparse.ArgumentTypeError(
          'Too many files found for <%s>: %s' % (pattern, found))
    return found[0]

  @staticmethod
  def GlobPathOrNone(pattern):
    """An argument as glob pattern or STR_NONE."""
    if pattern == STR_NONE:
      return pattern
    return ArgTypes.GlobPath(pattern)


class SysUtils(object):
  """Collection of system utilities."""

  @staticmethod
  def Shell(commands, sudo=False, output=False, check=True, silent=False,
            **kargs):
    """Helper to execute 'sudo' command in a shell.

    A simplified implementation. To reduce dependency, we don't want to use
    process_utils.Spawn.

    Args:
      sudo: Execute the command with sudo if needed.
      output: Returns the output from command (check_call).
    """
    if not isinstance(commands, basestring):
      commands = ' '.join(pipes.quote(arg) for arg in commands)
    kargs['shell'] = True

    caller = subprocess.check_output if output else subprocess.check_call
    if sudo and os.geteuid() != 0:
      commands = 'sudo ' + commands
    if silent:
      commands += ' >/dev/null 2>&1'
    if not check:
      if output:
        commands += ' || true'
      else:
        caller = subprocess.call

    return caller(commands, **kargs)

  @staticmethod
  def Sudo(commands, **kargs):
    """Shortcut to Shell(commands, sudo=True)."""
    kargs['sudo'] = True
    return Shell(commands, **kargs)

  @staticmethod
  def SudoOutput(commands, **kargs):
    """Shortcut to Sudo(commands, output=True)."""
    kargs['output'] = True
    return Sudo(commands, **kargs)

  @staticmethod
  def FindCommand(command):
    """Returns the right path to invoke given command."""
    provided = os.path.join(
        os.path.dirname(os.path.abspath(sys.argv[0])), command)
    if not os.path.exists(provided):
      provided = Shell(['which', command], output=True, check=False).strip()
    if not provided:
      raise RuntimeError('Cannot find program: %s' % command)
    return provided

  @staticmethod
  @contextlib.contextmanager
  def TempDirectory(prefix='imgtool_', delete=True):
    """Context manager to allocate and remove temporary folder.

    Args:
      prefix: a string as prefix of the created folder name.
    """
    tmp_folder = None
    try:
      tmp_folder = tempfile.mkdtemp(prefix=prefix)
      yield tmp_folder
    finally:
      if tmp_folder and delete:
        Sudo(['rm', '-rf', tmp_folder], check=False)


# Short cut to SysUtils.
Shell = SysUtils.Shell
Sudo = SysUtils.Sudo
SudoOutput = SysUtils.SudoOutput


class Partition(object):
  """To easily access partition on a disk image."""

  def __init__(self, image, number):
    """Constructor of partition on a disk image.

    Args:
      image: a path to disk image file.
      number: integer as 1-based index in partition table.
    """
    self._image = image
    self._number = number

    with open(image, 'rb') as f:
      self._gpt = pygpt.GPT.LoadFromFile(f)

    # Ensure given index is valid.
    parts = self._gpt.GetValidPartitions()
    total = len(parts)
    if not 1 <= number <= total:
      raise RuntimeError(
          'Partition number %s out of range [%s,%s] for image %s.' %
          (number, 1, total, image))
    self._part = parts[number - 1]

  def __str__(self):
    return '%s#%s' % (self._image, self._number)

  @property
  def image(self):
    return self._image

  @property
  def number(self):
    return self._number

  @property
  def offset(self):
    return self._part.FirstLBA * self._gpt.BLOCK_SIZE

  @property
  def size(self):
    return (self._part.LastLBA - self._part.FirstLBA + 1) * self._gpt.BLOCK_SIZE

  @staticmethod
  @contextlib.contextmanager
  def _Map(image, offset, size):
    """Context manager to map (using losetup) partition(s) from disk image.

    Args:
      image: a path to disk image to map.
      offset: an integer as offset to partition, or None to map whole disk.
      size: an integer as partition size, or None for whole disk.
    """
    loop_dev = None
    args = ['losetup', '--show', '--find']
    if offset is None:
      # Note "losetup -P" needs Ubuntu 15+.
      args += ['-P']
    else:
      args += ['-o', str(offset), '--sizelimit', str(size)]
    args += [image]
    try:
      loop_dev = SudoOutput(args).strip()
      yield loop_dev
    finally:
      if loop_dev:
        Sudo(['umount', '-R', loop_dev], check=False, silent=True)
        Sudo(['losetup', '-d', loop_dev], check=False, silent=True)

  def Map(self):
    """Maps given partition to loop block device."""
    logging.debug('Map %s: %s(+%s)', self, self.offset, self.size)
    return self._Map(self.image, self.offset, self.size)

  @staticmethod
  def MapAllPartitions(image):
    """Maps an image with all partitions to loop block devices.

    Map the image to /dev/loopN, and all partitions will be created as
    /dev/loopNpM, where M stands for partition number.
    This is not supported by older systems.

    Args:
      image: a path to disk image to map.

    Returns:
      The mapped major loop device (/dev/loopN).
    """
    return Partition._Map(image, None, None)

  @contextlib.contextmanager
  def Mount(self, mount_point=None, rw=False, fs_type=None, options=None,
            auto_umount=True, silent=False):
    """Context manager to mount partition from given disk image.

    Args:
      mount_point: directory to mount, or None to use temporary directory.
      rw: True to mount as read-write, otherwise read-only (-o ro).
      fs_type: string as file system type (-t).
      options: string as extra mount options (-o).
      auto_umount: True to un-mount when leaving context.
      silent: True to hide all warning and error messages.
    """
    options = options or []
    if isinstance(options, basestring):
      options = [options]
    options = ['rw' if rw else 'ro'] + options

    options += ['loop', 'offset=%s' % self.offset, 'sizelimit=%s' % self.size]
    args = ['mount', '-o', ','.join(options)]
    if fs_type:
      args += ['-t', fs_type]

    temp_dir = None
    try:
      if not mount_point:
        temp_dir = tempfile.mkdtemp(prefix='imgtool_')
        mount_point = temp_dir

      args += [self.image, mount_point]

      logging.debug('Partition.Mount: %s', ' '.join(args))
      Sudo(args, silent=silent)
      yield mount_point

    finally:
      if auto_umount:
        if mount_point:
          Sudo(['umount', '-R', mount_point], check=False)
        if temp_dir:
          os.rmdir(temp_dir)

  def MountAsCrOSRootfs(self, *args, **kargs):
    """Mounts as Chrome OS root file system with rootfs verification turned on.

    The Chrome OS disk image with rootfs verification turned on will enable the
    RO bit in ext2 attributes and can't be mounted without specifying mount
    arguments "-t ext2 -o ro".
    """
    assert kargs.get('rw', False) is False, (
        'Cannot change Chrome OS rootfs %s.' % self)
    assert kargs.get('fs_type', FS_TYPE_CROS_ROOTFS) == FS_TYPE_CROS_ROOTFS, (
        'Chrome OS rootfs %s must be mounted as %s.' % (
            self, FS_TYPE_CROS_ROOTFS))
    kargs['rw'] = False
    kargs['fs_type'] = FS_TYPE_CROS_ROOTFS
    return self.Mount(*args, **kargs)

  def CopyFile(self, rel_path, dest, **mount_options):
    """Copies a file inside partition to given destination.

    Args:
      rel_path: relative path to source on disk partition.
      dest: path of destination (file or directory).
      mount_options: anything that must be passed to Partition.Mount.
    """
    with self.Mount(**mount_options) as rootfs:
      # If rel_path is absolute then os.join will discard rootfs.
      if os.path.isabs(rel_path):
        rel_path = '.' + rel_path
      src_path = os.path.join(rootfs, rel_path)
      dest_path = (os.path.join(dest, os.path.basename(rel_path)) if
                   os.path.isdir(dest) else dest)
      logging.debug('Copying %s => %s ...', src_path, dest_path)
      shutil.copy(src_path, dest_path)
      return dest_path

  @staticmethod
  def _ParseExtFileSystemSize(block_dev):
    """Helper to parse ext* file system size using dumpe2fs.

    Args:
      raw_part: a path to block device.
    """
    raw_info = SudoOutput(['dumpe2fs', '-h', block_dev])
    block_count = int(RE_BLOCK_COUNT.findall(raw_info)[0])
    block_size = int(RE_BLOCK_SIZE.findall(raw_info)[0])
    return block_count * block_size

  def GetFileSystemSize(self):
    """Returns the (ext*) file system size.

    It is possible the real space occupied by file system is smaller than
    partition size, especially in Chrome OS, the extra space is reserved for
    verity data (rootfs verification) or to help quick wiping in factory
    process.
    """
    with self.Map() as raw_part:
      return self._ParseExtFileSystemSize(raw_part)

  def ResizeFileSystem(self, new_size=None):
    """Resizes the file system in given partition.

    resize2fs may not accept size in number > INT32, so we have to specify the
    size in larger units, for example MB; and that implies the result may be
    different from new_size.

    Args:
      new_size: The expected new size. None to use whole partition.

    Returns:
      New size in bytes.
    """
    with self.Map() as raw_part:
      # File system must be clean before we can perform resize2fs.
      # e2fsck may return 1 "errors corrected" or 2 "corrected and need reboot".
      old_size = self._ParseExtFileSystemSize(raw_part)
      result = Sudo(['e2fsck', '-y', '-f', raw_part], check=False)
      if result > 2:
        raise RuntimeError('Failed in ensuring file system integrity (e2fsck).')
      args = ['resize2fs', '-f', raw_part]
      if new_size:
        args.append('%sM' % (new_size / MEGABYTE))
      Sudo(args)
      real_size = self._ParseExtFileSystemSize(raw_part)
      logging.debug(
          '%s (%s) file system resized from %s (%sM) to %s (%sM), req = %s M',
          self, self.size, old_size, old_size / MEGABYTE,
          real_size, real_size / MEGABYTE,
          new_size / MEGABYTE if new_size else '(ALL)')
    return real_size


class LSBFile(object):
  """Access /etc/lsb-release file (or files in same format).

  The /etc/lsb-release can be loaded directly by shell ( . /etc/lsb-release ).
  There is no really good and easy way to parse that without sh, but fortunately
  for the fields we care, it's usually A=B or A="B C".

  Also, in Chrome OS, the /etc/lsb-release was implemented without using quotes
  (i,e., A=B C, no matter if the value contains space or not).
  """
  def __init__(self, path=None, is_cros=True):
    self._raw_data = ''
    self._dict = {}
    self._is_cros = is_cros
    if not path:
      return

    with open(path) as f:
      self._raw_data = f.read().strip()  # Remove trailing \n or \r
      self._dict = dict(RE_LSB.findall(self._raw_data))

  def AsDict(self):
    return self._dict

  def FormatKeyValue(self, key, value):
    return ('%s=%s' if self._is_cros or ' ' not in value else '%s="%s"') % (
        key, value)

  def GetValue(self, key, default=None):
    return self._dict.get(key, default)

  def AppendValue(self, key, value):
    self._dict[key] = value
    self._raw_data += '\n' + self.FormatKeyValue(key, value)

  def SetValue(self, key, value):
    if key in self._dict:
      self._dict[key] = value
      self._raw_data = re.sub(
          r'^' + re.escape(key) + r'=.*', self.FormatKeyValue(key, value),
          self._raw_data, flags=re.MULTILINE)
    else:
      self.AppendValue(key, value)

  def DeleteValue(self, key):
    if key not in self._dict:
      return
    self._dict.pop(key)
    self._raw_data = re.sub(
        r'^' + re.escape(key) + r'=.*', '', self._raw_data, flags=re.MULTILINE)

  def Install(self, destination):
    """Installs the contents to the given location as lsb-release style file.

    The file will be owned by root:root, with file mode 0644.
    """
    with tempfile.NamedTemporaryFile(prefix='lsb_') as f:
      f.write(self._raw_data + '\n')
      f.flush()
      os.chmod(f.name, 0644)
      Sudo(['cp', '-pf', f.name, destination])
      Sudo(['chown', 'root:root', destination])

  def GetChromeOSBoard(self, remove_signer=True):
    """Returns the Chrome OS board name.

    Gets the value using KEY_LSB_CROS_BOARD. For test or DEV signed images, this
    is exactly the board name we passed to build commands. For PreMP/MP signed
    images, this may have suffix '-signed-KEY', where KEY is the key name like
    'mpv2'.

    Args:
      remove_signer: True to remove '-signed-XX' information.
    """
    board = self.GetValue(KEY_LSB_CROS_BOARD, '')
    if remove_signer:
      # For signed images, the board may come in $BOARD-signed-$KEY.
      signed_index = board.find('-signed-')
      if signed_index > -1:
        board = board[:signed_index]
    return board

  def GetChromeOSVersion(self, remove_timestamp=True):
    """Returns the Chrome OS build version.

    Gets the value using KEY_LSB_CROS_VERSION. For self-built images, this may
    include a time stamp.

    Args:
      remove_timestamp: Remove the timestamp like version info if available.
    """
    version = self.GetValue('CHROMEOS_RELEASE_VERSION', '')
    if remove_timestamp:
      version = version.split()[0]
    return version


class ChromeOSFactoryBundle(object):
  """Utilities to work with factory bundle."""

  def __init__(self, temp_dir, board, release_image, test_image, toolkit,
               factory_shim=None, firmware=None, hwid=None, complete=None):
    self._temp_dir = temp_dir
    # Member data will be looked up by getattr so we don't prefix with '_'.
    self.board = board
    self.release_image = release_image
    self.test_image = test_image
    self.toolkit = toolkit
    self.factory_shim = factory_shim
    self.firmware = firmware
    self.hwid = hwid
    self.complete = complete
    self.components = [
        'release_image', 'test_image', 'toolkit', 'firmware', 'hwid',
        'complete']

  @staticmethod
  def DefineBundleArguments(parser):
    """Define common argparse arguments to work with factory bundle.

    Args:
      parser: An argparse subparser to add argument definitions.
    """
    parser.add_argument(
        '--release_image', default='release_image/*.bin',
        type=ArgTypes.GlobPath,
        help=('path to a Chromium OS (release or recovery) image. '
              'default: %(default)s'))
    parser.add_argument(
        '--test_image', default='test_image/*.bin',
        type=ArgTypes.GlobPath,
        help='path to a Chromium OS test image. default: %(default)s')
    parser.add_argument(
        '--toolkit', default='toolkit/*.run',
        type=ArgTypes.GlobPath,
        help='path to a Chromium OS factory toolkit. default: %(default)s')
    parser.add_argument(
        '--hwid', default='-hwid/*.sh',
        type=ArgTypes.GlobPath,
        help='path to a HWID bundle if available. default: %(default)s')

  def CreatePayloads(self, target_dir):
    """Builds cros_payload contents into target_dir.

    This is needed to store payloads or install to another system.

    Args:
      target_dir: a path to a folder for generating cros_payload contents.

    Returns:
      The JSON path in target_dir for cros_payload to use.
    """
    logging.debug('Generating cros_payload contents...')
    json_path = os.path.join(target_dir, '%s.json' % self.board)
    with open(json_path, 'wt') as f:
      f.write('{}')

    cros_payload = SysUtils.FindCommand('cros_payload')
    for component in self.components:
      resource = getattr(self, component)
      if resource:
        logging.debug('Add %s payloads from %s...', component, resource)
        Shell([cros_payload, 'add', json_path, component, resource])
      else:
        print('Leaving %s component payload as empty.' % component)
    return json_path

  def GetPMBR(self, image_path):
    """Creates a file containing PMBR contents from given image.

    Chrome OS firmware does not really need PMBR, but many legacy operating
    systems, UEFI BIOS, or particular SOC may need it, so we do want to create
    PMBR using a bootable image (for example release or factory_shim image).

    Args:
      image_path: a path to a Chromium OS disk image to read back PMBR.

    Returns:
      A file (in self._temp_dir) containing PMBR.
    """
    pmbr_path = os.path.join(self._temp_dir, '_pmbr')
    with open(image_path) as src:
      with open(pmbr_path, 'wb') as dest:
        dest.write(src.read(512))
    return pmbr_path

  def CreatePartitionScript(self, image_path, pmbr_path):
    """Creates a partition script from write_gpt.sh inside image_path.

    To initialize a new disk for Chrome OS, we need to execute the write_gpt.sh
    included in rootfs of disk images. And to run that outside Chrome OS,
    we have to slightly hack the script.

    Args:
      pmbr_path: a path to a file with PMBR code (by self.CreatePMBR).
      image_path: a path to a Chromium OS disk image to find write_gpt.sh.

    Returns:
      A generated script (in self._temp_dir) for execution.
    """
    part = Partition(image_path, PART_CROS_ROOTFS_A)
    with part.MountAsCrOSRootfs() as rootfs:
      script_path = os.path.join(self._temp_dir, '_write_gpt.sh')
      write_gpt_path = os.path.join(rootfs, 'usr', 'sbin', 'write_gpt.sh')
      chromeos_common_path = os.path.join(
          rootfs, 'usr', 'share', 'misc', 'chromeos-common.sh')
      if not os.path.exists(write_gpt_path):
        raise RuntimeError('%s does not have "write_gpt.sh".' % part)
      if not os.path.exists(chromeos_common_path):
        raise RuntimeError('%s does not have "chromeos-common.sh".' % part)

      # We need to patch up write_gpt.sh a bit to cope with the fact we're
      # running in a non-chroot/device env and that we're not running as root
      # 'write_gpt_path.sh' may be only readable by user 1001 (chronos).
      contents = SudoOutput(['cat', chromeos_common_path, write_gpt_path])
      # Override default GPT command path.
      if not RE_GPT.search(contents):
        raise RuntimeError('Missing GPT="" in %s:"write_gpt.sh".' % part)

      cgpt_path = SysUtils.FindCommand('cgpt')
      contents = RE_GPT.sub('GPT="%s"' % cgpt_path, contents)
      contents += '\n'.join([
          '',
          'write_base_table $1 %s' % pmbr_path,
          '${GPT} add -i 2 -S 1 -P 1 $1'])

      # stateful partitions are enlarged only if the target is a block device
      # (not file), in order to reduce USB image size. As a result, we have to
      # either run partition script with disk mapped, or hack the script like
      # this:
      contents = RE_WRITE_GPT_CHECK_BLOCKDEV.sub('if true; then', contents)

      with open(script_path, 'wt') as f:
        f.write(contents)
      return script_path

  def InitDiskImage(self, output, sectors):
    """Initializes (resize and partition) a new disk image.

    Args:
      output: a path to disk image to initialize.
      sectors: number of sectors in disk image.
    """
    print('Initialize disk image with %s sectors [%s G]' %
          (sectors, sectors * 512 / GIGABYTE_STORAGE))
    pmbr_path = self.GetPMBR(self.release_image)
    partition_script = self.CreatePartitionScript(self.release_image, pmbr_path)
    # TODO(hungte) Support block device as output, and support 'preserve'.
    Shell(['truncate', '-s', '0', output])
    Shell(['truncate', '-s', str(sectors * 512), output])
    logging.debug('Execute generated partitioning script on %s', output)
    Sudo(['bash', '-e', partition_script, output])

  def CreateDiskImage(self, output, sectors):
    """Creates the installed disk image.

    This creates a complete image that can be pre-flashed to and boot from
    internal storage.

    Args:
      output: a path to disk image to initialize.
      sectors: number of sectors in disk image.
    """
    self.InitDiskImage(output, sectors)
    payloads_dir = os.path.join(self._temp_dir, DIR_CROS_PAYLOADS)
    os.mkdir(payloads_dir)
    json_path = self.CreatePayloads(payloads_dir)

    cros_payload = SysUtils.FindCommand('cros_payload')
    with Partition.MapAllPartitions(output) as output_dev:
      Sudo([cros_payload, 'install', json_path, output_dev,
            'test_image', 'release_image'])

    # output_dev (via /dev/loopX) needs root permission so we have to leave
    # previous context and resize using the real disk image file.
    part = Partition(output, PART_CROS_STATEFUL)
    part.ResizeFileSystem(part.GetFileSystemSize() + 1024 * MEGABYTE)
    with Partition.MapAllPartitions(output) as output_dev:
      targets = ['toolkit', 'release_image.crx_cache']
      if self.hwid:
        targets += ['hwid']
      Sudo([cros_payload, 'install', json_path, output_dev] + targets)

    logging.debug('Add /etc/lsb-factory if not exists.')
    with part.Mount(rw=True) as stateful:
      Sudo(['touch', os.path.join(stateful, 'dev_image', 'etc', 'lsb-factory')],
           check=False)

  def CreateRMAImage(self, output):
    """Creates the RMA bootable installation disk image.

    This creates an RMA image that can boot and install all factory software
    resouces to device.

    Args:
      output: a path to disk image to initialize.
    """
    # It is possible to enlarge the disk by calculating sizes of all input
    # files, create cros_payloads folder in the disk image file, to minimize
    # execution time. However, that implies we have to shrink disk image later
    # (due to gz), and run build_payloads using root, which are all not easy.
    # As a result, here we want to create payloads in temporary folder then copy
    # into disk image.
    payloads_dir = os.path.join(self._temp_dir, DIR_CROS_PAYLOADS)
    os.mkdir(payloads_dir, MODE_NEW_DIR)
    self.CreatePayloads(payloads_dir)

    payloads_size = int(
        SudoOutput(['du', '-sk', payloads_dir]).split()[0]) * 1024
    print('cros_payloads size: %s M' % (payloads_size / MEGABYTE))
    shutil.copyfile(self.factory_shim, output)

    old_size = os.path.getsize(output)
    new_size = old_size + payloads_size
    print('Changing size: %s M => %s M' %
          (old_size / MEGABYTE, new_size / MEGABYTE))
    Shell(['truncate', '-s', str(new_size), output])
    with open(output, 'rb+') as f:
      gpt = pygpt.GPT.LoadFromFile(f)
      gpt.Resize(new_size)
      gpt.ExpandPartition(PART_CROS_STATEFUL - 1)  # pygpt.GPT is 0-based.
      gpt.WriteToFile(f)
    part = Partition(output, PART_CROS_STATEFUL)
    part.ResizeFileSystem()

    with part.Mount(rw=True) as stateful:
      print('Moving payload files to disk image...')
      new_name = os.path.join(stateful, DIR_CROS_PAYLOADS)
      if os.path.exists(new_name):
        raise RuntimeError('Factory shim already contains %s - already RMA?' %
                           DIR_CROS_PAYLOADS)
      Sudo(['chown', '-R', 'root:root', payloads_dir])
      Sudo(['mv', '-f', payloads_dir, stateful])

      # Update lsb-factory file.
      lsb_path = os.path.join(stateful, 'dev_image', 'etc', 'lsb-factory')
      lsb_file = LSBFile(lsb_path if os.path.exists(lsb_path) else None)
      lsb_file.AppendValue('FACTORY_INSTALL_FROM_USB', '1')
      lsb_file.AppendValue('USE_CROS_PAYLOAD', '1')
      lsb_file.Install(lsb_path)
      Sudo(['df', '-h', stateful])


# TODO(hungte) Generalize this (copied from py/tools/factory.py) for all
# commands to utilize easily.
class SubCommand(object):
  """A subcommand.

  Properties:
    name: The name of the command (set by the subclass).
    parser: The ArgumentParser object.
    subparser: The subparser object created with parser.add_subparsers.
    subparsers: A collection of all subparsers.
    args: The parsed arguments.
  """
  name = None  # Overridden by subclass
  aliases = [] # Overridden by subclass

  parser = None
  args = None
  subparser = None
  subparsers = None

  def __init__(self, parser, subparsers):
    assert self.name
    self.parser = parser
    self.subparsers = subparsers
    subparser = subparsers.add_parser(
        self.name, help=self.__doc__.splitlines()[0],
        description=self.__doc__)
    subparser.set_defaults(subcommand=self)
    self.subparser = subparser

  def Init(self):
    """Initializes the subparser.

    May be implemented the subclass, which may use "self.subparser" to
    refer to the subparser object.
    """
    pass

  def Run(self):
    """Runs the command.

    Must be implemented by the subclass.
    """
    raise NotImplementedError


class HelpCommand(SubCommand):
  """Get help on COMMAND"""
  name = 'help'

  def Init(self):
    self.subparser.add_argument('command', metavar='COMMAND', nargs='?')

  def Run(self):
    if self.args.command:
      choice = self.subparsers.choices.get(self.args.command)
      if not choice:
        sys.exit('Unknown subcommand %r' % self.args.command)
      choice.print_help()
    else:
      self.parser.print_help()


class MountPartitionCommand(SubCommand):
  """Mounts a partition from Chromium OS disk image.

  Chrome OS rootfs with rootfs verification turned on will be mounted as
  read-only.  All other file systems will be mounted as read-write."""
  name = 'mount'
  aliases = ['mount_partition']

  def Init(self):
    self.subparser.add_argument(
        '-rw', '--rw', action='store_true',
        help='mount partition read/write')
    self.subparser.add_argument(
        '-ro', '--ro', dest='rw', action='store_false',
        help='mount partition read-only')
    self.subparser.add_argument(
        'image', type=ArgTypes.ExistsPath,
        help='path to the Chromium OS image')
    self.subparser.add_argument(
        'partition_number', type=int,
        help='which partition (1-based) to mount')
    self.subparser.add_argument(
        'mount_point', type=ArgTypes.ExistsPath,
        help='the path to mount partition')

  def Run(self):
    part = Partition(self.args.image, self.args.partition_number)
    mode = ''
    rw = True
    silent = True
    try_ro = True
    if self.args.rw is not None:
      rw = self.args.rw
      silent = False
      try_ro = False

    try:
      with part.Mount(self.args.mount_point, rw=rw, auto_umount=False,
                      silent=silent):
        mode = 'RW' if rw else 'RO'
    except subprocess.CalledProcessError:
      if not try_ro:
        raise
      logging.debug('Failed mounting %s, try again as ro/ext2...', part)
      with part.MountAsCrOSRootfs(self.args.mount_point, auto_umount=False):
        mode = 'RO'

    print('OK: Mounted %s as %s on %s.' % (part, mode, self.args.mount_point))


class GetFirmwareCommand(SubCommand):
  """Extracts firmware updater from a Chrome OS disk image."""
  # Only Chrome OS disk images should have firmware updater, not Chromium OS.
  name = 'get_firmware'
  aliases = ['extract_firmware_updater']

  def Init(self):
    self.subparser.add_argument(
        '-i', '--image', type=ArgTypes.ExistsPath, required=True,
        help='path to the Chrome OS (release) image')
    self.subparser.add_argument(
        '-o', '--output_dir', default='.',
        help='directory to save output file(s)')

  def Run(self):
    part = Partition(self.args.image, PART_CROS_ROOTFS_A)
    output = part.CopyFile(PATH_CROS_FIRMWARE_UPDATER, self.args.output_dir,
                           fs_type=FS_TYPE_CROS_ROOTFS)
    print('OK: Extracted %s:%s to: %s' % (
        part, PATH_CROS_FIRMWARE_UPDATER, output))


class NetbootFirmwareSettingsCommand(SubCommand):
  """Access Chrome OS netboot firmware (image.net.bin) settings."""
  name = 'netboot'
  aliases = ['netboot_firmware_settings']

  def Init(self):
    netboot_firmware_settings.DefineCommandLineArgs(self.subparser)

  def Run(self):
    netboot_firmware_settings.NetbootFirmwareSettings(self.args)


class ResizeFileSystemCommand(SubCommand):
  """Changes file system size from a partition on a Chromium OS disk image."""
  name = 'resize'
  aliases = ['resize_image_fs']

  def Init(self):
    self.subparser.add_argument(
        '-i', '--image', type=ArgTypes.ExistsPath, required=True,
        help='path to the Chromium OS disk image')
    self.subparser.add_argument(
        '-p', '--partition_number', type=int, default=1,
        help='file system on which partition to resize')
    self.subparser.add_argument(
        '-s', '--size_mb', type=int, default=1024,
        help='file system size to change (set or add, see --append) in MB')
    self.subparser.add_argument(
        '-a', '--append', dest='append', action='store_true', default=True,
        help='append (increase) file system by +size_mb')
    self.subparser.add_argument(
        '--no-append', dest='append', action='store_false',
        help='set file system to a new size of size_mb')

  def Run(self):
    part = Partition(self.args.image, self.args.partition_number)
    curr_size = part.GetFileSystemSize()

    if self.args.append:
      new_size = curr_size + self.args.size_mb * MEGABYTE
    else:
      new_size = self.args.size_mb * MEGABYTE

    if new_size > part.size:
      raise RuntimeError(
          'Requested size (%s MB) larger than %s partition (%s MB).' % (
              new_size / MEGABYTE, part, part.size / MEGABYTE))

    new_size = part.ResizeFileSystem(new_size)
    print('OK: %s file system has been resized from %s to %s MB.' %
          (part, curr_size / MEGABYTE, new_size / MEGABYTE))


class CreatePreflashImageCommand(SubCommand):
  """Create a disk image for factory to pre-flash into internal storage.

  The output contains factory toolkit, release and test images.
  The manufacturing line can directly dump this image to device boot media
  (eMMC, SSD, NVMe, ... etc) using 'dd' command or copy machines.
  """
  name = 'preflash'

  def Init(self):
    ChromeOSFactoryBundle.DefineBundleArguments(self.subparser)
    self.subparser.add_argument(
        '--sectors', type=int, default=31277232,
        help='size of image in 512-byte sectors. default: %(default)s')
    self.subparser.add_argument(
        '-o', '--output', required=True,
        help='path to the output disk image file.')

  def Run(self):
    with SysUtils.TempDirectory(prefix='diskimg_') as temp_dir:
      bundle = ChromeOSFactoryBundle(
          temp_dir=temp_dir,
          board='default',
          release_image=self.args.release_image,
          test_image=self.args.test_image,
          toolkit=self.args.toolkit,
          factory_shim=None,
          firmware=None,
          hwid=self.args.hwid,
          complete=None)
      bundle.CreateDiskImage(self.args.output, self.args.sectors)
    print('OK: Generated pre-flash disk image at %s [%s G]' % (
        self.args.output, self.args.sectors * 512 / GIGABYTE_STORAGE))


class CreateRMAImageCommmand(SubCommand):
  """Create an RMA image for factory to boot from USB and repair device.

  The output is a special factory install shim (factory_install) with all
  resources (release, test images and toolkit). The manufacturing line or RMA
  centers can boot it from USB and install all factory software bits into
  a device.
  """
  name = 'rma'

  def Init(self):
    ChromeOSFactoryBundle.DefineBundleArguments(self.subparser)
    self.subparser.add_argument(
        '--firmware', default='-firmware/*.sh',
        type=ArgTypes.GlobPathOrNone,
        help=('optional path to a firmware update (chromeos-firmwareupdate); '
              'if not specified, use the firmware from release image '
              '(--release_image), or "none" to skip running firmware update.'))
    self.subparser.add_argument(
        '--factory_shim', default='factory_shim/*.bin',
        type=ArgTypes.GlobPath,
        help=('path to a factory shim (build_image factory_install), '
              'default: %(default)s'))
    # TODO(hungte) Should we have default value for this?
    self.subparser.add_argument(
        '--complete_script', dest='complete',
        help='path to a script for the last-step execution of factory install')
    self.subparser.add_argument(
        '--board',
        help='board name for dynamic installation')
    self.subparser.add_argument(
        '-o', '--output', required=True,
        help='path to the output RMA image file')

  def Run(self):
    # TODO(hungte) always print bundle info (what files have been found)
    with SysUtils.TempDirectory(prefix='rma_') as temp_dir:

      # Solve optional arguments.
      board = self.args.board
      firmware = self.args.firmware
      part = Partition(self.args.release_image, PART_CROS_ROOTFS_A)

      if not board:
        with part.MountAsCrOSRootfs() as root:
          board = LSBFile(
              os.path.join(root, 'etc', 'lsb-release')).GetChromeOSBoard()
      if not board:
        raise RuntimeError('--board argument must be manually specified.')

      # Load firmware updater from release image if not given.
      temp_updater = None
      if not firmware:
        temp_updater = part.CopyFile(
            PATH_CROS_FIRMWARE_UPDATER, temp_dir, fs_type=FS_TYPE_CROS_ROOTFS)
        firmware = temp_updater
      elif firmware == STR_NONE:
        firmware = None

      print('Generating RMA image for board %s' % board)
      bundle = ChromeOSFactoryBundle(
          temp_dir=temp_dir,
          board=board,
          release_image=self.args.release_image,
          test_image=self.args.test_image,
          toolkit=self.args.toolkit,
          factory_shim=self.args.factory_shim,
          firmware=firmware,
          hwid=self.args.hwid,
          complete=self.args.complete)
      bundle.CreateRMAImage(self.args.output)

    print('OK: Generated %s RMA image at %s' % (board, self.args.output))


class CreateDockerImageCommand(SubCommand):
  """Create a Docker image from existing Chromium OS disk image."""
  name = 'docker'

  def Init(self):
    self.subparser.add_argument(
        '-i', '--image', type=ArgTypes.ExistsPath, required=True,
        help='path to the Chromium OS image')

  def _CreateDocker(self, image, root):
    """Creates a docker image from prepared rootfs and stateful partition.

    Args:
      image: a path to raw input image.
      root: a path to prepared (mounted) Chromium OS disk image.
    """
    logging.debug('Checking image board and version...')
    lsb_data = LSBFile(os.path.join(root, 'etc', 'lsb-release'))
    board = lsb_data.GetChromeOSBoard()
    version = lsb_data.GetChromeOSVersion()
    if not board or not version:
      raise RuntimeError('Input image does not have proper Chromium OS '
                         'board [%s] or version [%s] info.' % (board, version))
    docker_name = 'cros/%s_test:%s' % (board, version)
    docker_tag = 'cros/%s_test:%s' % (board, 'latest')
    print('Creating Docker image as %s ...' % docker_name)

    # Use pv if possible. It may be hard to estimate the real size of files in
    # mounted folder so we will use 2/3 of raw disk image - which works on most
    # test images.
    try:
      pv = '%s -s %s' % (SysUtils.FindCommand('pv'),
                         os.path.getsize(image) / 3 * 2)
    except Exception:
      pv = 'cat'

    Sudo('tar -C "%s" -c . | %s | docker import - "%s"' %
         (root, pv, docker_name))
    Sudo(['docker', 'tag', docker_name, docker_tag])
    return docker_name

  def Run(self):
    rootfs_part = Partition(self.args.image, PART_CROS_ROOTFS_A)
    state_part = Partition(self.args.image, PART_CROS_STATEFUL)

    with state_part.Mount() as state:
      with rootfs_part.MountAsCrOSRootfs() as rootfs:
        Sudo(['mount', '--bind', os.path.join(state, 'var_overlay'),
              os.path.join(rootfs, 'var')])
        Sudo(['mount', '--bind', os.path.join(state, 'dev_image'),
              os.path.join(rootfs, 'usr', 'local')])
        docker_name = self._CreateDocker(self.args.image, rootfs)

    print('OK: Successfully built docker image [%s] from %s.' %
          (docker_name, self.args.image))


def main():
  parser = argparse.ArgumentParser(
      prog='image_tool',
      description=(
          'Tools to manipulate Chromium OS disk images for factory. '
          'Use "image_tool help COMMAND" for more info on a '
          'subcommand.'))
  parser.add_argument('--verbose', '-v', action='count', default=0,
                      help='Verbose output')
  subparsers = parser.add_subparsers(title='subcommands')
  argv0 = os.path.splitext(os.path.basename(sys.argv[0]))[0]

  selected_command = None
  for unused_key, v in sorted(globals().items()):
    if v != SubCommand and inspect.isclass(v) and issubclass(v, SubCommand):
      subcommand = v(parser, subparsers)
      subcommand.Init()
      if argv0 in subcommand.aliases:
        selected_command = subcommand.name

  if selected_command:
    args = parser.parse_args([selected_command] + sys.argv[1:])
  else:
    args = parser.parse_args()
  logging.basicConfig(level=logging.WARNING - args.verbose * 10)

  args.subcommand.args = args
  args.subcommand.Run()


if __name__ == '__main__':
  main()
