#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A script to run all pre-submit checks."""


from __future__ import print_function

import sys
import os


def FilterFiles(folder, files):
  return [file_path for file_path in files if file_path.startswith(
      '' if folder == '.' else folder)]


def CheckTestsPassedInDirectory(folder, files, instruction):
  """Checks if all given files are older than previous execution of tests."""
  files_in_folder = FilterFiles(folder, files)
  if not files_in_folder:
    return
  tests_file_path = os.path.join(folder, '.tests-passed')
  if not os.path.exists(tests_file_path):
    exit('Tests have not passed.\n%s' % instruction)
  mtime = os.path.getmtime(tests_file_path)
  newer_files = [file_path for file_path in files_in_folder
                 if os.path.getmtime(file_path) > mtime]
  if newer_files:
    exit('Files have changed since last time tests have passed:\n%s\n%s' %
         ('\n'.join('  ' + new_file for new_file in newer_files), instruction))


def CheckFactoryRepo(files):
  return CheckTestsPassedInDirectory(
      '.', files, 'Please run "make test" in factory repo inside chroot.')


def CheckUmpire(files):
  return CheckTestsPassedInDirectory(
      'py/umpire', files,
      'Please run "setup/cros_docker.sh umpire test" outside chroot.')


def CheckDome(files):
  return CheckTestsPassedInDirectory(
      'py/dome', files,
      'Please run "make test" in py/dome outside chroot.')


def CheckMakeFactoryPackage(files):
  target = 'setup/make_factory_package.sh'
  if not target in files:
    return

  instruction = '''
  Please run "py/tools/test_make_factory_package.py" (use --help for more
  information on how to use it if you do not have access to release
  repositories).'''

  tests_file_path = '.test_make_factory_package.passed'
  if not os.path.exist(tests_file_path):
    exit('Tests have not passed.%s' % instruction)
  if not os.path.getmtime(tests_file_path) > os.path.getmtime(target):
    exit('%s has been changed.%s' % (target, instruction))


def main():
  files = sys.argv[1:]
  CheckMakeFactoryPackage(files)
  CheckFactoryRepo(files)
  CheckUmpire(files)
  CheckDome(files)
  print('All presubmit test passed.')


if __name__ == '__main__':
  main()
