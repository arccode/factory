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


def GetInheritSet(manager_, test_list_id):
  """Generate a set contains all inheritance ancestors of `test_list_id`.

  Args:
    manager_: a test list manager instance.
    test_list_id: ID of the test list that we want to find the inherit
                  ancestors.

  Returns:
    A set object.
  """
  raw_config = manager_.loader.Load(test_list_id, allow_inherit=False)

  inherit_set = {test_list_id}
  if 'inherit' not in raw_config:
    return inherit_set

  for parent_config_name in raw_config['inherit']:
    parent_test_list_id = parent_config_name.split('.')[0]
    inherit_set.update(GetInheritSet(manager_, parent_test_list_id))

  return inherit_set


def IsReferenced(test_object_name, cache):
  """Check if `test_object_name` appears in cache.

  If a test object definition is referenced in the `tests` section of a test
  list, then the test object should appears in the test object cache for
  building the test objects.
  """
  for _test_list_id in cache:
    if test_object_name in cache[_test_list_id]:
      return True
  return False


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

  # Check if there are unreferenced test object definitions in the test list.
  cache = {}
  all_test_lists, unused_failed_test_lists = manager_.BuildAllTestLists()
  for child_test_list_id in all_test_lists:
    # Skip because child_test_list_id is not a child of test_list_id.
    if test_list_id not in GetInheritSet(manager_, child_test_list_id):
      continue

    cache[child_test_list_id] = {}
    _test_list = all_test_lists[child_test_list_id]
    _config = _test_list.ToTestListConfig()
    for _test_object in _config['tests']:
      _test_list.MakeTest(_test_object, cache[child_test_list_id])

  raw_config = manager_.loader.Load(test_list_id, allow_inherit=False)
  for test_object_name in raw_config['definitions']:
    if not IsReferenced(test_object_name, cache):
      logging.warning(
          'Test object "%s" is defined but not referenced in any test list',
          test_object_name)

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
