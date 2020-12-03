#!/usr/bin/env python3
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import json
import logging
import os
import re
import sys

from cros.factory.test import device_data_constants
from cros.factory.test.env import paths
from cros.factory.test.test_lists import manager
from cros.factory.utils import config_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils


ERROR_LEVEL = type_utils.Obj(NONE=0, CONVENTION=1, WARNING=2, ERROR=3, FATAL=4)
ERROR_LEVEL_SHORT = {
    'N': ERROR_LEVEL.NONE,
    'C': ERROR_LEVEL.CONVENTION,
    'W': ERROR_LEVEL.WARNING,
    'E': ERROR_LEVEL.ERROR,
    'F': ERROR_LEVEL.FATAL,
}


def GetTestListID(test_list_config_name):
  """Get the test list id from test list config name

  Args:
    test_list_config_name: test list config name string (e.g. main.test_list).

  Returns:
    test list id (e.g. main).
  """
  return test_list_config_name.split('.')[0]


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
    parent_test_list_id = GetTestListID(parent_config_name)
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


def ValidateRunIf(test_object_value):
  if 'run_if' not in test_object_value:
    return True

  for comp in re.findall(r'\bcomponent\.has_\w+', test_object_value['run_if']):
    if comp not in device_data_constants.KEY_COMPONENT_ALLOWLIST:
      return False

  return True


def CheckTestList(manager_, waived_level, test_list_id, dump):
  """Check the test list with given `test_list_id`.

  Args:
    manager: a test list manager instance, will be used to load test list and
      perform checking.
    waived_level: The messages which are less or equal to this value do not
      count as failures.
    test_list_id: ID of the test list (a string).
    dump: true to simply load and print the test list.

  Returns:
    True if there is no error in the test list and False when there is error.
  """
  logging.info('Checking test list: %s...', test_list_id)
  try:
    test_list = manager_.GetTestListByID(test_list_id)
  except Exception:
    logging.exception('Failed to load test list: %s.', test_list_id)
    return ERROR_LEVEL.FATAL <= waived_level

  if dump:
    print(test_list.ToFactoryTestList().__repr__(recursive=True))
    return True

  _DEFINITIONS = 'definitions'
  raw_config = manager_.loader.Load(test_list_id, allow_inherit=False)
  raw_definitions = raw_config.get(_DEFINITIONS, {})
  result = True

  # Check if there are test object definiions that overrides nothing.
  parents_config = {}
  for parent_name in reversed(raw_config.get('inherit', ())):
    _parent_config = manager_.loader.Load(GetTestListID(parent_name)).ToDict()
    parents_config = config_utils.OverrideConfig(
        parents_config, _parent_config)

  parents_definitions = parents_config.get(_DEFINITIONS, {})
  for object_name, overrides in raw_definitions.items():
    if object_name not in parents_definitions:
      continue
    base_object = parents_definitions[object_name]

    if not isinstance(base_object, str) and not isinstance(overrides, str):
      new_object = config_utils.OverrideConfig(
          base_object, overrides, copy_on_write=True)
    else:
      # If one of the value is string, then OverrideConfig will simply assign
      # the value.
      new_object = overrides

    if new_object == base_object:
      logging.warning(
          'Test object "%s" inherits from another test object but overrides'
          ' nothing.', object_name)
      result &= ERROR_LEVEL.WARNING <= waived_level

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

  for test_object_name in raw_definitions:
    if not IsReferenced(test_object_name, cache):
      logging.warning(
          'Test object "%s" is defined but not referenced in any test list',
          test_object_name)
      result &= ERROR_LEVEL.WARNING <= waived_level

  for test_object_name, test_object_value in raw_definitions.items():
    if not ValidateRunIf(test_object_value):
      logging.warning(
          'The value "%s" of run_if in test object "%s" does not use the'
          ' correct value. Please check if you use the wrong name or maybe you'
          ' need to add a new key into our allow list.',
          test_object_value['run_if'], test_object_name)
      result &= ERROR_LEVEL.CONVENTION <= waived_level

  try:
    test_list.CheckValid()
  except Exception as e:
    if isinstance(e, KeyError) and str(e) == repr('tests'):
      # The list of header test list. For header test lists in private overlay,
      # we should name them with prefix 'generic'.
      header_list = ('main', 'common', 'base', 'disable_factory_server', 'smt',
                     'fat', 'runin', 'run_in', 'fft', 'grt')
      if not (test_list_id in header_list or
              test_list_id.startswith('generic')):
        logging.warning(
            'Test list "%s" does not have "tests" field. Rename it "generic_%s"'
            ' or add missing "tests" field.', test_list_id, test_list_id)
        result &= ERROR_LEVEL.ERROR <= waived_level
    else:
      logging.error('Test list "%s" is invalid: %s.', test_list_id, e)
      result &= ERROR_LEVEL.ERROR <= waived_level
  else:
    failed_tests = []
    for test in test_list.Walk():
      try:
        manager_.checker.CheckArgsType(test, test_list)
      except Exception as e:
        # We are not checking other fields, no need to show them.
        test_object = {
            'pytest_name': test.pytest_name,
            'args': test.dargs,
            'locals': test.locals_,
        }
        logging.error('Failed checking %s: %s', test.path, e)
        logging.error(
            '%s = %s\n', test.path,
            json.dumps(test_object, indent=2, sort_keys=True,
                       separators=(',', ': ')))
        failed_tests.append(test)
    if failed_tests:
      logging.error('The following tests have invalid arguments: \n  %s',
                    '\n  '.join(test.path for test in failed_tests))
      result &= ERROR_LEVEL.ERROR <= waived_level

  if not result:
    logging.error('The above warnings should be fixed')
    return False

  logging.info('Woohoo, test list "%s" looks great!', test_list_id)
  return True


def main(args):
  parser = argparse.ArgumentParser(
      description='Static Test List Checker',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--board', help='board name')
  parser.add_argument('--dump', '-d', help='dump test list content and exit',
                      action='store_true')
  parser.add_argument('--verbose', '-v', help='verbose mode',
                      action='store_true')
  parser.add_argument('test_list_id', help='test list id', nargs='+')
  parser.add_argument(
      '--waived', help=('The messages which are less or equal to this value'
                        ' do not count as failures. Levels from low to high'
                        ' N, C, W, E, F.'
                        '\n* (N) none, which fails if any check fails'
                        '\n* (C) convention, for programming standard violation'
                        '\n* (W) warning, for test list specific problems'
                        '\n* (E) error, for much probably bugs in the test list'
                        '\n* (F) fatal, if an error occurred which prevented '
                        'test_list_checker from doing'), default='N',
      choices=ERROR_LEVEL_SHORT)
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
  success = True
  for test_list_id in options.test_list_id:
    success &= CheckTestList(manager_, ERROR_LEVEL_SHORT[options.waived],
                             test_list_id, options.dump)

  sys.exit(not success)

if __name__ == '__main__':
  main(sys.argv[1:])
