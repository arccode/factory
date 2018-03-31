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
# Regular expression for reading file system information from dumpe2fs.
RE_BLOCK_COUNT = re.compile(r'^Block count: *(.*)$', re.MULTILINE)
RE_BLOCK_SIZE = re.compile(r'^Block size: *(.*)$', re.MULTILINE)
# Simple constant(s)
MEGABYTE = 1048576


class ArgTypes(object):
  """Helper class to collect all argument type checkers."""

  @staticmethod
  def ExistsPath(path):
    """An argument with existing path."""
    if not os.path.exists(path):
      raise argparse.ArgumentTypeError('Does not exist: %s' % path)
    return path


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

  @contextlib.contextmanager
  def Map(self):
    """Context manager to map (using losetup) partition from disk image."""
    loop_dev = None
    logging.debug('Map %s: %s(+%s)', self, self.offset, self.size)
    try:
      loop_dev = SudoOutput(
          ['losetup', '--show', '--find', '-o', str(self.offset),
           '--sizelimit', str(self.size), self.image]).strip()
      yield loop_dev
    finally:
      if loop_dev:
        Sudo(['umount', '-R', loop_dev], check=False, silent=True)
        Sudo(['losetup', '-d', loop_dev], check=False, silent=True)

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
