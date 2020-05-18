#!/usr/bin/env python3
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import argparse
import json
import logging
import os
import sys

from cros.factory.test.env import paths
from cros.factory.test.test_lists import manager
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils


def CheckTestList(manager_, test_list_id, dump):
  """Check the test list with given `test_list_id`.

  Args:
    manager: a test list manager instance, will be used to load test list and
      perform checking.
    test_list_id: ID of the test list (a string).
    dump: true to simply load and print the test list.
  """
  logging.info('Checking test list: %s...', test_list_id)
  try:
    test_list = manager_.GetTestListByID(test_list_id)
  except Exception:
    logging.exception('Failed to load test list: %s.', test_list_id)
    return

  if dump:
    print(test_list.ToFactoryTestList().__repr__(recursive=True))
    return

  try:
    test_list.CheckValid()
  except Exception as e:
    if isinstance(e, KeyError) and str(e) == repr('tests'):
      logging.warning('Test list "%s" does not have "tests" field. '
                      'Fine for generic test lists.', test_list_id)
    else:
      logging.error('Test list "%s" is invalid: %s.', test_list_id, e)
    return

  failed_tests = []
  for test in test_list.Walk():
    try:
      manager_.checker.CheckArgsType(test, test_list)
    except Exception as e:
      test_object = {  # We are not checking other fields, no need to show them.
          'pytest_name': test.pytest_name,
          'args': test.dargs,
          'locals': test.locals_,
      }
      logging.error('Failed checking %s: %s', test.path, e)
      logging.error('%s = %s\n', test.path,
                    json.dumps(test_object, indent=2, sort_keys=True,
                               separators=(',', ': ')))
      failed_tests.append(test)

  if failed_tests:
    logging.error('The following tests have invalid arguments: \n  %s',
                  '\n  '.join(test.path for test in failed_tests))
  else:
    logging.info('Woohoo, test list "%s" looks great!', test_list_id)


def main(args):
  parser = argparse.ArgumentParser(description='Static Test List Checker')
  parser.add_argument('--board', help='board name')
  parser.add_argument('--dump', '-d', help='dump test list content and exit',
                      action='store_true')
  parser.add_argument('--verbose', '-v', help='verbose mode',
                      action='store_true')
  parser.add_argument('test_list_id', help='test list id', nargs='+')
  options = parser.parse_args(args)

  logging.basicConfig(
      level=(logging.DEBUG if options.verbose else logging.INFO))

  if options.board:
    if not sys_utils.InChroot():
      raise ValueError('`board` argument is only availabe in chroot')

    process_utils.Spawn(['make', 'overlay-' + options.board],
                        cwd=paths.FACTORY_DIR, check_call=True,
                        ignore_stdout=True)
    # Run the copy of this script under overlay-board directory.
    overlay_dir = os.path.join(paths.FACTORY_DIR, 'overlay-' + options.board)
    overlay_factory_env = os.path.join(overlay_dir, 'bin', 'factory_env')
    tools_dir = os.path.join(overlay_dir, 'py', 'tools')
    overlay_checker_path = os.path.join(tools_dir, os.path.basename(__file__))
    # Remove --board argument.
    board_index = args.index('--board')
    new_args = ([overlay_factory_env, overlay_checker_path] +
                args[:board_index] + args[board_index + 2:])
    os.execv(overlay_factory_env, new_args)

  manager_ = manager.Manager()
  for test_list_id in options.test_list_id:
    CheckTestList(manager_, test_list_id, options.dump)

if __name__ == '__main__':
  main(sys.argv[1:])
