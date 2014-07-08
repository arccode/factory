#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import argparse
import itertools
import logging
import os
import sys

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import CheckOutput, Spawn


def main():
  parser = argparse.ArgumentParser(
      description="Lints files that are new, changed, or in a pending CL.")
  parser.add_argument('--verbose', '-v', action='count')
  args = parser.parse_args()
  logging.basicConfig(level=logging.WARNING - 10 * (args.verbose or 0))

  # chdir to repo root so paths are all correct
  os.chdir(CheckOutput(['git', 'rev-parse', '--show-toplevel']).strip())

  output = CheckOutput(
      ['git', 'status', '--untracked-files=all', '--porcelain'])
  uncommitted = [x[3:] for x in output.splitlines()]
  uncommitted = [x for x in uncommitted
                 if x.endswith('.py') and '#' not in x]
  logging.info('Uncommitted files: %r', uncommitted)

  all_files = set(uncommitted)

  for i in itertools.count():
    commit = 'HEAD~%d' % i
    proc = Spawn(['git', 'log', '-1', commit], read_stdout=True)
    if proc.returncode:
      # No more log entries
      break
    if '\n    Reviewed-on: ' in proc.stdout_data:
      logging.info('%s has Reviewed-on; ending search', commit)
      break

    files = CheckOutput(['git', 'diff-tree', '--no-commit-id', '--name-only',
                         '-r', commit]).splitlines()
    logging.info('%s contains files %s', commit, files)
    for f in files:
      if f.endswith('.py'):
        all_files.add(f)

  if not all_files:
    sys.exit('No files to lint.')

  all_files_str = ' '.join(sorted(all_files))
  proc = Spawn(['make', 'lint', 'LINT_FILES=%s' % all_files_str], call=True)
  sys.exit(proc.returncode)


if __name__ == '__main__':
  main()
