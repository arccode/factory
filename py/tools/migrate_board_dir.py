#!/usr/bin/env python2
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import argparse
from collections import namedtuple
from datetime import date
import os
import re
import shutil
import sys

import factory_common  # pylint: disable=unused-import
from cros.factory.utils.file_utils import UnopenedTemporaryFile


ReplacePattern = namedtuple('ReplacePattern',
                            ['old_substring', 'new_substring'])

DESCRIPTION = """Migrates a board-specific folder from one board to
another board. For example, copying factory-board folder
under one private overlay to another private overlay. It also renames
board-specific folder/file names and renames board-specific strings
in files.
"""

EXAMPLES = r"""Examples:
  1. Migrating factory-board folder from rambi private overlay
     to cranky private overlay:

     py/tools/migrate_board_dir.py \
         --src_board_name rambi \
         --dst_board_name cranky \
         --src_dir ~/trunk/src/private-overlays/overlay-rambi-private/\
chromeos-base/factory-board \
         --dst_dir ~/trunk/src/private-overlays/overlay-cranky-private/\
chromeos-base/factory-board \
         --reset_ebuild_file

  2. Migrating chromeos-bsp-rambi folder (for battery cutoff scripts) from
     rambi public overlay to cranky public overlay as chromeos-bsp-cranky:

     py/tools/migrate_board_dir.py \
         --src_board_name rambi \
         --dst_board_name cranky \
         --src_dir ~/trunk/src/overlays/overlay-rambi/chromeos-base/\
chromeos-bsp-rambi \
         --dst_dir ~/trunk/src/overlays/overlay-cranky/chromeos-base/\
chromeos-bsp-cranky \
         --reset_ebuild_file
"""


class MigrateBoardException(Exception):
  pass


def PrepareDirectoryCopy(src_dir, dst_dir,
                         in_stream=sys.stdin, out_stream=sys.stdout):
  """Checks that src_dir exists but dst_dir doesn't exist.

  If the dst_dir already exists, prompts a message showing that the
  directory will be deleted before copy. The user can select 'y' to
  proceed or 'n' to cancel the operation.

  Args:
    src_dir: The source directory to copy the files from.
    dst_dir: The destination directory to copy the files to.
    in_stream: a stream to read user input from.
    out_stream: a stream to write output messages to.
  """
  if not os.path.isdir(src_dir):
    out_stream.write('Source directory: %r not found.\n' % src_dir)
    sys.exit(1)

  if os.path.isdir(dst_dir):
    out_stream.write('dst_dir: %r already exists.\n'
                     'The folder will be deleted before copy.\n'
                     'Are you sure you want to proceed?\n'
                     'Press "y" to continue and press "n" to exit.\n' % dst_dir)
    while True:
      input_char = in_stream.readline().strip()
      if input_char == 'n':
        sys.exit(0)
      if input_char == 'y':
        shutil.rmtree(dst_dir)
        out_stream.write(
            'Directory: %r was removed before migration.\n' % dst_dir)
        break
      out_stream.write('Only accept input y/n.\n')


def CopyFilesAndRename(src_dir, dst_dir, rename_pattern, reset_ebuild_file):
  r"""Copies all files under src_dir to dst_dir.

  It will rename folder/file names based on the value in rename_pattern.
  For example, renaming rambi_shopfloor.py to cranky_shopfloor.py if the
  rename_pattern is ReplacePattern('rambi', 'cranky').

  It also changes the path name of a symlink. For example,
  change a symlink path from ../rambi_mock_shopfloor_backend.py
  to ../cranky_mock_shopfloor_backend.py.

  If will reset r\d+.ebuild files to r1.ebuild if reset_ebuild_file is True.

  Args:
    src_dir: The source directory to copy the files from.
    dst_dir: The destination directory to copy the files to.
    rename_pattern: A ReplacePattern tuple representing that the old substring
        in folder/file name will be replaced with the new substring.
    reset_ebuild_file: True for resetting *-r\d+.ebuild files to *-r1.ebuild.
  """
  names = os.listdir(src_dir)
  os.mkdir(dst_dir, os.stat(src_dir).st_mode)
  errors = []

  for name in names:
    src_name = os.path.join(src_dir, name)
    dst_name = os.path.join(dst_dir, name.replace(rename_pattern.old_substring,
                                                  rename_pattern.new_substring))
    # Resets ebuild version if necessary.
    if reset_ebuild_file and re.search(r'r\d+\.ebuild$', dst_name):
      dst_name = re.sub(r'r\d+\.ebuild$', 'r1.ebuild', dst_name)

    try:
      # Handles symlink file and rename the symlink path.
      if os.path.islink(src_name):
        target = os.readlink(src_name).replace(rename_pattern.old_substring,
                                               rename_pattern.new_substring)
        os.symlink(target, dst_name)
      elif os.path.isdir(src_name):
        CopyFilesAndRename(src_name, dst_name,
                           rename_pattern, reset_ebuild_file)
      else:
        shutil.copy2(src_name, dst_name)
    except (IOError, os.error) as why:
      errors.append((src_name, dst_name, str(why)))
    # Catch the Error from the recursive CopyFilesAndRename so that we can
    # continue with other files.
    except MigrateBoardException as err:
      errors.extend(err.args[0])

  try:
    shutil.copystat(src_dir, dst_dir)
  except OSError as why:
    errors.append((src_dir, dst_dir, str(why)))

  if errors:
    raise MigrateBoardException(errors)


def ReplaceStringInFiles(root_dir, replace_patterns):
  """Replaces strings based on replace_patterns for all files in root_dir.

  For example, renaminig string 'RambiBoard' to 'CrankyBoard' if there
  is a tuple ('Rambi', 'Cranky') in replace_patterns.

  Args:
    root_dir: The root directory containing files that we want to
        replace strings.
    replace_patterns: A list of ReplacePatterns (old_substring, new_substring)
        that we want to replace old_substring to new_substring in all files
        under the root_dir.
  """
  for dirpath, _, filenames in os.walk(root_dir):
    for filename in filenames:
      filepath = os.path.join(dirpath, filename)
      # No need to process the symlink because the target file will
      # be processed.
      if os.path.islink(filepath):
        continue
      with open(filepath, 'r') as old_file:
        with UnopenedTemporaryFile() as new_filepath:
          shutil.copystat(filepath, new_filepath)
          with open(new_filepath, 'w') as new_file:
            for line in old_file:
              for replace_pattern in replace_patterns:
                line = re.sub(replace_pattern.old_substring,
                              replace_pattern.new_substring,
                              line)
              new_file.write(line)
          shutil.move(new_filepath, filepath)


def GenerateReplacePatterns(src_board_name, dst_board_name):
  """Generates a list of ReplacePattern for string substitution in files.

  Args:
   src_board_name: The board name of source directory to copy the files from.
   dst_board_name: The board name of destination directory to copy the files to.

  Returns:
    A list of ReplacePatterns including the following patterns:
    1. All characters are lowercase, ex: 'rambi' -> 'cranky'.
    2. All characters are uppercase, ex: 'RAMBI' -> 'CRANKY'.
    3. The first character is capital, ex: 'Rambi' -> 'Cranky'.
    4. The year in copyright header, ex: 'Copyright 2013' -> 'Copyright 2014'.
  """
  replace_patterns = [ReplacePattern(getattr(src_board_name, pattern)(),
                                     getattr(dst_board_name, pattern)())
                      for pattern in ['lower', 'upper', 'title']]

  # Changes the year in the copyright header.
  # Also converts old style format to new style format.
  # Old style: Copyright (c) 2013 The Chromium OS Authors.
  # New style: Copyright 2014 The Chromium OS Authors.
  COPYRIGHT = 'Copyright .* The Chromium OS Authors'
  COPYRIGHT_THIS_YEAR = 'Copyright %d The Chromium OS Authors' % (
      date.today().year)
  replace_patterns.append(ReplacePattern(COPYRIGHT, COPYRIGHT_THIS_YEAR))

  return replace_patterns


def ParseArgs():
  parser = argparse.ArgumentParser(
      description=DESCRIPTION,
      epilog=EXAMPLES,
      formatter_class=argparse.RawDescriptionHelpFormatter)

  parser.add_argument('--src_board_name', dest='src_board_name',
                      help=('The board name of the source directory to '
                            'copy the files from.'))
  parser.add_argument('--dst_board_name', dest='dst_board_name',
                      help=('The board name of the destination directory to '
                            'copy the files to.'))

  parser.add_argument('--src_dir', dest='src_dir',
                      help=('The source directory to copy the files from.'))
  parser.add_argument('--dst_dir', dest='dst_dir',
                      help=('The destinaton directory to copy the files to.'))

  parser.add_argument('--reset_ebuild_file', action='store_true',
                      help=('whether to reset ebuild files to version r1.'))

  return parser.parse_args()


def main():
  args = ParseArgs()
  PrepareDirectoryCopy(args.src_dir, args.dst_dir)
  CopyFilesAndRename(args.src_dir, args.dst_dir,
                     ReplacePattern(args.src_board_name, args.dst_board_name),
                     args.reset_ebuild_file)
  ReplaceStringInFiles(args.dst_dir,
                       GenerateReplacePatterns(args.src_board_name,
                                               args.dst_board_name))
  print ('Migration complete!\n'
         'Please check the result under: %r.') % args.dst_dir


if __name__ == '__main__':
  main()
