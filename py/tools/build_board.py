# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import os
import re


import factory_common  # pylint: disable=W0611


class BuildBoardException(Exception):
  pass


class BuildBoard(object):
  """A board that we build CrOS for.

  Properties:
    base: The base name.  Always set.
    variant: The variant name, or None if there is no variant.
    full_name: The base name, plus '_'+variant if set.  This is
      the name used for build directories, like "/build/daisy_spring").
    short_name: The variant if set; else the base.  This is the
      name used in branches (like "spring" in factory-spring-1234.B).
    overlay: Relative patch the overlay within the source root
      (like "overlays/overlay-variant-tegra2-dev-board" for
      "tegra2_dev-board").
  """
  def __init__(self, board_name=None):
    """Constructor.

    Args:
      board_name: The name of a board.  This may be one of:

        "None" or "default": Uses the user's default board in
          $HOME/src/scripts/.default_board (or fails if there is
          none).
        "foo": Uses the foo board.  Can also handle the case
          where "foo" is a variant (e.g., use "spring" to mean
          "daisy_spring").
        "base_foo".  Uses the "foo" variant of the "base" board.
    """
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
        src, 'third_party', 'chromiumos-overlay', 'eclass', 'cros-board.eclass')
    eclass_contents = open(eclass_path).read()
    pattern = "(?s)ALL_BOARDS=\((.+?)\)"
    match = re.search(pattern, eclass_contents)
    if not match:
      raise BuildBoardException('Unable to read pattern %s in %s',
                                pattern, eclass_path)
    boards = match.group(1).split()

    self.full_name = None
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

    self.base, _, self.variant = self.full_name.partition('_')
    self.variant = self.variant or None  # Use None, not ''
    self.short_name = self.variant or self.base  # Ick

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


if __name__ == '__main__':
  BuildBoard()
