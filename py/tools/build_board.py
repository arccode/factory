# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tools to get variaous representations of a board name."""

import os
import re
import subprocess

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.utils import process_utils


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
    overlay_relpath: Relative patch the overlay within the source root
      (like "overlays/overlay-variant-tegra2-dev-board" for
      "tegra2_dev-board").  This is available only when this module is
      invoked in chroot.
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
    if utils.in_chroot():
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
      pattern = "(?s)ALL_BOARDS=\((.+?)\)"
      match = re.search(pattern, eclass_contents)
      if not match:
        raise BuildBoardException('Unable to read pattern %s in %s',
                                  pattern, eclass_path)
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

      if os.environ.get('ROOT'):
        # Skip if ROOT env var is set as crossdev does not work with it. This
        # can happen while running 'emerge-<board>'. Extract arch from
        # 'emerge-<board> --info' instead.
        try:
          emerge_info = process_utils.CheckOutput(
              ['emerge-%s' % self.full_name, '--info'])
          self.arch = re.search(r'^ACCEPT_KEYWORDS="(.*)"$', emerge_info,
                                re.MULTILINE).group(1)
        except subprocess.CalledProcessError:
          self.arch = None
      else:
        # Try to determine arch through toolchain.
        chromite = os.path.join(os.environ['CROS_WORKON_SRCROOT'], 'chromite')
        toolchain = process_utils.CheckOutput(
            [os.path.join(chromite, 'bin', 'cros_setup_toolchains'),
             '--show-board-cfg=%s' % self.full_name]).split(',')[0].strip()
        target_cfg = process_utils.CheckOutput(
                    ['/usr/bin/crossdev', '--show-target-cfg', toolchain])
        self.arch = re.search(r'^arch=(.*)$', target_cfg, re.MULTILINE).group(1)
        if self.arch == '*':
          self.arch = None
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

        # Try to determine arch from 'uname -m'.
        self.arch = None
        uname_machine = process_utils.CheckOutput(['uname', '-m'])
        # Translate the output from 'uname -m' to match the arch definition in
        # chroot.
        machine_arch_map = {
            'x86_64': 'amd64',
            'arm': 'arm',
        }
        for key, value in machine_arch_map.iteritems():
          if uname_machine.startswith(key):
            self.arch = value
            break
      else:
        self.full_name = re.sub('-', '_', board_name).lower()
        self.arch = None

    self.base, _, self.variant = self.full_name.partition('_')
    self.variant = self.variant or None  # Use None, not ''
    self.short_name = self.variant or self.base  # Ick
    self.gsutil_name = re.sub('_', '-', self.full_name)

    if utils.in_chroot():
      # Only get overlay relative path in chroot.
      if self.variant:
        overlay = 'overlay-variant-%s-%s' % (self.base, self.variant)
      else:
        overlay = 'overlay-%s' % self.base

      try_overlays = ['private-overlays/%s-private' % overlay,
                      'overlays/%s' % overlay]
      overlay_paths = [os.path.join(src, d) for d in try_overlays]
      existing_overlays = filter(os.path.exists, overlay_paths)
      if not existing_overlays:
        raise BuildBoardException('Unable to find overlay for board %s at %s' %
                                  (self.full_name, overlay_paths))
      self.overlay_relpath = os.path.relpath(existing_overlays[0], src)
    else:
      self.overlay_relpath = None


if __name__ == '__main__':
  BuildBoard()
