#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import argparse
import json
import os
import stat


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '-a', '--all', action='store_true',
      help='Also check if files with shebang are with execution permission.')
  parser.add_argument(
      'rules_file', metavar='RULES_FILE',
      help=(
          'A JSON file contains a shebang white list and a file exclusion '
          'list.'))
  parser.add_argument(
      'files', metavar='FILE', nargs='*', help='File or directory to check.')
  args = parser.parse_args()

  with open(args.rules_file) as f:
    rules = json.load(f)
  exclusion_set = set(rules['exclusion_list'])
  white_list_set = set(rules['white_list'])

  redundant_files = []
  unknown_shebangs = {}
  def check(filepath):
    if (os.path.relpath(filepath) in exclusion_set or
        not os.path.isfile(filepath) or os.path.islink(filepath)):
      return
    executable = (os.stat(filepath).st_mode & stat.S_IXUSR) != 0
    if not executable and not args.all:
      return
    with open(filepath) as f:
      if f.read(2) != '#!':
        return
      line = f.readline().rstrip('\n')
      if not executable:
        redundant_files.append(filepath)
      elif line not in white_list_set:
        unknown_shebangs.setdefault(line, []).append(filepath)

  for arg in args.files:
    if not os.path.isdir(arg):
      check(arg)
    else:
      for dirpath, unused_dirnames, filenames in os.walk(arg):
        for filename in filenames:
          check(os.path.join(dirpath, filename))

  if redundant_files:
    print('%4d files with redundant shebang:' % len(redundant_files))
    for filepath in redundant_files:
      print('     %s' % filepath)
    print()
  for shebang, filepaths in unknown_shebangs.iteritems():
    print('%4d #!%s' % (len(filepaths), shebang))
    for filepath in filepaths:
      print('     %s' % filepath)
    print()
  if redundant_files or unknown_shebangs:
    quit('Failed.')


if __name__ == '__main__':
  main()
