#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import json
import re
import subprocess
import sys


def ComputeDiffRange(commit, files):
  """Collect files changed by @commit, with ranges of the change.

  Args:
    commit: If given, will check the change between commit^..commit. Otherwise,
        will check the unstaged changes (that is, `git diff HEAD`).
    files: If given, the return value will be limited to files.  Otherwise, will
        changed files will be returned.

  Returns:
    A mapping of {"<file_path>": [(diff_start, diff_len), ...]}
  """
  # Copied from depot_tools/git_cl.py
  diff_cmd = [
      'git', '-c', 'core.quotePath=false', 'diff', '--no-ext-diff', '-U0',
      '--src-prefix=a/', '--dst-prefix=b/'
  ]
  if commit:
    diff_cmd.append('{commit}^..{commit}'.format(commit=commit))
  # If @files is an empty list, the diff command will show "all" changed files.
  diff_cmd += ['--', *files]
  diff_output = subprocess.check_output(diff_cmd, encoding='utf-8')

  pattern = r'(?:^diff --git a/(?:.*) b/(.*))|(?:^@@.*\+(.*) @@)'
  # 2 capture groups
  # 0 == fname of diff file
  # 1 == 'diff_start,diff_count' or 'diff_start'
  # will match each of
  # diff --git a/foo.foo b/foo.py
  # @@ -12,2 +14,3 @@
  # @@ -12,2 +17 @@
  # running re.findall on the above string with pattern will give
  # [('foo.py', ''), ('', '14,3'), ('', '17')]

  curr_file = None
  line_diffs = {}
  for match in re.findall(pattern, diff_output, flags=re.MULTILINE):
    if match[0] != '':
      # Will match the second filename in diff --git a/a.py b/b.py.
      curr_file = match[0]
      line_diffs[curr_file] = []
    else:
      # Matches +14,3
      if ',' in match[1]:
        diff_start, diff_count = match[1].split(',')
      else:
        # Single line changes are of the form +12 instead of +12,1.
        diff_start = match[1]
        diff_count = 1

      diff_start = int(diff_start)
      diff_count = int(diff_count)

      # If diff_count == 0 this is a removal we can ignore.
      line_diffs[curr_file].append((diff_start, diff_count))

  return line_diffs


def main():
  parser = argparse.ArgumentParser()
  subparsers = parser.add_subparsers(title='subcommands', dest='subcommand')
  diff_parser = subparsers.add_parser('diff')
  diff_parser.add_argument('--commit', help='Compute diff made by a commit')
  diff_parser.add_argument(
      'files', nargs='*', help='File or directly to compute diff')

  args = parser.parse_args()
  if args.subcommand == 'diff':
    line_diffs = ComputeDiffRange(args.commit, args.files)
    json.dump(line_diffs, sys.stdout, indent=2)


if __name__ == '__main__':
  main()
