# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utils to get various representations of a ChromeOS board name."""

import logging
import os
import re
import subprocess

from six import iteritems

from . import process_utils
from . import sys_utils
from . import type_utils


def GetChromeOSFactoryBoardPath(board):
  # The packages here must be in same order as defined in
  # virtual/chromeos-bsp-factory.
  package_names = ['factory-board', 'chromeos-factory-board']
  for package in package_names:
    try:
      ebuild_path = process_utils.SpawnOutput(
          ['equery-%s' % board, 'which', package])
    except OSError:
      logging.error('Fail to execute equery-%s. Try to run inside chroot'
                    ' and do "setup_board --board %s" first.', board, board)
      return None
    if ebuild_path:
      files_dir = os.path.join(os.path.dirname(ebuild_path), 'files')
      # Some packages, for example the fallback one in chromiumos-overlay,
      # may not have 'files' so we have to check again.
      if os.path.exists(files_dir):
        return files_dir
    logging.warning('no ebuild [%s] for board [%s].', package, board)
  logging.warning('cannot find any board packages for board [%s].', board)
  return None


class BuildBoardException(Exception):
  """Build board exception."""
  pass


class BuildBoard(object):
  """A board that we build CrOS for.

  Properties:
    arch: The architecture of the board, or None if unable to determine
      architecture.
    base: The base name.  Always set.
    variant: The variant name, or None if there is no variant.
    full_name: The base name, plus '_'+variant if set.  This is
      the name used for build directories, like "/build/daisy_spring").
    short_name: The variant if set; else the base.  This is the
      name used in branches (like "spring" in factory-spring-1234.B).
    gsutil_name: The base name, plus '-'+variant if set.  GSUtil uses
      'base-variant' as bucket names.
    factory_board_files: A folder to FILESDIR in factory board package
      (chromeos-factory-board or factory-board). This is available only
      when the module is invoked in chroot.
  """

  def __init__(self, board_name=None):
    """Constructor.

    Args:
      board_name: The name of a board.  This may be one of:

        "None" or "default": If runs in chroot, uses the user's default
          board in $HOME/src/scripts/.default_board (or fails if there is
          none).  Otherwise tries to find out the board name from
          /etc/lsb-release (or fails if the file does not exist).

        "foo": Uses the foo board.  If runs in chroot, it can also handle
          the case where "foo" is a variant (e.g., use "spring" to mean
          "daisy_spring").

        "base_foo": Uses the "foo" variant of the "base" board.

    Raises:
      BuildBoardException if unable to determine board or overlay name.
    """
    self.board_name = board_name
    if sys_utils.InChroot():
      # The following sanity checks are feasible only in chroot.
      src = os.path.join(os.environ['CROS_WORKON_SRCROOT'], 'src')
      if board_name in [None, 'default']:
        default_path = os.path.join(src, 'scripts', '.default_board')
        if not os.path.exists(default_path):
          raise BuildBoardException('Unable to read default board from %s' %
                                    default_path)
        board_name = open(default_path).read().strip()

      # Grok cros-board.eclass to find the set of all boards.
      # May the gods forgive me.
      eclass_path = os.path.join(
          src, 'third_party', 'chromiumos-overlay', 'eclass',
          'cros-board.eclass')
      eclass_contents = open(eclass_path).read()
      pattern = r'(?s)ALL_BOARDS=\((.+?)\)'
      match = re.search(pattern, eclass_contents)
      if not match:
        raise BuildBoardException('Unable to read pattern %s in %s' %
                                  (pattern, eclass_path))
      boards = match.group(1).split()

      self.full_name = None
      board_name = board_name.lower()
      if board_name in boards:
        self.full_name = board_name

      # User said "daisy-spring" but means "daisy_spring"?
      if not self.full_name:
        try_board_name = board_name.replace('-', '_')
        if try_board_name in boards:
          self.full_name = try_board_name

      # User said "spring" but means "daisy_spring"?
      if not self.full_name:
        try_board_names = [x for x in boards
                           if x.endswith('_' + board_name)]
        if len(try_board_names) > 1:
          raise BuildBoardException('Multiple board names %s match %r' %
                                    (try_board_names, board_name))
        if try_board_names:
          self.full_name = try_board_names[0]

      if not self.full_name:
        # Oh well, we tried
        raise BuildBoardException('Unknown board %r' % board_name)
    else:
      if board_name in [None, 'default']:
        # See if we can get the board name from /etc/lsb-release.
        LSB_RELEASE_FILE = '/etc/lsb-release'
        LSB_BOARD_RE = re.compile(r'^CHROMEOS_RELEASE_BOARD=(\w+)$', re.M)
        if not os.path.exists(LSB_RELEASE_FILE):
          raise BuildBoardException(
              'Not in chroot and %r does not exist, unable to determine board' %
              LSB_RELEASE_FILE)
        try:
          with open(LSB_RELEASE_FILE) as f:
            self.full_name = LSB_BOARD_RE.findall(f.read())[0].lower()
        except IndexError:
          raise BuildBoardException(
              'Cannot determine board from %r' % LSB_RELEASE_FILE)
      else:
        self.full_name = re.sub('-', '_', board_name).lower()

    self.base, _, self.variant = self.full_name.partition('_')
    self.variant = self.variant or None  # Use None, not ''
    self.short_name = self.variant or self.base  # Ick
    self.gsutil_name = re.sub('_', '-', self.full_name)

  @type_utils.LazyProperty
  def factory_board_files(self):
    return (GetChromeOSFactoryBoardPath(self.full_name) if sys_utils.InChroot()
            else None)

  @type_utils.LazyProperty
  def arch(self):
    if sys_utils.InChroot():
      if os.environ.get('ROOT'):
        # Skip if ROOT env var is set as crossdev does not work with it. This
        # can happen while running 'emerge-<board>'. Extract arch from
        # 'emerge-<board> --info' instead.
        try:
          emerge_info = process_utils.CheckOutput(
              ['emerge-%s' % self.full_name, '--info'])
          return re.search(r'^ACCEPT_KEYWORDS="(.*)"$', emerge_info,
                           re.MULTILINE).group(1)
        except subprocess.CalledProcessError:
          return None
      else:
        # Try to determine arch through toolchain.
        chromite = os.path.join(os.environ['CROS_WORKON_SRCROOT'], 'chromite')
        toolchain = process_utils.CheckOutput(
            [os.path.join(chromite, 'bin', 'cros_setup_toolchains'),
             '--show-board-cfg=%s' % self.full_name]).split(',')[0].strip()
        target_cfg = process_utils.CheckOutput(
            ['/usr/bin/crossdev', '--show-target-cfg', toolchain])
        arch = re.search(r'^arch=(.*)$', target_cfg, re.MULTILINE).group(1)
        return arch if arch != '*' else None
    else:
      if self.board_name not in [None, 'default']:
        return None
      # Try to determine arch from 'uname -m'.
      uname_machine = process_utils.CheckOutput(['uname', '-m'])
      # Translate the output from 'uname -m' to match the arch definition in
      # chroot.
      machine_arch_map = {
          'x86_64': 'amd64',
          'arm': 'arm',
          'aarch64': 'arm64'
      }
      for key, value in iteritems(machine_arch_map):
        if uname_machine.startswith(key):
          return value
      return None
