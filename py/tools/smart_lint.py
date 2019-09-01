#!/usr/bin/env python2
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import argparse
import itertools
import logging
import os
import re
import sys

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import cros_board_utils
from cros.factory.utils.process_utils import CheckOutput
from cros.factory.utils.process_utils import Spawn


RE_PACKAGE_FILES = re.compile(r'.*?files/')


def GetFileToLint(path=None):
  output = CheckOutput(
      ['git', 'status', '--untracked-files=all', '--porcelain'], cwd=path,
      log=True)

  # Remove first three characters, and anything up to the -> for renames.
  uncommitted = [re.sub(r'^...(.+ -> )?', '', x) for x in output.splitlines()]

  # The output contains full path as
  # chromeos-base/{chromeos-,}factory-board/files/py/device/boards/test.py
  # and we want to strip until 'files/'.
  uncommitted = [re.sub(RE_PACKAGE_FILES, '', x) if path else x
                 for x in uncommitted if x.endswith('.py') and '#' not in x]
  logging.info('Uncommitted files: %r', uncommitted)

  all_files = set(uncommitted)

  for i in itertools.count():
    commit = 'HEAD~%d' % i
    proc = Spawn(['git', 'log', '-1', commit], cwd=path, read_stdout=True)
    if proc.returncode:
      # No more log entries
      break
    if '\n    Reviewed-on: ' in proc.stdout_data:
      logging.info('%s has Reviewed-on; ending search', commit)
      break

    files = CheckOutput(['git', 'diff-tree', '--no-commit-id', '--name-only',
                         '-r', commit], cwd=path, log=True).splitlines()
    logging.info('%s contains files %s', commit, files)
    for f in files:
      file_path = os.path.join(path, f) if path else f
      if f.endswith('.py') and os.path.exists(file_path):
        all_files.add(re.sub(RE_PACKAGE_FILES, '', f) if path else f)

  all_files = set(f for f in all_files if os.path.exists(f))
  return all_files

def main():
  parser = argparse.ArgumentParser(
      description='Lints files that are new, changed, or in a pending CL.')
  parser.add_argument('--verbose', '-v', action='count')
  parser.add_argument('--overlay', '-o')
  args = parser.parse_args()
  logging.basicConfig(level=logging.WARNING - 10 * (args.verbose or 0))

  # chdir to repo root so paths are all correct
  os.chdir(CheckOutput(['git', 'rev-parse', '--show-toplevel']).strip())

  all_files = GetFileToLint()
  if args.overlay:
    overlay_path = cros_board_utils.GetChromeOSFactoryBoardPath(args.overlay)
    if overlay_path:
      all_files |= GetFileToLint(os.path.join(overlay_path, '../..'))
    CheckOutput(['make', 'overlay-%s' % args.overlay])

  all_files_str = ' '.join(sorted(all_files))
  overlay_args = ['-C', 'overlay-%s' % args.overlay] if args.overlay else []
  proc = Spawn(
      ['make'] + overlay_args + ['lint', 'LINT_FILES=%s' % all_files_str],
      call=True, log=True)
  sys.exit(proc.returncode)


if __name__ == '__main__':
  main()
