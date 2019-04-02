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
import json
import logging
import os
import pipes
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import urlparse

# The edit_lsb command works better if readline enabled, but will still work if
# that is not available.
try:
  import readline  # pylint: disable=unused-import
except ImportError:
  pass

# This file needs to run on various environments, for example a fresh Ubuntu
# that does not have Chromium OS source tree nor chroot. So we do want to
# prevent introducing more cros.factory dependency except very few special
# modules (pygpt, fmap, netboot_firmware_settings).
# Please don't add more cros.factory modules.
import factory_common  # pylint: disable=unused-import
from cros.factory.utils import fmap
from cros.factory.utils import pygpt
from cros.factory.tools import netboot_firmware_settings


# Partition index for Chrome OS stateful partition.
PART_CROS_STATEFUL = 1
# Partition index for Chrome OS kernel A.
PART_CROS_KERNEL_A = 2
# Partition index for Chrome OS rootfs A.
PART_CROS_ROOTFS_A = 3
# Partition index for Chrome OS kernel B.
PART_CROS_KERNEL_B = 4
# Partition index for Chrome OS rootfs B.
PART_CROS_ROOTFS_B = 5
# Special options to mount Chrome OS rootfs partitions. (-t ext2, -o ro).
FS_TYPE_CROS_ROOTFS = 'ext2'
# Relative path of firmware updater on Chrome OS disk images.
PATH_CROS_FIRMWARE_UPDATER = '/usr/sbin/chromeos-firmwareupdate'
# The name of folder must match /etc/init/cros-payloads.conf.
DIR_CROS_PAYLOADS = 'cros_payloads'
# Relative path of RMA image metadata.
CROS_RMA_METADATA = 'rma_metadata.json'
PATH_CROS_RMA_METADATA = os.path.join(DIR_CROS_PAYLOADS, CROS_RMA_METADATA)
# Mode for new created folder, 0755 = u+rwx, go+rx
MODE_NEW_DIR = 0o755
# Regular expression for parsing LSB value, which should be sh compatible.
RE_LSB = re.compile(r'^ *(.*)="?(.*[^"])"?$', re.MULTILINE)
# Key for Chrome OS board name in /etc/lsb-release.
KEY_LSB_CROS_BOARD = 'CHROMEOS_RELEASE_BOARD'
# Key for Chrome OS build version in /etc/lsb-release.
KEY_LSB_CROS_VERSION = 'CHROMEOS_RELEASE_VERSION'
# Regular expression for reading file system information from dumpe2fs.
RE_BLOCK_COUNT = re.compile(r'^Block count: *(.*)$', re.MULTILINE)
RE_BLOCK_SIZE = re.compile(r'^Block size: *(.*)$', re.MULTILINE)
# Simple constant(s)
MEGABYTE = 1048576
# The storage industry treat "mega" and "giga" differently.
GIGABYTE_STORAGE = 1000000000
# Default size of each disk block (or sector).
DEFAULT_BLOCK_SIZE = pygpt.GPT.DEFAULT_BLOCK_SIZE
# Components for cros_payload
PAYLOAD_COMPONENTS = [
    'release_image', 'test_image',
    'toolkit', 'firmware', 'hwid', 'complete', 'toolkit_config']
# Payload types
PAYLOAD_TYPE_TOOLKIT_CONFIG = 'toolkit_config'
# Payload subtypes
PAYLOAD_SUBTYPE_VERSION = 'version'


def MakePartition(block_dev, part):
  """Helper function to build Linux device path for storage partition."""
  return '%s%s%s' % (block_dev, 'p' if block_dev[-1].isdigit() else '', part)


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
    If the pattern has '|', split the pattern by '|' and return the first
    matched pattern.
    """
    allow_none = False
    if pattern.startswith('-'):
      # Special trick to allow defaults.
      pattern = pattern[1:]
      allow_none = True
    goals = pattern.split('|')
    for i, goal in enumerate(goals):
      found = glob.glob(goal)
      if len(found) < 1:
        if i + 1 < len(goals):
          continue
        if allow_none:
          return None
        raise argparse.ArgumentTypeError('Does not exist: %s' % pattern)
      if len(found) > 1:
        raise argparse.ArgumentTypeError(
            'Too many files found for <%s>: %s' % (pattern, found))
      return found[0]


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
      commands = 'sudo -E ' + commands
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

  @classmethod
  def FindCommands(cls, *commands):
    """Find any of the given commands in order."""
    for cmd in commands:
      try:
        return cls.FindCommand(cmd)
      except Exception:
        pass
    raise RuntimeError(
        'Cannot find any of the following commands: %s' % ', '.join(commands))

  @classmethod
  def FindCGPT(cls):
    """Returns the best match of `cgpt` style command.

    The `cgpt` is a native program that is hard to deploy. As an alternative, we
    have the `pygpt` that emulates most of its functions, and that is accessible
    via `image_tool gpt`.
    """
    if os.path.exists(__file__) and os.access(__file__, os.X_OK):
      return '%s gpt' % __file__

    # Are we inside PAR?
    par_path = os.environ.get('PAR_PATH')
    if par_path:
      if os.path.basename(par_path) == 'image_tool':
        return '%s gpt' % par_path
      return 'sh %s image_tool gpt' % par_path

    # Nothing more - let's try to find the real programs.
    return cls.FindCommands('pygpt', 'cgpt')

  @classmethod
  def FindBZip2(cls):
    """Returns a path to best working 'bzip2'."""
    return cls.FindCommands('lbzip2', 'pbzip2', 'bzip2')

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

  @staticmethod
  def PartialCopy(src_path, dest_path, count, src_offset=0, dest_offset=0,
                  buffer_size=32 * MEGABYTE, sync=False, verbose=None):
    """Copy partial contents from one file to another file, like 'dd'."""
    with open(src_path, 'rb') as src:
      if verbose is None:
        verbose = count / buffer_size > 5
      with open(dest_path, 'r+b') as dest:
        fd = dest.fileno()
        src.seek(src_offset)
        dest.seek(dest_offset)
        remains = count
        while remains > 0:
          data = src.read(min(remains, buffer_size))
          dest.write(data)
          remains -= len(data)
          if sync:
            dest.flush()
            os.fdatasync(fd)
          if verbose:
            if sys.stderr.isatty():
              width = 5
              sys.stderr.write(
                  '%*.1f%%%s' % (width, (1 - float(remains) / count) * 100,
                                 '\b' * (width + 1)))
            else:
              sys.stderr.write('.')
    if verbose:
      sys.stderr.write('\n')

  @staticmethod
  def GetDiskUsage(path):
    return int(SudoOutput(['du', '-sk', path]).split()[0]) * 1024

  @staticmethod
  def GetRemainingSize(path):
    return int(
        SudoOutput(['df', '-k', '--output=avail', path]).splitlines()[1]) * 1024

  @staticmethod
  @contextlib.contextmanager
  def SetUmask(mask):
    old_umask = os.umask(mask)
    try:
      yield
    finally:
      os.umask(old_umask)


# Short cut to SysUtils.
Shell = SysUtils.Shell
Sudo = SysUtils.Sudo
SudoOutput = SysUtils.SudoOutput


class CrosPayloadUtils(object):
  """Collection of cros_payload utilities."""

  _cros_payload = None

  @classmethod
  def GetProgramPath(cls):
    """Gets the path for `cros_payload` program."""
    if cls._cros_payload:
      return cls._cros_payload
    cls._cros_payload = SysUtils.FindCommand('cros_payload')
    return cls._cros_payload

  @staticmethod
  def GetJSONPath(payloads_dir, board):
    return os.path.join(payloads_dir, '%s.json' % board)

  @staticmethod
  def AddMountedPayloadFile(mounted_payloads_dir, file_name, content):
    with tempfile.NamedTemporaryFile() as f:
      f.write(content)
      f.flush()
      os.chmod(f.name, 0o644)
      dest = os.path.join(mounted_payloads_dir, file_name)
      Sudo(['cp', '-pf', f.name, dest])
      Sudo(['chown', 'root:root', dest])

  @classmethod
  def InitMetaData(cls, payloads_dir, board, mounted=False):
    json_path = cls.GetJSONPath(payloads_dir, board)
    if mounted:
      cls.AddMountedPayloadFile(payloads_dir, os.path.basename(json_path), '{}')
    else:
      with open(json_path, 'w') as f:
        f.write('{}')
    return json_path

  @classmethod
  def AddComponent(cls, json_path, component, resource, **kargs):
    if not os.path.exists(json_path):
      logging.warning('Cannot find %s', json_path)
      return
    Shell([cls.GetProgramPath(), 'add', json_path, component, resource],
          **kargs)

  @classmethod
  def InstallComponents(cls, json_path, dest, components, **kargs):
    if not os.path.exists(json_path):
      logging.warning('Cannot find %s', json_path)
      return
    if isinstance(components, basestring):
      components = [components]
    Sudo([cls.GetProgramPath(), 'install', json_path, dest] + components,
         **kargs)

  @classmethod
  def GetComponentVersions(cls, json_path):
    if not os.path.exists(json_path):
      logging.warning('Cannot find %s', json_path)
      return {}
    with open(json_path) as f:
      metadata = json.load(f)
      component_versions = {
          component: resource.get(PAYLOAD_SUBTYPE_VERSION, '<unknown>')
          for component, resource in metadata.iteritems()}
      # Make sure that there are no unknown components
      for component in component_versions:
        assert component in PAYLOAD_COMPONENTS, (
            'Unknown component "%s"' % component)
      return component_versions

  @classmethod
  def GetComponentFiles(cls, json_path, component):
    """Get a list of payload files for a component.

    If a board metadata JSON file is as follows:

    ```
    {
      "release_image": {
        "part1": "release_image.part1.gz",
        "part2": "release_image.part2.gz"
      }
    }
    ```

    GetComponentFiles(json_path, 'release_image') returns a list
    ['release_image.part1.gz', 'release_image.part2.gz']
    """
    if not os.path.exists(json_path):
      logging.warning('Cannot find %s', json_path)
      return []
    files = Shell([cls.GetProgramPath(), 'get_file', json_path, component],
                  output=True).strip().splitlines()
    return files

  @classmethod
  def GetAllComponentFiles(cls, json_path):
    """Get a list of payload files for all components.

    If a board metadata JSON file is as follows:

    ```
    {
      "release_image": {
        "part1": "release_image.part1.gz",
        "part2": "release_image.part2.gz"
      },
      "hwid": {
        "file": "hwid.gz"
      }
    }
    ```

    GetAllComponentFiles(json_path) returns a list
    ['release_image.part1.gz', 'release_image.part2.gz', 'hwid.gz']
    """
    if not os.path.exists(json_path):
      logging.warning('Cannot find %s', json_path)
      return []
    files = Shell([cls.GetProgramPath(), 'get_all_files', json_path],
                  output=True).strip().splitlines()
    return files

  @classmethod
  def ReplaceComponent(cls, json_path, component, resource):
    """Replace a component in a payload directory with a given file.

    Remove old payload files and add new files for a component. Doesn't check
    if the removed file is used by other boards. This function cannot directly
    replace payload components in a mounted image due to permission issues. To
    do so, we need to create a temporary directory, update the payloads in the
    directory, then use `ReplaceComponentsInImage()` function to replace the
    payload components in the image, e.g.

    ```
    with CrosPayloadUtils.TempPayloadsDir() as temp_dir:
      CrosPayloadUtils.CopyComponentsInImage(image, board, component, temp_dir)
      json_path = CrosPayloadUtils.GetJSONPath(temp_dir, board)
      CrosPayloadUtils.ReplaceComponent(json_path, component, resource)
      CrosPayloadUtils.ReplaceComponentsInImage(image, board, temp_dir)
    ```
    """
    payloads_dir = os.path.dirname(json_path)
    old_files = cls.GetComponentFiles(json_path, component)
    for f in old_files:
      old_file_path = os.path.join(payloads_dir, f)
      if os.path.exists(old_file_path):
        Sudo(['rm', '-f', old_file_path])
    cls.AddComponent(json_path, component, resource)

  @classmethod
  def CopyComponentsInImage(cls, image, board, components, dest_payloads_dir,
                            create_metadata=False):
    """Copy payload metadata json file and component files from an image..

    Args:
      image: path to RMA shim image.
      board: board name.
      components: a list of payload components to copy from the shim image.
      dest_payloads_dir: directory to copy to.
      create_metadata: True to create board metadata file if it doesn't exist
                       in shim image.
    """
    dest_json_path = cls.GetJSONPath(dest_payloads_dir, board)

    # Copy metadata and components to the temp directory.
    with Partition(image, PART_CROS_STATEFUL).Mount() as stateful:
      image_payloads_dir = os.path.join(stateful, DIR_CROS_PAYLOADS)
      image_json_path = cls.GetJSONPath(image_payloads_dir, board)

      if os.path.exists(image_json_path):
        Shell(['cp', '-pf', image_json_path, dest_json_path])
      elif create_metadata:
        cls.InitMetaData(dest_payloads_dir, board)
      else:
        raise RuntimeError('Cannot find %s.' % image_json_path)

      for component in components:
        files = cls.GetComponentFiles(image_json_path, component)
        for f in files:
          f_path = os.path.join(image_payloads_dir, f)
          Shell(['cp', '-pf', f_path, dest_payloads_dir])

  @classmethod
  def ReplaceComponentsInImage(cls, image, board, new_payloads_dir):
    """Replace payload metada json file and component files in an image.

    Args:
      image: path to RMA shim image.
      board: board name.
      new_payloads_dir: directory containing the new payload files.
    """
    new_json_path = cls.GetJSONPath(new_payloads_dir, board)

    with Partition(image, PART_CROS_STATEFUL).Mount(rw=True) as stateful:
      rma_metadata = _ReadRMAMetadata(stateful)
      old_payloads_dir = os.path.join(stateful, DIR_CROS_PAYLOADS)
      old_json_path = cls.GetJSONPath(old_payloads_dir, board)

      # Remove unused and duplicate files.
      old_files = set(cls.GetAllComponentFiles(old_json_path))
      new_files = set(cls.GetAllComponentFiles(new_json_path))
      other_files = set()
      for info in rma_metadata:
        if info.board != board:
          board_component_files = cls.GetAllComponentFiles(
              cls.GetJSONPath(old_payloads_dir, info.board))
          other_files.update(board_component_files)

      # Remove old files that are not used by any boards.
      for f in old_files - new_files - other_files:
        file_path = os.path.join(old_payloads_dir, f)
        print('Remove old payload file %s.' % os.path.basename(f))
        Sudo(['rm', '-f', file_path])

      # Don't copy files that already exists.
      for f in new_files & (old_files | other_files):
        file_path = os.path.join(new_payloads_dir, f)
        if os.path.exists(file_path):
          Sudo(['rm', '-f', file_path])

      remain_size = SysUtils.GetRemainingSize(stateful)
      new_payloads_size = SysUtils.GetDiskUsage(new_payloads_dir)

    # When expanding or shrinking a partition, leave an extra 10M margin. 10M
    # is just a size larger than most small payloads, so that we don't need to
    # change the partition size when updating the small payloads.
    margin = 10 * MEGABYTE

    # Expand stateful partition if needed.
    if remain_size < new_payloads_size:
      ExpandPartition(
          image, PART_CROS_STATEFUL, new_payloads_size - remain_size + margin)

    # Move the added payloads to stateful partition.
    print('Moving payloads (%dM)...' % (new_payloads_size / MEGABYTE))
    with Partition(image, PART_CROS_STATEFUL).Mount(rw=True) as stateful:
      Sudo(['chown', '-R', 'root:root', new_payloads_dir])
      Sudo(['rsync', '-a', new_payloads_dir, stateful])

    # Shrink stateful partition.
    if remain_size > new_payloads_size + 2 * margin:
      ShrinkPartition(
          image, PART_CROS_STATEFUL, remain_size - new_payloads_size - margin)

  @classmethod
  @contextlib.contextmanager
  def TempPayloadsDir(cls):
    with SysUtils.TempDirectory() as temp_dir:
      temp_payloads_dir = os.path.join(temp_dir, DIR_CROS_PAYLOADS)
      with SysUtils.SetUmask(0o022):
        os.mkdir(temp_payloads_dir, MODE_NEW_DIR)
      yield temp_payloads_dir


def Aligned(value, alignment):
  """Helper utility to calculate aligned numbers.

  Args:
    value: an integer as original value.
    alignment: an integer for alignment.
  """
  remains = value % alignment
  return value - remains + (alignment if remains else 0)


class GPT(pygpt.GPT):
  """A special version GPT object with more helper utilities."""

  class Partition(pygpt.GPT.Partition):
    """A special GPT Partition object with mount ability."""

    @staticmethod
    @contextlib.contextmanager
    def _Map(image, offset, size, partscan=False, block_size=None):
      """Context manager to map (using losetup) partition(s) from disk image.

      Args:
        image: a path to disk image to map.
        offset: an integer as offset to partition, or None to map whole disk.
        size: an integer as partition size, or None for whole disk.
        partscan: True to scan partition table and create sub device files.
        block_size: specify the size of each logical block.
      """
      loop_dev = None
      args = ['losetup', '--show', '--find']
      if offset is None:
        # Note "losetup -P" needs Ubuntu 15+.
        # TODO(hungte) Use partx if -P is not supported (partx -d then -a).
        if partscan:
          args += ['-P']
      else:
        args += ['-o', str(offset), '--sizelimit', str(size)]
      if block_size is not None and block_size != pygpt.GPT.DEFAULT_BLOCK_SIZE:
        # For Linux kernel without commit "loop: add ioctl for changing logical
        # block size", calling "-b 512" will fail, so we should only add "-b"
        # when needed, so people with standard block size can work happily
        # without upgrading their host kernel.
        args += ['-b', str(block_size)]
      args += [image]

      try:
        loop_dev = SudoOutput(args).strip()
        yield loop_dev
      finally:
        if loop_dev:
          Sudo(['umount', '-R', loop_dev], check=False, silent=True)
          Sudo(['losetup', '-d', loop_dev], check=False, silent=True)
          # `losetup -d` doesn't detach the loop device immediately, which might
          # cause future mount failures. Make sure that the loop device is
          # detached before returning.
          while True:
            output = SudoOutput(['losetup', '-j', image]).strip()
            regex = r'^' + re.escape(loop_dev)
            if not re.search(regex, output, re.MULTILINE):
              break
            time.sleep(0.1)

    def Map(self):
      """Maps given partition to loop block device."""
      logging.debug('Map %s: %s(+%s)', self, self.offset, self.size)
      return self._Map(self.image, self.offset, self.size)

    @classmethod
    def MapAll(cls, image, partscan=True, block_size=None):
      """Maps an image with all partitions to loop block devices.

      Map the image to /dev/loopN, and all partitions will be created as
      /dev/loopNpM, where M stands for partition number.
      This is not supported by older systems.

      Args:
        image: a path to disk image to map.
        partscan: True to scan partition table and create sub device files.
        block_size: specify the size of each logical block.

      Returns:
        The mapped major loop device (/dev/loopN).
      """
      return cls._Map(image, None, None, partscan, block_size)

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
      if GPT.IsBlockDevice(self.image):
        try:
          mount_dev = MakePartition(self.image, self.number)
          mounted_dir = Shell(['lsblk', '-n', '-o', 'MOUNTPOINT', mount_dev],
                              output=True).strip()
          if mounted_dir:
            logging.debug('Already mounted: %s', self)
            yield mounted_dir
            return
        except Exception:
          pass

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
      """Mounts as Chrome OS root file system with rootfs verification enabled.

      The Chrome OS disk image with rootfs verification turned on will enable
      the RO bit in ext2 attributes and can't be mounted without specifying
      mount arguments "-t ext2 -o ro".
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
      # The 'block' in file system may be different from disk/partition logical
      # block size (LBA).
      fs_block_count = int(RE_BLOCK_COUNT.findall(raw_info)[0])
      fs_block_size = int(RE_BLOCK_SIZE.findall(raw_info)[0])
      return fs_block_count * fs_block_size

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
        # e2fsck may return 1 "errors corrected" or 2 "corrected and need
        # reboot".
        old_size = self._ParseExtFileSystemSize(raw_part)
        result = Sudo(['e2fsck', '-y', '-f', raw_part], check=False)
        if result > 2:
          raise RuntimeError('Failed ensuring file system integrity (e2fsck).')
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

    def Copy(self, dest, check_equal=True, sync=False, verbose=False):
      """Copies one partition to another partition.

      Args:
        dest: a Partition object as the destination.
        check_equal: True to raise exception if the sizes of partitions are
                     different.
      """
      if self.size != dest.size:
        if check_equal:
          raise RuntimeError(
              'Partition size is different (%d, %d).' % (self.size, dest.size))
        elif self.size > dest.size:
          raise RuntimeError(
              'Source partition (%s) is larger than destination (%s).' %
              (self.size, dest.size))
      if verbose:
        logging.info('Copying partition %s => %s...', self, dest)
      SysUtils.PartialCopy(self.image, dest.image, self.size, self.offset,
                           dest.offset, sync=sync)


def Partition(image, number):
  """Returns a GPT object by given parameters."""
  part = GPT.LoadFromFile(image).GetPartition(number)
  if part.IsUnused():
    raise RuntimeError('Partition %s is unused.' % part)
  return part

def ExpandPartition(image, number, size):
  """Expands an image partition for at least `size` bytes.

  By default, ext2/3/4 file system reserves 5% space for root, so we round
  (`size` * 1.05) up to a multiple of block size, and expand that amount
  of space. The partition should be the last partition of the image.

  Args:
    image: a path to an image file.
    number: 1-based partition number.
    size: Amount of space in bytes to expand.
  """
  gpt = GPT.LoadFromFile(image)
  part = gpt.GetPartition(number)
  # Check that the partition is the last partition.
  if part.IsUnused() or gpt.GetMaxUsedLBA() > part.LastLBA:
    raise RuntimeError('Cannot expand partition %d; '
                       'must be the last one in LBA layout.' % number)

  old_size = gpt.GetSize()
  new_size = old_size + Aligned(int(size * 1.05), part.block_size)
  print('Changing size: %d M => %d M' %
        (old_size / MEGABYTE, new_size / MEGABYTE))

  Shell(['truncate', '-s', str(new_size), image])
  gpt.Resize(new_size)
  gpt.ExpandPartition(number)
  gpt.WriteToFile(image)
  gpt.WriteProtectiveMBR(image, create=True)
  part.ResizeFileSystem()

def ShrinkPartition(image, number, size):
  """Shrinks an image partition for at most `size` bytes.

  Round `size` down to a multiple of block size, and reduce that amount of
  space for a partition. The partition should be the last partition of the
  image.

  Args:
    image: a path to an image file.
    number: 1-based partition number.
    size: Amount of space in bytes to reduce.
  """
  gpt = GPT.LoadFromFile(image)
  part = gpt.GetPartition(number)
  reduced_size = (size / part.block_size) * part.block_size
  # Check that the partition is the last partition.
  if part.IsUnused() or gpt.GetMaxUsedLBA() > part.LastLBA:
    raise RuntimeError('Cannot expand partition %d; '
                       'must be the last one in LBA layout.' % number)
  # Check that the partition size is greater than shrink size.
  if part.size <= reduced_size:
    raise RuntimeError('Cannot shrink partition %d. Size too small.' % number)

  old_size = gpt.GetSize()
  new_size = old_size - reduced_size
  print('Changing size: %d M => %d M' %
        (old_size / MEGABYTE, new_size / MEGABYTE))

  part.ResizeFileSystem(part.size - reduced_size)
  Shell(['truncate', '-s', str(new_size), image])
  gpt.Resize(new_size, check_overlap=False)
  gpt.ExpandPartition(number)
  gpt.WriteToFile(image)
  gpt.WriteProtectiveMBR(image, create=True)

class LSBFile(object):
  """Access /etc/lsb-release file (or files in same format).

  The /etc/lsb-release can be loaded directly by shell ( . /etc/lsb-release ).
  There is no really good and easy way to parse that without sh, but fortunately
  for the fields we care, it's usually A=B or A="B C".

  Also, in Chrome OS, the /etc/lsb-release was implemented without using quotes
  (i,e., A=B C, no matter if the value contains space or not).
  """
  def __init__(self, path=None, is_cros=True):
    self._path = path
    self._raw_data = ''
    self._dict = {}
    self._is_cros = is_cros
    if not path:
      return

    with open(path) as f:
      self._raw_data = f.read().strip()  # Remove trailing \n or \r
      self._dict = dict(RE_LSB.findall(self._raw_data))

  def AsRawData(self):
    return self._raw_data

  def AsDict(self):
    return self._dict

  def GetPath(self):
    return self._path

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
    self._raw_data = re.sub(r'^' + re.escape(key) + r'=.*\n*', '',
                            self._raw_data, flags=re.MULTILINE)

  def Install(self, destination, backup=False):
    """Installs the contents to the given location as lsb-release style file.

    The file will be owned by root:root, with file mode 0644.
    """
    with tempfile.NamedTemporaryFile(prefix='lsb_') as f:
      f.write(self._raw_data + '\n')
      f.flush()
      os.chmod(f.name, 0o644)
      if backup and os.path.exists(destination):
        bak_file = '%s.bak.%s' % (destination, time.strftime('%Y%m%d%H%M%S'))
        Sudo(['cp', '-pf', destination, bak_file])
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


class RMAImageBoardInfo(object):
  """Store the RMA image information related to one board."""

  __slots__ = ['board', 'kernel', 'rootfs']

  def __init__(self,
               board,
               kernel=PART_CROS_KERNEL_A,
               rootfs=PART_CROS_ROOTFS_A):
    self.board = board
    self.kernel = kernel
    self.rootfs = rootfs

  def ToDict(self):
    return {k: getattr(self, k) for k in self.__slots__}


def _WriteRMAMetadata(stateful, board_list):
  """Write RMA metadata to mounted stateful parititon.

  Args:
    stateful: path of stateful partition mount point.
    board_list: a list of RMAImageBoardInfo object.
  """
  payloads_dir = os.path.join(stateful, DIR_CROS_PAYLOADS)
  content = json.dumps([b.ToDict() for b in board_list])
  CrosPayloadUtils.AddMountedPayloadFile(
      payloads_dir, CROS_RMA_METADATA, content)


def _ReadRMAMetadata(stateful):
  """Read RMA metadata from mounted stateful partition.

  Args:
    stateful: path of stateful partition mount point.

  Returns:
    RMA metadata, which is a list of RMAImageBoardInfo.

  Raises:
    RuntimeError if the file doesn't exist and cannot auto-generate either.
  """
  if os.path.exists(os.path.join(stateful, PATH_CROS_RMA_METADATA)):
    with open(os.path.join(stateful, PATH_CROS_RMA_METADATA)) as f:
      metadata = json.load(f)
      metadata = [
          RMAImageBoardInfo(board=e['board'],
                            kernel=e['kernel'],
                            rootfs=e['rootfs'])
          for e in metadata]
      return metadata
  else:
    logging.warning('Cannot find %s.', PATH_CROS_RMA_METADATA)
    # Check if it is a legacy single-board RMA shim.
    found = glob.glob(os.path.join(stateful, DIR_CROS_PAYLOADS, '*.json'))
    if len(found) == 1:
      logging.warning('Found legacy RMA shim. Auto-generating metadata.')
      board = os.path.basename(found[0]).split('.')[0]
      metadata = [RMAImageBoardInfo(board=board, kernel=2, rootfs=3)]
      return metadata
    else:
      raise RuntimeError('Cannot get metadata, is this a RMA shim?')


class RMABoardResourceVersions(object):
  """Store the RMA resource versions related to one board."""

  __slots__ = ['board', 'install_shim'] + PAYLOAD_COMPONENTS

  def __init__(self, **kargs):
    for component, version in kargs.iteritems():
      assert component in self.__slots__, 'Unknown component "%s"' % component
      setattr(self, component, version)

  def __str__(self):
    max_len = max([len(s) for s in self.__slots__])
    return '\n'.join(['%-*s: %s' % (max_len, k, getattr(self, k, 'None'))
                      for k in self.__slots__])


def _ReadBoardResourceVersions(rootfs, stateful, board_info):
  """Read board resource versions from mounted stateful partition.

  Get board resource versions from <board>.json and install shim version.

  Args:
    stateful: path of stateful partition mount point.
    rootfs: path of rootfs mount point.
    board_info: a RMAImageBoardInfo instance.

  Returns:
    A RMABoardResourceVersions instance containing resource versions.
  """

  def _GetInstallShimVersion(rootfs):
    # Version of install shim rootfs.
    lsb_path = os.path.join(rootfs, 'etc', 'lsb-release')
    shim_version = LSBFile(lsb_path).GetChromeOSVersion(remove_timestamp=False)
    return shim_version

  versions = {
      'board': board_info.board,
      'install_shim': _GetInstallShimVersion(rootfs)}
  json_path = CrosPayloadUtils.GetJSONPath(
      os.path.join(stateful, DIR_CROS_PAYLOADS), board_info.board)
  payload_versions = CrosPayloadUtils.GetComponentVersions(json_path)
  versions.update(payload_versions)
  return RMABoardResourceVersions(**versions)


def UserSelect(title, options):
  """Ask user to select an option from the given options.

  Prints the options and their corresponding 1-based index, and let the user
  enter a number to select an option. The return value is 0-based.

  Args:
    title: question description.
    options: list of strings, each representing an option.

  Returns:
    The user selected number, between 0 and len(options)-1.
  """
  n = len(options)
  if n == 0:
    return None
  split_line = '-' * 25
  print(title)
  print(split_line)
  for i, option in enumerate(options, 1):
    print('[%d]' % i)
    print(option)
    print(split_line)

  while True:
    answer = raw_input(
        'Please select an option [1-%d]: ' % n).strip()
    try:
      selected = int(answer)
      if not 0 < selected <= n:
        print('Out of range: %d' % selected)
        continue
    except ValueError:
      print('Invalid option: %s' % answer)
      continue
    break
  # Convert to 0-based
  return selected - 1


class ChromeOSFactoryBundle(object):
  """Utilities to work with factory bundle."""

  # Types of build targets (for DefineBundleArguments to use).
  PREFLASH = 1
  RMA = 2
  BUNDLE = 3
  REPLACEABLE = 4

  def __init__(self, temp_dir, board, release_image, test_image, toolkit,
               factory_shim=None, enable_firmware=True, firmware=None,
               hwid=None, complete=None, netboot=None, toolkit_config=None,
               setup_dir=None, server_url=None):
    self._temp_dir = temp_dir
    # Member data will be looked up by getattr so we don't prefix with '_'.
    self._board = board
    self.release_image = release_image
    self.test_image = test_image
    self.toolkit = toolkit
    self.factory_shim = factory_shim
    self.enable_firmware = enable_firmware
    self._firmware = firmware
    self.hwid = hwid
    self.complete = complete
    self.netboot = netboot
    self.toolkit_config = toolkit_config
    self.setup_dir = setup_dir
    self.server_url = server_url

  @staticmethod
  def DefineBundleArguments(parser, build_type):
    """Define common argparse arguments to work with factory bundle.

    Args:
      parser: An argparse subparser to add argument definitions.
    """
    # Common arguments for all types. For ChromeOSFactoryBundle.REPLACEABLE,
    # everything is optional.
    if build_type in [ChromeOSFactoryBundle.REPLACEABLE]:
      parser.add_argument(
          '--release_image', default='-release_image/*.bin',
          type=ArgTypes.GlobPath,
          help=('path to a Chromium OS (release or recovery) image. '
                'default: %(default)s'))
      parser.add_argument(
          '--test_image', default='-test_image/*.bin',
          type=ArgTypes.GlobPath,
          help='path to a Chromium OS test image. default: %(default)s')
      parser.add_argument(
          '--toolkit', default='-toolkit/*.run',
          type=ArgTypes.GlobPath,
          help='path to a Chromium OS factory toolkit. default: %(default)s')
    else:
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

    # Additional arguments.
    if build_type in [ChromeOSFactoryBundle.RMA, ChromeOSFactoryBundle.BUNDLE,
                      ChromeOSFactoryBundle.REPLACEABLE]:
      # firmware/ may be updater*.sh or chromeos-firmwareupdate.
      parser.add_argument(
          '--firmware', default='-firmware/*update*',
          type=ArgTypes.GlobPath,
          help=('optional path to a firmware update (chromeos-firmwareupdate); '
                'if not specified, extract firmware from --release_image '
                'unless if --no-firmware is specified'))
      parser.add_argument(
          '--complete_script', dest='complete', default='-complete/*.sh',
          type=ArgTypes.GlobPath,
          help='path to a script for last-step execution of factory install')
      parser.add_argument(
          '--toolkit_config', dest='toolkit_config',
          default='-toolkit/*.json', type=ArgTypes.GlobPath,
          help='path to a config file to override test list constants')
      parser.add_argument(
          '--board',
          help='board name for dynamic installation')

    if build_type in [ChromeOSFactoryBundle.RMA, ChromeOSFactoryBundle.BUNDLE]:
      parser.add_argument(
          '--no-firmware', dest='enable_firmware', action='store_false',
          default=True,
          help='skip running firmware updater')
      parser.add_argument(
          '--factory_shim', default='factory_shim/*.bin',
          type=ArgTypes.GlobPath,
          help=('path to a factory shim (build_image factory_install), '
                'default: %(default)s'))

    if build_type in [ChromeOSFactoryBundle.BUNDLE]:
      parser.add_argument(
          '--setup_dir', default='-setup',
          type=ArgTypes.GlobPath,
          help='path to scripts for setup and deployment from factory zip')
      parser.add_argument(
          '--netboot', default='-netboot|factory_shim/netboot',
          type=ArgTypes.GlobPath,
          help='path to netboot firmware (image.net.bin) and kernel (vmlinuz)')
      # TODO(hungte) Support more flexible names like 'evt2'.
      parser.add_argument(
          '-p', '--phase', choices=['proto', 'evt', 'dvt', 'pvt', 'mp'],
          default='proto',
          help='build phase (evt, dvt, pvt or mp).')
      parser.add_argument(
          '-s', '--server_url',
          help='URL to factory server. The host part may be used for TFTP.')

  @property
  def board(self):
    """Determines the right 'board' configuration."""
    if self._board:
      return self._board

    part = Partition(self.release_image, PART_CROS_ROOTFS_A)
    with part.MountAsCrOSRootfs() as rootfs:
      self._board = LSBFile(
          os.path.join(rootfs, 'etc', 'lsb-release')).GetChromeOSBoard()
    logging.info('Detected board as %s from %s.', self._board, part)
    return self._board

  @property
  def firmware(self):
    if not self.enable_firmware:
      return None
    elif self._firmware is not None:
      return self._firmware

    part = Partition(self.release_image, PART_CROS_ROOTFS_A)
    logging.info('Loaded %s from %s.', PATH_CROS_FIRMWARE_UPDATER, part)
    self._firmware = part.CopyFile(
        PATH_CROS_FIRMWARE_UPDATER, self._temp_dir, fs_type=FS_TYPE_CROS_ROOTFS)
    return self._firmware

  @staticmethod
  def CreateDirectory(dir_name, mode=MODE_NEW_DIR):
    with SysUtils.SetUmask(0o022):
      os.mkdir(dir_name, mode)

  def CreatePayloads(self, target_dir):
    """Builds cros_payload contents into target_dir.

    This is needed to store payloads or install to another system.

    Args:
      target_dir: a path to a folder for generating cros_payload contents.

    Returns:
      The JSON path in target_dir for cros_payload to use.
    """
    logging.debug('Generating cros_payload contents...')
    json_path = CrosPayloadUtils.InitMetaData(target_dir, self.board)

    for component in PAYLOAD_COMPONENTS:
      resource = getattr(self, component)
      if resource:
        logging.debug('Add %s payloads from %s...', component, resource)
        CrosPayloadUtils.AddComponent(json_path, component, resource)
      else:
        print('Leaving %s component payload as empty.' % component)
    return json_path

  @staticmethod
  def CopyPayloads(src_dir, target_dir, json_path):
    """Copy cros_payload contents of a board to target_dir.

    Board metadata <board>.json stores the resources in a dictionary.

    {
      "release_image": {
        "version": <version>,
        "crx_cache": "release_image.crx_cache.xxx.gz",
        "part1": "release_image.part1.xxx.gz",
        ...
      },
      "test_image": {
        "version": <version>,
        "crx_cache": "test_image.crx_cache.xxx.gz",
        "part1": "test_image.part1.xxx.gz",
        ...
      },
      ...
    }

    The function copies resources of a board from src_dir to target_dir.

    Args:
      src_dir: path of source directory.
      target_dir: path of target directory.
      json_path: board metadata path <board>.json.
    """
    assert os.path.exists(src_dir), 'Path does not exist: %s' % src_dir
    assert os.path.exists(target_dir), 'Path does not exist: %s' % target_dir
    assert os.path.isfile(json_path), 'File does not exist: %s' % json_path

    Sudo('cp -p %s %s/' % (json_path, target_dir))
    with open(json_path) as f:
      metadata = json.load(f)
      for resource in metadata.values():
        for subtype, payload in resource.iteritems():
          if subtype == PAYLOAD_SUBTYPE_VERSION:
            continue
          path = os.path.join(src_dir, payload)
          assert os.path.isfile(path), 'Cannot find payload %s.' % path
          Sudo('cp -p %s %s/' % (path, target_dir))

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
        # The PMBR is always less than DEFAULT_BLOCK_SIZE, no matter if the
        # disk has larger sector size.
        dest.write(src.read(DEFAULT_BLOCK_SIZE))
    return pmbr_path

  def ExecutePartitionScript(
      self, image_path, block_size, pmbr_path, rootfs, verbose=False):
    """Creates a partition script from write_gpt.sh inside image_path.

    To initialize (create partition table) on a new preflashed disk image for
    Chrome OS, we need to execute the write_gpt.sh included in rootfs of disk
    images.

    Args:
      image_path: the disk image to initialize partition table.
      block_size: the size of each logical block.
      pmbr_path: a path to a file with PMBR code (by self.CreatePMBR).
      rootfs: a directory to root file system containing write_gpt.sh script.
      verbose: True to enable debug out of script execution (-x).
    """
    write_gpt_path = os.path.join(rootfs, 'usr', 'sbin', 'write_gpt.sh')
    chromeos_common_path = os.path.join(
        rootfs, 'usr', 'share', 'misc', 'chromeos-common.sh')

    if not os.path.exists(write_gpt_path):
      raise RuntimeError('Missing write_gpt.sh.')
    if not os.path.exists(chromeos_common_path):
      raise RuntimeError('Missing chromeos-common.sh.')

    # pygpt is already available, but to allow write_gpt.sh access gpt
    # commands, have to find an externally executable GPT.
    cgpt_command = SysUtils.FindCGPT()

    with GPT.Partition.MapAll(
        image_path, partscan=False, block_size=block_size) as loop_dev:
      # stateful partitions are enlarged only if the target is a block device
      # (not file), in order to reduce USB image size. As a result, we have to
      # run partition script with disk mapped.
      commands = [
          # Currently write_gpt.sh will load chromeos_common from a fixed path.
          # In future when it supports overriding ROOT, we can invoke prevent
          # sourcing chromeos_common.sh explicitly below.
          '. "%s"' % chromeos_common_path,
          '. "%s"' % write_gpt_path,
          'GPT="%s"' % cgpt_command,
          'set -e',
          'write_base_table "%s" "%s"' % (loop_dev, pmbr_path),
          # write_base_table will set partition #2 to S=0, T=15, P=15.
          # However, if update_engine is disabled (very common in factory) or if
          # the system has to do several quick reboots before reaching
          # chromeos-setgoodkernel, then the device may run out of tries without
          # setting S=1 and will stop booting. So we want to explicitly set S=1.
          '%s add -i 2 -S 1 "%s"' % (cgpt_command, loop_dev)]
      # The commands must be executed in a single invocation for '.' to work.
      command = ' ; '.join(commands)
      Sudo("bash %s -c '%s'" % ('-x' if verbose else '', command))

  def InitDiskImage(self, output, sectors, sector_size, verbose=False):
    """Initializes (resize and partition) a new disk image.

    Args:
      output: a path to disk image to initialize.
      sectors: integer for new size in number of sectors.
      sector_size: size of each sector (block) in bytes.
      verbose: provide more details when calling partition execution script.

    Returns:
      An integer as the size (in bytes) of output file.
    """
    new_size = sectors * sector_size
    print('Initialize disk image in %s*%s bytes [%s G]' %
          (sectors, sector_size, new_size / GIGABYTE_STORAGE))
    pmbr_path = self.GetPMBR(self.release_image)

    # TODO(hungte) Support block device as output, and support 'preserve'.
    Shell(['truncate', '-s', '0', output])
    Shell(['truncate', '-s', str(new_size), output])

    part = Partition(self.release_image, PART_CROS_ROOTFS_A)
    with part.MountAsCrOSRootfs() as rootfs:
      self.ExecutePartitionScript(
          output, sector_size, pmbr_path, rootfs, verbose)
    return new_size

  def CreateDiskImage(self, output, sectors, sector_size, stateful_free_space,
                      verbose=False):
    """Creates the installed disk image.

    This creates a complete image that can be pre-flashed to and boot from
    internal storage.

    Args:
      output: a path to disk image to initialize.
      sectors: number of sectors in disk image.
      sector_size: size of each sector in bytes.
      stateful_free_space: extra free space to claim in MB.
      verbose: provide more verbose output when initializing disk image.
    """
    new_size = self.InitDiskImage(output, sectors, sector_size, verbose)
    payloads_dir = os.path.join(self._temp_dir, DIR_CROS_PAYLOADS)
    self.CreateDirectory(payloads_dir)
    json_path = self.CreatePayloads(payloads_dir)

    with GPT.Partition.MapAll(output) as output_dev:
      CrosPayloadUtils.InstallComponents(
          json_path, output_dev, ['test_image', 'release_image'])

    # output_dev (via /dev/loopX) needs root permission so we have to leave
    # previous context and resize using the real disk image file.
    part = Partition(output, PART_CROS_STATEFUL)
    part.ResizeFileSystem(
        part.GetFileSystemSize() + stateful_free_space * MEGABYTE)
    with GPT.Partition.MapAll(output) as output_dev:
      targets = ['toolkit', 'release_image.crx_cache']
      if self.hwid:
        targets += ['hwid']
      CrosPayloadUtils.InstallComponents(json_path, output_dev, targets)

    logging.debug('Add /etc/lsb-factory if not exists.')
    with part.Mount(rw=True) as stateful:
      Sudo(['touch', os.path.join(stateful, 'dev_image', 'etc', 'lsb-factory')],
           check=False)
    return new_size

  def CreateRMAImage(self, output, active_test_list=None):
    """Creates the RMA bootable installation disk image.

    This creates an RMA image that can boot and install all factory software
    resouces to device.

    Args:
      output: a path to disk image to initialize.
      block_size: the size of block (sector) in bytes in output image.
    """
    # It is possible to enlarge the disk by calculating sizes of all input
    # files, create cros_payloads folder in the disk image file, to minimize
    # execution time. However, that implies we have to shrink disk image later
    # (due to gz), and run build_payloads using root, which are all not easy.
    # As a result, here we want to create payloads in temporary folder then copy
    # into disk image.
    payloads_dir = os.path.join(self._temp_dir, DIR_CROS_PAYLOADS)
    self.CreateDirectory(payloads_dir)
    json_path = self.CreatePayloads(payloads_dir)

    # Set active test_list
    if active_test_list:
      with tempfile.NamedTemporaryFile() as config_file:
        try:
          CrosPayloadUtils.InstallComponents(
              json_path, config_file.name, PAYLOAD_TYPE_TOOLKIT_CONFIG,
              silent=True)
          config = json.load(config_file)
        except Exception:
          config = {}
        config.update({'active_test_list': {'id': active_test_list}})
        config_file.seek(0)
        config_file.truncate()
        config_file.write(json.dumps(config, indent=2, separators=(',', ': ')))
        config_file.flush()
        CrosPayloadUtils.ReplaceComponent(
            json_path, PAYLOAD_TYPE_TOOLKIT_CONFIG, config_file.name)

    payloads_size = SysUtils.GetDiskUsage(payloads_dir)
    print('cros_payloads size: %s M' % (payloads_size / MEGABYTE))

    shutil.copyfile(self.factory_shim, output)
    ExpandPartition(output, PART_CROS_STATEFUL, payloads_size)

    with Partition(output, PART_CROS_STATEFUL).Mount(rw=True) as stateful:
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
      lsb_file.AppendValue('RMA_AUTORUN', 'true')
      lsb_file.Install(lsb_path)

      _WriteRMAMetadata(stateful,
                        board_list=[RMAImageBoardInfo(board=self.board)])

      Sudo(['df', '-h', stateful])

  @staticmethod
  def ShowRMAImage(image):
    """Show the content of a RMA image."""
    gpt = GPT.LoadFromFile(image)

    stateful_part = gpt.GetPartition(PART_CROS_STATEFUL)
    with stateful_part.Mount() as stateful:
      payloads_dir = os.path.join(stateful, DIR_CROS_PAYLOADS)
      if not os.path.exists(payloads_dir):
        raise RuntimeError('Cannot find dir /%s, is this a RMA shim?' %
                           DIR_CROS_PAYLOADS)

      metadata = _ReadRMAMetadata(stateful)

      print('This RMA shim contains boards: %s' % (
          ' '.join(board_info.board for board_info in metadata)))

      split_line = '-' * 25
      print(split_line)
      for board_info in metadata:
        with gpt.GetPartition(board_info.rootfs).MountAsCrOSRootfs() as rootfs:
          resource_versions = _ReadBoardResourceVersions(
              rootfs, stateful, board_info)
        print(resource_versions)
        print(split_line)

  class RMABoardEntry(object):
    """An internal class that stores the info of a board.

    The info includes
      board: board name.
      image: The image file that the board belongs to.
      versions: An RMABoardResourceVersions object being the payload versions
                of the board.
      kernel: A GPT.Partition object being the kernel partition of the board.
      rootfs: A GPT.Partition object being the rootfs partition of the board.
    """

    def __init__(self, board, image, versions, kernel, rootfs):
      self.board = board
      self.image = image
      self.versions = versions
      self.kernel = kernel
      self.rootfs = rootfs

    def GetPayloadSizes(self):
      """Returns a list of (resource name, resource size) of the board."""
      resources = []
      with Partition(self.image, PART_CROS_STATEFUL).Mount() as stateful:
        payloads_dir = os.path.join(stateful, DIR_CROS_PAYLOADS)
        json_path = CrosPayloadUtils.GetJSONPath(payloads_dir, self.board)
        json_file = os.path.basename(json_path)
        resources.append((json_file, SysUtils.GetDiskUsage(json_path)))
        with open(json_path) as f:
          metadata = json.load(f)
          for resource in metadata.values():
            for subtype, payload in resource.iteritems():
              if subtype == PAYLOAD_SUBTYPE_VERSION:
                continue
              path = os.path.join(payloads_dir, payload)
              resources.append((payload, SysUtils.GetDiskUsage(path)))
      return resources

  @staticmethod
  def _RecreateRMAImage(output, images, select_func):
    """Recreate RMA (USB installation) disk images using existing ones.

    A (universal) RMA image should have factory_install kernel and rootfs in
    partition (2n, 2n+1), and resources in stateful partition (partition 1)
    cros_payloads directory.  This function extracts some stateful partitions
    using a user defined function `select_func` and then generate the output
    image by merging the resource files to partition 1 and cloning kernel/rootfs
    partitions of each selected boards.

    The layout of the merged output image:
       1 stateful  [cros_payloads from all rmaimgX]
       2 kernel    [install-rmaimg1]
       3 rootfs    [install-rmaimg1]
       4 kernel    [install-rmaimg2]
       5 rootfs    [install-rmaimg2]
       6 kernel    [install-rmaimg3]
       7 rootfs    [install-rmaimg3]
      ...

    Args:
      output: a path to output image file.
      images: a list of image files.
      select_func: A function that takes a list of RMABoardEntry, and returns
                   a reduced list with same or less elements. The remaining
                   board entries will be merged into a single RMA shim.
    """

    def _GetPayloadSize(entries):
      """Get the sum of payload size of all board entries."""
      payloads = [entry.GetPayloadSizes() for entry in entries]
      payloads_set = set().union(*payloads)
      payloads_size = sum(p[1] for p in payloads_set)
      return payloads_size

    # A list of entries in every images.
    entries = []
    # A dict that maps an image to a list of entries that belongs to the image.
    image_entries_map = {}
    stateful_parts = []
    kern_rootfs_parts = []
    block_size = 0
    # Currently we only support merging images in same block size.
    for image in images:
      gpt = GPT.LoadFromFile(image)
      if block_size == 0:
        block_size = gpt.block_size
      assert gpt.block_size == block_size, (
          'Cannot merge image %s due to different block size (%s, %s)' %
          (image, block_size, gpt.block_size))
      stateful_parts.append(gpt.GetPartition(PART_CROS_STATEFUL))
      # A list of entries in `image`.
      image_entries = []
      with gpt.GetPartition(PART_CROS_STATEFUL).Mount() as stateful:
        src_metadata = _ReadRMAMetadata(stateful)
        for board_info in src_metadata:
          with gpt.GetPartition(
              board_info.rootfs).MountAsCrOSRootfs() as rootfs:
            versions = _ReadBoardResourceVersions(rootfs, stateful, board_info)
          entry = ChromeOSFactoryBundle.RMABoardEntry(
              board_info.board, image, versions,
              gpt.GetPartition(board_info.kernel),
              gpt.GetPartition(board_info.rootfs))
          image_entries.append(entry)

      entries += image_entries
      image_entries_map[image] = image_entries

    # Count the payload size of each images separately.
    old_payload_size = sum([_GetPayloadSize(image_entries)
                            for image_entries in image_entries_map.values()])
    entries = select_func(entries)
    # Count the payload size in the merged image.
    new_payload_size = _GetPayloadSize(entries)
    diff_payload_size = old_payload_size - new_payload_size
    assert diff_payload_size >= 0, 'Merged payload should not become larger.'

    for entry in entries:
      kern_rootfs_parts.append(entry.kernel)
      kern_rootfs_parts.append(entry.rootfs)

    # Build a new image based on first image's layout.
    gpt = pygpt.GPT.LoadFromFile(images[0])
    pad_blocks = gpt.header.FirstUsableLBA
    # We can remove at least `diff_payload_size` space from stateful partition,
    # but cannot make it smaller than the original size before copying the
    # contents.
    final_state_blocks = (
        sum(p.blocks for p in stateful_parts) - diff_payload_size / block_size)
    state_blocks = max(stateful_parts[0].blocks, final_state_blocks)
    data_blocks = state_blocks + sum(p.blocks for p in kern_rootfs_parts)
    # pad_blocks hold header and partition tables, in front and end of image.
    new_size = (data_blocks + pad_blocks * 2) * block_size

    logging.info('Creating new image file as %s M...', new_size / MEGABYTE)
    Shell(['truncate', '-s', '0', output])
    Shell(['truncate', '-s', str(new_size), output])

    # Clear existing entries because this GPT was cloned from other image.
    for p in gpt.partitions:
      p.Zero()
    gpt.Resize(new_size)
    assert (gpt.header.LastUsableLBA - gpt.header.FirstUsableLBA + 1 >=
            data_blocks), 'Disk image is too small.'

    used_guids = []
    def AddPartition(number, p, begin, blocks=None):
      next_lba = begin + (blocks or p.blocks)
      guid = p.UniqueGUID
      if guid in used_guids:
        # Ideally we don't need to change UniqueGUID, but if user specified same
        # disk images in images then this may cause problems, for example
        # INVALID_ENTRIES in cgpt.
        logging.warning(
            'Duplicated UniqueGUID found from %s, replace with random.', p)
        guid = pygpt.GUID.Random()
      used_guids.append(guid)
      # The target number location will be different so we have to clone,
      # update and call UpdatePartition with new number explicitly.
      p = p.Clone()
      p.Update(
          UniqueGUID=guid,
          FirstLBA=begin,
          LastLBA=next_lba - 1)
      gpt.UpdatePartition(p, number=number)
      return next_lba

    # Put stateful partition at the end so we can resize it if needed.
    begin = gpt.header.FirstUsableLBA
    for i, p in enumerate(kern_rootfs_parts, 2):
      begin = AddPartition(i, p, begin)
    stateful_begin = begin
    AddPartition(1, stateful_parts[0], stateful_begin, state_blocks)

    gpt.WriteToFile(output)
    gpt.WriteProtectiveMBR(output, create=True)
    new_state = Partition(output, PART_CROS_STATEFUL)
    old_state = Partition(images[0], PART_CROS_STATEFUL)
    # TODO(chenghan): Find a way to copy stateful without cros_payloads/
    old_state.Copy(new_state, check_equal=False)
    with new_state.Mount(rw=True) as stateful:
      payloads_dir = os.path.join(stateful, DIR_CROS_PAYLOADS)
      Sudo('rm -rf "%s"/*' % payloads_dir)

    if state_blocks == final_state_blocks:
      # Stateful partition is expanded
      logging.debug('Maximize stateful file system...')
      new_state.ResizeFileSystem()
    else:
      # Stateful partition needs to shrink
      logging.debug('Shrinking stateful file system...')
      ShrinkPartition(output, PART_CROS_STATEFUL, diff_payload_size)

    with new_state.Mount(rw=True) as stateful:
      board_list = []
      for index, entry in enumerate(entries):
        with Partition(entry.image, PART_CROS_STATEFUL).Mount() as src_dir:
          print('Copying %s board ...' % entry.board)
          # Copy payloads in stateful partition
          src_payloads_dir = os.path.join(src_dir, DIR_CROS_PAYLOADS)
          src_metadata_path = CrosPayloadUtils.GetJSONPath(
              src_payloads_dir, entry.board)
          target_payloads_dir = os.path.join(stateful, DIR_CROS_PAYLOADS)
          ChromeOSFactoryBundle.CopyPayloads(
              src_payloads_dir, target_payloads_dir, src_metadata_path)
          # Copy kernel/rootfs partitions
          new_kernel = index * 2 + PART_CROS_KERNEL_A
          new_rootfs = index * 2 + PART_CROS_ROOTFS_A
          entry.kernel.Copy(Partition(output, new_kernel))
          entry.rootfs.Copy(Partition(output, new_rootfs))
          board_list.append(
              RMAImageBoardInfo(entry.board, new_kernel, new_rootfs))

      _WriteRMAMetadata(stateful, board_list)

      Sudo(['df', '-h', stateful])

  @staticmethod
  def MergeRMAImage(output, images, auto_select):
    """Merges multiple RMA disk images into a single universal RMA image.

    When there are duplicate boards across different images, it asks user to
    decide which one to use, or auto-select if `auto_select` is set.
    """

    def _ResolveDuplicate(entries):
      board_map = {}
      for entry in entries:
        if entry.board not in board_map:
          board_map[entry.board] = []
        board_map[entry.board].append(entry)

      selected_entries = set()
      for board_name, board_entries in board_map.iteritems():
        if len(board_entries) == 1 or auto_select:
          selected = 0
        else:
          title = 'Board %s has more than one entry.' % board_name
          options = ['From %s\n%s' % (entry.image, entry.versions)
                     for entry in board_entries]
          selected = UserSelect(title, options)
        selected_entries.add(board_entries[selected])

      resolved_entries = [
          entry for entry in entries if entry in selected_entries]

      return resolved_entries

    ChromeOSFactoryBundle._RecreateRMAImage(output, images, _ResolveDuplicate)

  @staticmethod
  def ExtractRMAImage(output, image, select=None):
    """Extract a board image from a universal RMA image."""

    def _SelectBoard(entries):
      if select is not None:
        selected = int(select) - 1
        if not 0 <= selected < len(entries):
          raise ValueError('Index %d out of range.' % selected)
      else:
        title = 'Please select a board to extract.'
        options = [str(entry.versions) for entry in entries]
        selected = UserSelect(title, options)

      return [entries[selected]]

    ChromeOSFactoryBundle._RecreateRMAImage(output, [image], _SelectBoard)

  @staticmethod
  def ReplaceRMAPayload(image, board=None, **kargs):
    """Replace payloads in an RMA shim."""

    replaced_payloads = {
        component: payload for component, payload in kargs.iteritems()
        if payload is not None}
    for component in replaced_payloads:
      assert component in PAYLOAD_COMPONENTS, (
          'Unknown component "%s"', component)

    if board is None:
      with Partition(image, PART_CROS_STATEFUL).Mount() as stateful:
        rma_metadata = _ReadRMAMetadata(stateful)
      if len(rma_metadata) == 1:
        board = rma_metadata[0].board
      else:
        raise RuntimeError('Board not set.')

    with CrosPayloadUtils.TempPayloadsDir() as temp_dir:
      CrosPayloadUtils.CopyComponentsInImage(image, board, [], temp_dir)
      json_path = CrosPayloadUtils.GetJSONPath(temp_dir, board)
      for component, payload in replaced_payloads.iteritems():
        CrosPayloadUtils.ReplaceComponent(json_path, component, payload)
      CrosPayloadUtils.ReplaceComponentsInImage(image, board, temp_dir)

    with Partition(image, PART_CROS_STATEFUL).Mount() as stateful:
      Sudo(['df', '-h', stateful])

  @staticmethod
  def GetKernelVersion(image_path):
    raw_output = Shell(['file', image_path], output=True)
    versions = (line.strip().partition(' ')[2] for line in raw_output.split(',')
                if line.startswith(' version'))
    return next(versions, 'Unknown')

  @staticmethod
  def GetFirmwareVersion(image_path):
    with open(image_path) as f:
      fw_image = fmap.FirmwareImage(f.read())
      ro = fw_image.get_section('RO_FRID').strip('\xff').strip('\0')
      for rw_name in ['RW_FWID', 'RW_FWID_A']:
        if fw_image.has_section(rw_name):
          rw = fw_image.get_section(rw_name).strip('\xff').strip('\0')
          break
      else:
        raise RuntimeError('Unknown RW firmware version in %s' % image_path)
    return {'ro': ro, 'rw': rw}

  @staticmethod
  def GetFirmwareUpdaterVersion(updater):
    if not updater:
      return {}

    with SysUtils.TempDirectory() as extract_dir:
      Shell([updater, '--sb_extract', extract_dir], silent=True)
      targets = {'main': 'bios.bin', 'ec': 'ec.bin'}
      # TODO(hungte) Read VERSION.signer for signing keys.
      results = {}
      for target, image in targets.iteritems():
        image_path = os.path.join(extract_dir, image)
        if not os.path.exists(image_path):
          continue
        results[target] = ChromeOSFactoryBundle.GetFirmwareVersion(image_path)
    return results

  def GenerateTFTP(self, tftp_root):
    """Generates TFTP data in a given folder."""
    with open(os.path.join(tftp_root, '..', 'dnsmasq.conf'), 'w') as f:
      f.write(textwrap.dedent(
          '''\
          # This is a sample config, can be invoked by "dnsmasq -d -C FILE".
          interface=eth2
          tftp-root=/var/tftp
          enable-tftp
          dhcp-leasefile=/tmp/dnsmasq.leases
          dhcp-range=192.168.200.50,192.168.200.150,12h
          port=0'''))

    tftp_server_ip = ''
    if self.server_url:
      tftp_server_ip = urlparse.urlparse(self.server_url).hostname
      server_url_config = os.path.join(
          tftp_root, 'omahaserver_%s.conf' % self.board)
      with open(server_url_config, 'w') as f:
        f.write(self.server_url)

    cmdline_sample = os.path.join(
        tftp_root, 'chrome-bot', self.board, 'cmdline.sample')
    with open(cmdline_sample, 'w') as f:
      config = (
          'lsm.module_locking=0 cros_netboot_ramfs cros_factory_install '
          'cros_secure cros_netboot earlyprintk cros_debug loglevel=7 '
          'console=ttyS2,115200n8')
      if tftp_server_ip:
        config += ' tftpserverip=%s' % tftp_server_ip
      f.write(config)

  def CreateNetbootFirmware(self, src_path, dest_path):
    parser = argparse.ArgumentParser()
    netboot_firmware_settings.DefineCommandLineArgs(parser)
    # This comes from sys-boot/chromeos-bootimage: ${PORTAGE_USER}/${BOARD_USE}
    tftp_board_dir = 'chrome-bot/%s' % self.board
    args = [
        '--argsfile', os.path.join(tftp_board_dir, 'cmdline'),
        '--bootfile', os.path.join(tftp_board_dir, 'vmlinuz'),
        '--input', src_path,
        '--output', dest_path]
    if self.server_url:
      args += [
          '--factory-server-url', self.server_url,
          '--tftpserverip', urlparse.urlparse(self.server_url).hostname]
    netboot_firmware_settings.NetbootFirmwareSettings(parser.parse_args(args))

  @staticmethod
  def GetImageVersion(image):
    if not image:
      return 'N/A'
    part = Partition(image, PART_CROS_ROOTFS_A)
    with part.MountAsCrOSRootfs() as rootfs:
      lsb_path = os.path.join(rootfs, 'etc', 'lsb-release')
      return LSBFile(lsb_path).GetChromeOSVersion(remove_timestamp=False)

  def GetToolkitVersion(self, toolkit=None):
    return Shell([toolkit or self.toolkit, '--lsm'], output=True).strip()

  def CreateBundle(self, output_dir, phase, notes, timestamp=None):
    """Creates a bundle from given resources."""

    def FormatFirmwareVersion(info):
      if not info:
        return 'N/A'
      if info['ro'] == info['rw']:
        return info['ro']
      return 'RO: %s, RW: %s' % (info['ro'], info['rw'])

    def AddResource(dir_name, resources_glob, do_copy=False):
      """Adds resources to specified sub directory under bundle_dir.

      Returns the path of last created resource.
      """
      if not resources_glob:
        return None
      resources = glob.glob(resources_glob)
      if not resources:
        raise RuntimeError('Cannot find resource: %s' % resources_glob)
      resource_dir = os.path.join(bundle_dir, dir_name)
      if not os.path.exists(resource_dir):
        os.makedirs(resource_dir)
      dest_path = None
      for resource in resources:
        dest_name = os.path.basename(resource)
        # Many files downloaded from CPFE or GoldenEye may contain '%2F' in its
        # name and we want to remove them.
        strip = dest_name.rfind('%2F')
        if strip >= 0:
          # 3 as len('%2F')
          dest_name = dest_name[strip + 3:]
        dest_path = os.path.join(resource_dir, dest_name)
        if do_copy:
          shutil.copy(resource, dest_path)
        else:
          os.symlink(os.path.abspath(resource), dest_path)
      return dest_path

    if timestamp is None:
      timestamp = time.strftime('%Y%m%d%H%M')
    bundle_name = '%s_%s_%s' % (self.board, timestamp, phase)
    output_name = 'factory_bundle_%s.tar.bz2' % bundle_name
    bundle_dir = os.path.join(self._temp_dir, 'bundle')
    self.CreateDirectory(bundle_dir)

    try:
      part = Partition(self.release_image, PART_CROS_ROOTFS_A)
      release_firmware_updater = part.CopyFile(
          PATH_CROS_FIRMWARE_UPDATER, self._temp_dir,
          fs_type=FS_TYPE_CROS_ROOTFS)
    except IOError:
      if phase not in {'proto', 'evt', 'dvt'}:
        # chromeos-firmwareupate should always be available since PVT
        # Currently, phase name like 'evt2' is not allowed, allowed phase names
        # are {'proto', 'evt', 'dvt', 'pvt', 'mp'}
        raise
      logging.warning('Failed to get firmware updater from release image',
                      exc_info=1)
      release_firmware_updater = None

    # The 'vmlinuz' may be in netboot/ folder (factory zip style) or
    # netboot/tftp/chrome-bot/$BOARD/vmlinuz (factory bundle style).
    netboot_vmlinuz = None
    has_tftp = False
    if self.netboot:
      netboot_vmlinuz = os.path.join(self.netboot, 'vmlinuz')
      if not os.path.exists(netboot_vmlinuz):
        netboot_vmlinuz = os.path.join(
            self.netboot, 'tftp', 'chrome-bot', self.board, 'vmlinuz')
        has_tftp = True

    readme_path = os.path.join(bundle_dir, 'README.md')
    with open(readme_path, 'w') as f:
      fw_ver = self.GetFirmwareUpdaterVersion(self.firmware)
      fsi_fw_ver = self.GetFirmwareUpdaterVersion(release_firmware_updater)
      info = [
          ('Board', self.board),
          ('Bundle', '%s (created by %s)' % (
              bundle_name, os.environ.get('USER', 'unknown'))),
          ('Factory toolkit', self.GetToolkitVersion()),
          ('Test image', self.GetImageVersion(self.test_image)),
          ('Factory shim', self.GetImageVersion(self.factory_shim)),
          ('AP firmware', FormatFirmwareVersion(fw_ver.get('main'))),
          ('EC firmware', FormatFirmwareVersion(fw_ver.get('ec'))),
          ('Release (FSI)', self.GetImageVersion(self.release_image)),
      ]
      if fsi_fw_ver != fw_ver:
        info += [
            ('FSI AP firmware', FormatFirmwareVersion(fsi_fw_ver.get('main'))),
            ('FSI EC firmware', FormatFirmwareVersion(fsi_fw_ver.get('ec')))]
      if self.netboot:
        info += [
            ('Netboot firmware', FormatFirmwareVersion(self.GetFirmwareVersion(
                os.path.join(self.netboot, 'image.net.bin')))),
            ('Netboot kernel', self.GetKernelVersion(netboot_vmlinuz))]
      info += [('Factory server URL', self.server_url or 'N/A')]
      key_len = max(len(k) for (k, v) in info)

      f.write(textwrap.dedent(
          '''\
          # Chrome OS Factory Bundle
          %s
          ## Additional Notes
          %s
          ''') % ('\n'.join('- %-*s%s' % (key_len + 2, k + ':', v)
                            for (k, v) in info), notes))
    Shell(['cat', readme_path])

    output_path = os.path.join(output_dir, output_name)
    AddResource('toolkit', self.toolkit)
    AddResource('release_image', self.release_image)
    AddResource('test_image', self.test_image)
    AddResource('firmware', self.firmware)
    AddResource('complete', self.complete)
    AddResource('hwid', self.hwid)

    if self.server_url:
      shim_path = AddResource('factory_shim', self.factory_shim, do_copy=True)
      with Partition(shim_path, PART_CROS_STATEFUL).Mount(rw=True) as stateful:
        logging.info('Patching factory_shim lsb-factory file...')
        lsb = LSBFile(os.path.join(stateful, 'dev_image', 'etc', 'lsb-factory'))
        lsb.SetValue('CHROMEOS_AUSERVER', self.server_url)
        lsb.SetValue('CHROMEOS_DEVSERVER', self.server_url)
        lsb.Install(lsb.GetPath())
    else:
      AddResource('factory_shim', self.factory_shim)

    if self.setup_dir:
      AddResource('setup', os.path.join(self.setup_dir, '*'))
    if self.netboot:
      self.CreateDirectory(os.path.join(bundle_dir, 'netboot'))
      self.CreateNetbootFirmware(
          os.path.join(self.netboot, 'image.net.bin'),
          os.path.join(bundle_dir, 'netboot', 'image.net.bin'))
      if has_tftp:
        AddResource('netboot', os.path.join(self.netboot, 'tftp'))
      else:
        AddResource('netboot/tftp/chrome-bot/%s' % self.board, netboot_vmlinuz)
        self.GenerateTFTP(os.path.join(bundle_dir, 'netboot', 'tftp'))

    Shell(['tar', '-I', SysUtils.FindBZip2(), '-chvf', output_path,
           '-C', bundle_dir, '.'])
    # Print final results again since tar may have flood screen output.
    Shell(['cat', readme_path])
    return output_path


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
  aliases = []  # Overridden by subclass

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


class GPTCommand(SubCommand):
  """Access GPT (GUID Partition Table) with `cgpt` style commands."""
  name = 'gpt'
  aliases = ['pygpt', 'cgpt']
  gpt = None

  def Init(self):
    self.gpt = pygpt.GPTCommands()
    self.gpt.DefineArgs(self.subparser)

  def Run(self):
    self.gpt.Execute(self.args)


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
    ChromeOSFactoryBundle.DefineBundleArguments(
        self.subparser, ChromeOSFactoryBundle.PREFLASH)
    self.subparser.add_argument(
        '--sectors', type=int, default=31277232,
        help=('size of image in sectors (see --sector-size). '
              'default: %(default)s'))
    self.subparser.add_argument(
        '--sector-size', type=int, default=DEFAULT_BLOCK_SIZE,
        help='size of each sector. default: %(default)s')
    self.subparser.add_argument(
        '--stateful_free_space', type=int, default=1024,
        help=('extra space to claim in stateful partition in MB. '
              'default: %(default)s'))
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
          enable_firmware=False,
          hwid=self.args.hwid,
          complete=None)
      new_size = bundle.CreateDiskImage(
          self.args.output, self.args.sectors, self.args.sector_size,
          self.args.stateful_free_space, self.args.verbose)
    print('OK: Generated pre-flash disk image at %s [%s G]' % (
        self.args.output, new_size / GIGABYTE_STORAGE))


class CreateRMAImageCommmand(SubCommand):
  """Create an RMA image for factory to boot from USB and repair device.

  The output is a special factory install shim (factory_install) with all
  resources (release, test images and toolkit). The manufacturing line or RMA
  centers can boot it from USB and install all factory software bits into
  a device.
  """
  name = 'rma-create'
  aliases = ['rma']

  def Init(self):
    ChromeOSFactoryBundle.DefineBundleArguments(
        self.subparser, ChromeOSFactoryBundle.RMA)
    self.subparser.add_argument(
        '--active_test_list', default=None,
        help='active test list')
    self.subparser.add_argument(
        '-f', '--force', action='store_true',
        help='Overwrite existing output image file.')
    self.subparser.add_argument(
        '-o', '--output', required=True,
        help='path to the output RMA image file')

  def Run(self):
    output = self.args.output
    if os.path.exists(output) and not self.args.force:
      raise RuntimeError(
          'Output already exists (add -f to overwrite): %s' % output)

    with SysUtils.TempDirectory(prefix='rma_') as temp_dir:
      bundle = ChromeOSFactoryBundle(
          temp_dir=temp_dir,
          board=self.args.board,
          release_image=self.args.release_image,
          test_image=self.args.test_image,
          toolkit=self.args.toolkit,
          factory_shim=self.args.factory_shim,
          enable_firmware=self.args.enable_firmware,
          firmware=self.args.firmware,
          hwid=self.args.hwid,
          complete=self.args.complete,
          toolkit_config=self.args.toolkit_config)
      bundle.CreateRMAImage(self.args.output, self.args.active_test_list)
      bundle.ShowRMAImage(output)
      print('OK: Generated %s RMA image at %s' %
            (bundle.board, self.args.output))


class MergeRMAImageCommand(SubCommand):
  """Merge multiple RMA images into one single large image."""
  name = 'rma-merge'
  aliases = ['merge_rma']

  def Init(self):
    self.subparser.add_argument(
        '-f', '--force', action='store_true',
        help='Overwrite existing output image file.')
    self.subparser.add_argument(
        '-o', '--output', required=True,
        help='Path to the merged output image.')
    self.subparser.add_argument(
        '-i', '--images', required=True, nargs='+',
        type=ArgTypes.ExistsPath,
        help='Path to input RMA images')
    self.subparser.add_argument(
        '-a', '--auto_select', action='store_true',
        help='Automatically resolve duplicate boards (use the first one).')


  def Run(self):
    """Merge multiple RMA (USB installation) disk images.

    The RMA images should be created by 'image_tool rma' command, with different
    board names.
    """
    output = self.args.output
    if os.path.exists(output) and not self.args.force:
      raise RuntimeError(
          'Output already exists (add -f to overwrite): %s' % output)
    if len(self.args.images) < 2:
      raise RuntimeError('Need > 1 input image files to merge.')

    print('Scanning %s input image files...' % len(self.args.images))
    ChromeOSFactoryBundle.MergeRMAImage(
        self.args.output, self.args.images, self.args.auto_select)
    ChromeOSFactoryBundle.ShowRMAImage(output)
    print('OK: Merged successfully in new image: %s' % output)

class ExtractRMAImageCommand(SubCommand):
  """Extract an RMA image from a universal RMA image."""
  name = 'rma-extract'
  aliases = ['extract_rma']

  def Init(self):
    self.subparser.add_argument(
        '-f', '--force', action='store_true',
        help='Overwrite existing output image file.')
    self.subparser.add_argument(
        '-o', '--output', required=True,
        help='Path to the merged output image.')
    self.subparser.add_argument(
        '-i', '--image', required=True,
        type=ArgTypes.ExistsPath,
        help='Path to input RMA image.')
    self.subparser.add_argument(
        '-s', '--select', default=None,
        help='Select the SELECT-th board in the shim to extract.')

  def Run(self):
    """Extract RMA (USB installation) disk image from a universal RMA image.

    The RMA image should be created by 'image_tool rma-create' or
    'image_tool rma-merge' command.
    """
    output = self.args.output
    if os.path.exists(output) and not self.args.force:
      raise RuntimeError(
          'Output already exists (add -f to overwrite): %s' % output)

    print('Scanning input image file...')
    ChromeOSFactoryBundle.ExtractRMAImage(
        self.args.output, self.args.image, self.args.select)
    ChromeOSFactoryBundle.ShowRMAImage(output)
    print('OK: Extracted successfully in new image: %s' % output)

class ShowRMAImageCommand(SubCommand):
  """Show the content of a RMA image."""
  name = 'rma-show'

  def Init(self):
    self.subparser.add_argument(
        'image', type=ArgTypes.ExistsPath,
        help='Path to input RMA image.')

  def Run(self):
    ChromeOSFactoryBundle.ShowRMAImage(self.args.image)


class ReplaceRMAPayloadCommand(SubCommand):
  """Replace payloads in an RMA shim."""
  name = 'rma-replace'
  aliases = ['replace_rma']

  def Init(self):
    ChromeOSFactoryBundle.DefineBundleArguments(
        self.subparser, ChromeOSFactoryBundle.REPLACEABLE)
    self.subparser.add_argument(
        '-i', '--image', required=True,
        type=ArgTypes.ExistsPath,
        help='Path to input RMA image.')

  def Run(self):
    ChromeOSFactoryBundle.ReplaceRMAPayload(
        self.args.image,
        board=self.args.board,
        release_image=self.args.release_image,
        test_image=self.args.test_image,
        toolkit=self.args.toolkit,
        firmware=self.args.firmware,
        hwid=self.args.hwid,
        complete=self.args.complete,
        toolkit_config=self.args.toolkit_config)
    ChromeOSFactoryBundle.ShowRMAImage(self.args.image)
    print('OK: Replaced payloads successfully in image: %s' % self.args.image)


class CreateBundleCommand(SubCommand):
  """Creates a factory bundle from given arguments."""
  name = 'bundle'

  def Init(self):
    ChromeOSFactoryBundle.DefineBundleArguments(
        self.subparser, ChromeOSFactoryBundle.BUNDLE)
    self.subparser.add_argument(
        '-o', '--output_dir', default='.',
        help='directory for the output factory bundle file')
    self.subparser.add_argument(
        '--timestamp',
        help='override the timestamp field in output file name')
    self.subparser.add_argument(
        '-n', '--notes',
        help='additional notes or comments for bundle release')

  def Run(self):
    with SysUtils.TempDirectory(prefix='bundle_') as temp_dir:
      bundle = ChromeOSFactoryBundle(
          temp_dir=temp_dir,
          board=self.args.board,
          release_image=self.args.release_image,
          test_image=self.args.test_image,
          toolkit=self.args.toolkit,
          factory_shim=self.args.factory_shim,
          enable_firmware=self.args.enable_firmware,
          firmware=self.args.firmware,
          hwid=self.args.hwid,
          complete=self.args.complete,
          netboot=self.args.netboot,
          setup_dir=self.args.setup_dir,
          server_url=self.args.server_url)
      output_file = bundle.CreateBundle(
          self.args.output_dir, self.args.phase, self.args.notes,
          timestamp=self.args.timestamp)
      print('OK: Created %s factory bundle: %s' % (bundle.board, output_file))


class CreateDockerImageCommand(SubCommand):
  """Create a Docker image from existing Chromium OS disk image.

  The architecture of the source Chromium OS disk image should be the same as
  the docker host (basically, amd64).
  """
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


class InstallChromiumOSImageCommand(SubCommand):
  """Installs a Chromium OS disk image into inactive partition.

  This command takes a Chromium OS (USB) disk image, installs into current
  device (should be a Chromium OS device) and switches boot records to try
  the newly installed kernel.
  """
  name = 'install'

  def Init(self):
    self.subparser.add_argument(
        '-i', '--image', type=ArgTypes.ExistsPath, required=True,
        help='path to a Chromium OS disk image or USB stick device')
    self.subparser.add_argument(
        '-o', '--output', type=ArgTypes.ExistsPath, required=False,
        help=('install to given path of a disk image or USB stick device; '
              'default to boot disk'))
    self.subparser.add_argument(
        '-x', '--exclude', type=str, default='dev_image/telemetry/*',
        help='pattern to tar --exclude when copying stateful partition.')
    self.subparser.add_argument(
        '--no-stateful-partition', dest='do_stateful', action='store_false',
        default=True,
        help='skip copying stateful partition')
    self.subparser.add_argument(
        '-p', '--partition_number', type=int, required=False,
        help=('kernel partition number to install (rootfs will be +1); '
              'default to %s or %s if active kernel is %s.' % (
                  PART_CROS_KERNEL_A, PART_CROS_KERNEL_B,
                  PART_CROS_KERNEL_A)))

  def Run(self):
    # TODO(hungte) Auto-detect by finding removable and fixed storage for from
    # and to.
    from_image = self.args.image
    to_image = self.args.output
    arg_part = self.args.partition_number
    exclude = self.args.exclude
    to_part = arg_part if arg_part is not None else PART_CROS_KERNEL_A

    if to_image is None:
      to_image = SudoOutput('rootdev -s -d').strip()
    is_block = GPT.IsBlockDevice(to_image)

    if is_block:
      # to_part refers to kernel but rootdev -s refers to rootfs.
      to_rootfs = MakePartition(to_image, to_part + 1)
      if to_rootfs == SudoOutput('rootdev -s').strip():
        if arg_part is not None:
          raise RuntimeError(
              'Cannot install to active partition %s' % to_rootfs)
        known_kernels = [PART_CROS_KERNEL_A, PART_CROS_KERNEL_B]
        if to_part not in known_kernels:
          raise RuntimeError(
              'Unsupported kernel destination for %s' % to_rootfs)
        to_part = known_kernels[1 - known_kernels.index(to_part)]

    # Ready to install!
    gpt_from = GPT.LoadFromFile(from_image)
    gpt_to = GPT.LoadFromFile(to_image)

    # On USB stick images, kernel A is signed by recovery key and B is signed by
    # normal key, so we have to choose B when installed to disk.
    print('Installing [%s] to [%s#%s]...' % (from_image, to_image, to_part))
    gpt_from.GetPartition(PART_CROS_KERNEL_B).Copy(
        gpt_to.GetPartition(to_part), sync=is_block, verbose=True)
    gpt_from.GetPartition(PART_CROS_ROOTFS_A).Copy(
        gpt_to.GetPartition(to_part + 1),
        check_equal=False, sync=is_block, verbose=True)

    # Now, prioritize and make kernel A bootable.
    # TODO(hungte) Check if kernel key is valid.
    pri_cmd = pygpt.GPTCommands.Prioritize()
    pri_cmd.ExecuteCommandLine('-i', str(to_part), to_image)

    # People may try to abort if installing stateful partition takes too much
    # time, so we do want to sync now (for partition changes to commit).
    print('Syncing...')
    Shell('sync')

    # Call 'which' directly to avoid error messages by FindCommand.
    pv = SysUtils.Shell('which pv 2>/dev/null || echo cat', output=True).strip()

    # TODO(hungte) Do partition copy if stateful in to_image is not mounted.
    # Mount and copy files in stateful partition.
    # Note stateful may not support mount with rw=False.
    with gpt_from.GetPartition(PART_CROS_STATEFUL).Mount(rw=True) as from_dir:
      dev_image_from = os.path.join(from_dir, 'dev_image')
      if self.args.do_stateful and os.path.exists(dev_image_from):
        print('Copying stateful partition...')
        with gpt_to.GetPartition(PART_CROS_STATEFUL).Mount(rw=True) as to_dir:
          dev_image_old = os.path.join(to_dir, 'dev_image.old')
          dev_image_to = os.path.join(to_dir, 'dev_image')
          if os.path.exists(dev_image_old):
            logging.warn('Removing %s...', dev_image_old)
            Sudo(['rm', '-rf', dev_image_old])
          if os.path.exists(dev_image_to):
            Sudo(['mv', dev_image_to, dev_image_old])
          # Use sudo instead of shutil.copytree sine people may invoke this
          # command with user permission (which works for copying partitions).
          # SysUtils.Sudo does not support pipe yet so we have to add 'sh -c'.
          Sudo(['sh', '-c', 'tar -C %s -cf - dev_image | %s | '
                'tar -C %s --warning=none --exclude="%s" -xf -' %
                (from_dir, pv, to_dir, exclude)])

    print('OK: Successfully installed image from [%s] to [%s].' %
          (from_image, to_image))


class EditLSBCommand(SubCommand):
  """Edit contents of 'lsb-factory' file from a factory_install image."""
  name = 'edit_lsb'

  old_data = ''
  lsb = None

  def Init(self):
    self.subparser.add_argument(
        '-i', '--image', type=ArgTypes.ExistsPath, required=True,
        help='Path to the factory_install image.')

  def _DoURL(self, title, keys, default_port=8080, suffix=''):
    host = raw_input('Enter %s host: ' % title).strip()
    if not host:
      return
    port = raw_input('Enter port (default=%s): ' % default_port).strip()
    if not port:
      port = str(default_port)
    url = 'http://%s:%s%s' % (host, port, suffix)
    for key in keys:
      self.lsb.SetValue(key, url)

  def _DoOptions(self, title, key, options):
    print('%s (%s):' % (title, key))
    for i, value in enumerate(options):
      print('(%s) %s' % (i + 1, value))
    while True:
      answer = raw_input(
          'Please select an option [1-%d]: ' % len(options)).strip().lower()
      try:
        selected = int(answer)
        if not 0 < selected <= len(options):
          raise ValueError('out of range')
      except ValueError:
        print('Invalid option: %s' % answer)
        continue
      break
    new_value = options[selected - 1]
    self.lsb.SetValue(key, new_value)
    return new_value

  def _DoOptionalNumber(self, title, key, min_value, max_value):
    print('%s (%s): ' % (title, key))
    while True:
      prompt = 'Enter a number%s or empty to remove this setting: ' % (
          '' if min_value is None else (
              ' in [%s, %s]' % (min_value, max_value)))
      answer = raw_input(prompt).strip()
      if not answer:
        self.lsb.DeleteValue(key)
        return None
      try:
        selected = int(answer)
        if min_value is not None and not min_value <= selected <= max_value:
          raise ValueError('out of range')
      except ValueError:
        print('Invalid option: %s' % answer)
        continue
      break
    self.lsb.SetValue(key, str(selected))
    return selected

  def EditServerAddress(self):
    """Modify Chrome OS Factory Server address."""
    self._DoURL(
        'Chrome OS Factory Server', ['CHROMEOS_AUSERVER', 'CHROMEOS_DEVSERVER'],
        suffix='/update')

  def EditBoardPrompt(self):
    """Enable/disable board prompt on download."""
    answer = raw_input(
        'Enable (y) or disable (n) board prompt? ').strip().lower()
    while not answer in ['y', 'n']:
      answer = raw_input('Please input "y" or "n": ').strip().lower()
    self.lsb.SetValue('USER_SELECT', 'true' if answer == 'y' else 'false')

  def EditCutOff(self):
    """Modify cutoff method after factory reset.

    All options are defined in src/platform/factory/sh/cutoff/options.sh
    """
    answer = self._DoOptions(
        'Select cutoff method after factory reset', 'CUTOFF_METHOD',
        ['shutdown', 'reboot', 'battery_cutoff', 'ectool_cutoff'])
    if not answer.endswith('cutoff'):
      return
    answer = self._DoOptions(
        'Select cutoff AC state', 'CUTOFF_AC_STATE',
        ['remove_ac', 'connect_ac'])
    answer = self._DoOptionalNumber(
        'Minimum allowed battery percentage', 'CUTOFF_BATTERY_MIN_PERCENTAGE',
        0, 100)
    self._DoOptionalNumber(
        'Maximum allowed battery percentage', 'CUTOFF_BATTERY_MAX_PERCENTAGE',
        0 if answer is None else answer, 100)
    self._DoOptionalNumber(
        'Minimum allowed battery voltage (mA)', 'CUTOFF_BATTERY_MIN_VOLTAGE',
        None, None)
    self._DoOptionalNumber(
        'Maximum allowed battery voltage (mA)', 'CUTOFF_BATTERY_MAX_VOLTAGE',
        None, None)
    self._DoURL(
        'Chrome OS Factory Server or Shopfloor Service for OQC ReFinalize',
        ['SHOPFLOOR_URL'])

  def EditRMAAutorun(self):
    """Enable/disable autorun in RMA shim.

    If RMA autorun is set, automatically do RSU (RMA Server Unlock) or install,
    depending on HWWP status.
    """
    answer = raw_input(
        'Enable (y) or disable (n) autorun in RMA? ').strip().lower()
    while not answer in ['y', 'n']:
      answer = raw_input('Please input "y" or "n": ').strip().lower()
    self.lsb.SetValue('RMA_AUTORUN', 'true' if answer == 'y' else 'false')

  def DoMenu(self, *args, **kargs):
    redo_options = True

    while True:
      if redo_options:
        print('=' * 72)
        print(self.lsb.AsRawData())
        print('-' * 72)
        for i, arg in enumerate(args):
          print('(%d) %s' % (i + 1, arg.__doc__.splitlines()[0]))
        for k, v in kargs.iteritems():
          print('(%s) %s' % (k, v.__doc__.splitlines()[0]))
        print('=' * 72)
        redo_options = False

      answer = raw_input('Please select an option: ').strip().lower()
      if answer.isdigit():
        answer = int(answer)
        if not 1 <= answer <= len(args):
          print('Invalid option [%s].' % answer)
          continue
        selected = args[answer - 1]
      elif answer not in kargs:
        print('Invalid option [%s].' % answer)
        continue
      else:
        selected = kargs.get(answer)

      if selected():
        return
      redo_options = True

  def Write(self):
    """Apply changes and exit."""
    if self.old_data == self.lsb.AsRawData():
      print('QUIT. No modifications.')
    else:
      self.lsb.Install(self.lsb.GetPath(), backup=True)
      print('DONE. All changes saved properly.')
    return True

  def Quit(self):
    """Quit without saving changes."""
    print('QUIT. No changes were applied.')
    return True

  def Run(self):
    lsb_file = os.path.join('dev_image', 'etc', 'lsb-factory')
    with Partition(self.args.image, PART_CROS_STATEFUL).Mount(rw=True) as state:
      src_file = os.path.join(state, lsb_file)
      if not os.path.exists(src_file):
        raise RuntimeError(
            'No %s file in disks image: %s. Please make sure you have '
            'specified a factory_install image.' % (lsb_file, self.args.image))
      self.lsb = LSBFile(src_file)
      self.old_data = self.lsb.AsRawData()
      self.DoMenu(self.EditServerAddress,
                  self.EditBoardPrompt,
                  self.EditCutOff,
                  self.EditRMAAutorun,
                  w=self.Write,
                  q=self.Quit)


def main():
  # Support `cros_payload` in bin/ folder, so that we can run
  # `py/tools/image_tool.py` directly.
  new_path = os.path.realpath(os.path.join(
      os.path.dirname(os.path.realpath(__file__)), '..', '..', 'bin'))
  os.putenv('PATH', ':'.join(os.getenv('PATH', '').split(':') + [new_path]))
  sys.path.append(new_path)

  parser = argparse.ArgumentParser(
      prog='image_tool',
      description=(
          'Tools to manipulate Chromium OS disk images for factory. '
          'Use "image_tool help COMMAND" for more info on a '
          'subcommand.'))
  parser.add_argument('--verbose', '-v', action='count', default=0,
                      help='Verbose output')
  subparsers = parser.add_subparsers(title='subcommands')

  verb = sys.argv[1] if (len(sys.argv) > 1) else None

  selected_command = None
  for unused_key, v in sorted(globals().items()):
    if v != SubCommand and inspect.isclass(v) and issubclass(v, SubCommand):
      subcommand = v(parser, subparsers)
      subcommand.Init()
      if verb in subcommand.aliases:
        selected_command = subcommand.name

  if selected_command:
    args = parser.parse_args([selected_command] + sys.argv[2:])
  else:
    args = parser.parse_args()
  logging.basicConfig(level=logging.WARNING - args.verbose * 10)

  args.subcommand.args = args
  args.subcommand.Run()


if __name__ == '__main__':
  main()
