# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test list builder."""


import glob
import importlib
import logging
import os
import re
import threading
from contextlib import contextmanager

from cros.factory.test import factory

# Imports needed for test list modules.  Some may be unused by this
# module (hence disable=W06110), but they are included here so that
# they can be imported directly by test lists.
from cros.factory.test.factory import RequireRun
from cros.factory.goofy.connection_manager import WLAN  # pylint: disable=W0611


# Directory for new-style test lists.
TEST_LISTS_PATH = os.path.join(
    factory.FACTORY_PACKAGE_PATH, 'test', 'test_lists')

# File identifying the active test list.
ACTIVE_PATH = os.path.join(TEST_LISTS_PATH, 'ACTIVE')

# Main test list name.
MAIN_TEST_LIST_ID = 'main'

# Old symlinked custom directory (which may contain test lists).
# For backward compatibility only.
CUSTOM_DIR = os.path.join(factory.FACTORY_PATH, 'custom')

# State used to build test lists.
#
# Properties:
#   stack: A stack of items being built.  stack[0] is always a TestList
#       (if one is currently being built).
#   test_lists: A dictionary (id, test_list_object) of all test lists
#       that have been built or are being built.
builder_state = threading.local()


class TestListError(Exception):
  pass


@contextmanager
def Context(test):
  """Creates the context manager for a test (or test list) with subtests.

  This appends test to the stack when it is entered, and pops it from the stack
  when exited.
  """
  try:
    builder_state.stack.append(test)
    yield test
  finally:
    popped = builder_state.stack.pop()
    assert test == popped


def Add(test):
  """Adds a test to the current item on the state.

  Returns a context that can be used to add subtests."""
  if not builder_state.stack:
    raise TestListError('Cannot add test %r: not within a test list' % test.id)
  builder_state.stack[-1].subtests.append(test)
  return Context(test)


#####
#
# Builders for test steps/object in cros.factory.test.factory.
#
# See the respective class definitions in that module for docs.
#
#####

def FactoryTest(*args, **kwargs):
  return Add(factory.FactoryTest(*args, **kwargs))


def AutomatedSequence(*args, **kwargs):
  return Add(factory.AutomatedSequence(*args, **kwargs))


def TestGroup(*args, **kwargs):
  return Add(factory.TestGroup(*args, **kwargs))


def OperatorTest(*args, **kwargs):
  return Add(factory.OperatorTest(*args, **kwargs))


def HaltStep(*args, **kwargs):
  return Add(factory.HaltStep(*args, **kwargs))


def ShutdownStep(*args, **kwargs):
  return Add(factory.ShutdownStep(*args, **kwargs))


def RebootStep(*args, **kwargs):
  return Add(factory.RebootStep(*args, **kwargs))


def Passed(name):
  return RequireRun(name, passed=True)


@contextmanager
def TestList(id, label_en):  # pylint: disable=W0622
  """Creates a test list.

  Args:
    id: The ID of the test list.  By convention, the default test list
      is called 'main'.
    label_en: An English label for the test list.
  """
  if id in builder_state.test_lists:
    raise TestListError('Duplicate test list with id %r' % id)
  if builder_state.stack:
    raise TestListError(
        'Cannot create test list %r within another test list %r',
        id, builder_state.stack[0].id)
  test_list = factory.FactoryTestList(
      [], None, factory.Options(), id, label_en, finish_construction=False)
  builder_state.test_lists[id] = test_list
  try:
    builder_state.stack.append(test_list)
    # Proceed with subtest construction.
    yield test_list
    # We're done: finalize it (e.g., to check for duplicate path
    # elements).
    test_list.FinishConstruction()
  finally:
    popped = builder_state.stack.pop()
    assert test_list == popped


def BuildTestLists(module):
  """Creates test lists from a module.

  This runs the CreateTestLists function in the module, which should look like:

  def CreateTestLists():
    # Add tests for the 'main' test list
    with TestList('main', 'All Tests'):
      with TestGroup(...):
        ...
      OperatorTest(...)

    # Add tests for the 'alternate' test list
    with TestList('alternate', 'Alternate'):
      ...

  Args:
    module: The name of the module to load the tests from, or any module
      or object with a CreateTestLists method.  If None, main.py will be
      read (from the overlay) if it exists; otherwise generic.py will be
      read (from the factory repo).
  """
  builder_state.stack = []
  builder_state.test_lists = {}

  try:
    if isinstance(module, str):
      module = __import__(module, fromlist=['CreateTestLists'])
    module.CreateTestLists()
    if not builder_state.test_lists:
      raise TestListError('No test lists were created by %r' %
                          getattr(module, '__name__', module))

    return builder_state.test_lists
  finally:
    # Clear out the state, to avoid unnecessary references or
    # accidental reuse.
    builder_state.__dict__.clear()


class OldStyleTestList(object):
  """A reference to an old-style test list.

  This object contains the same id and label_en attributes as
  FactoryTestList (e.g., to use to display a full test list menu) but
  it does not contain the full contents of the test list, since
  loading all test lists may be slow and have side effects.  Use Load
  to actually load the list.
  """
  def __init__(self, test_list_id, label_en, path):
    self.test_list_id = test_list_id
    self.label_en = label_en
    self.path = path

  def Load(self, state_instance=None):
    """Loads the test list referred to by this object.

    Returns: A FactoryTestList object.
    """
    logging.info('Loading old-style test list %s', self.path)
    test_list = factory.read_test_list(self.path, state_instance)
    # Set test_list_id: old-style test lists don't know their own ID.
    test_list.test_list_id = self.test_list_id
    return test_list


def BuildAllTestLists():
  """Builds all test lists in this package.

  See README for an explanation of the test-list loading process.

  Returns:
    A dict mapping test list IDs to test list objects.  Values are either
    OldStyleTestList objects (for old-style test lists), or TestList objects
    (for new-style test lists).
  """
  test_lists = {}

  def IsGenericTestList(f):
    return os.path.basename(f) == 'generic.py'

  test_list_files = glob.glob(os.path.join(TEST_LISTS_PATH, '*.py'))
  test_list_files.sort(key=lambda f: (IsGenericTestList(f), f))
  for f in test_list_files:
    if f.endswith('_unittest.py') or os.path.basename(f) == '__init__.py':
      continue
    # Skip generic test list if there is already a main test list loaded.
    if IsGenericTestList(f) and 'main' not in test_lists:
      continue

    module_name = ('cros.factory.test.test_lists.' +
                   os.path.splitext(os.path.basename(f))[0])
    try:
      module = importlib.import_module(module_name)
    except:  # pylint: disable=W0702
      logging.exception('Unable to import %s', module_name)
      continue

    method = getattr(module, 'CreateTestLists', None)
    if method:
      try:
        new_test_lists = BuildTestLists(module)
        dups = set(new_test_lists) & set(test_lists.keys())
        if dups:
          logging.warning('Duplicate test lists: %s', dups)
        test_lists.update(new_test_lists)
      except:  # pylint: disable=W0702
        logging.exception('Unable to read test lists from %s', module_name)

  # Also read in all old-style test lists.  We don't actually evaluate
  # the contents yet, since that might be very slow and have side
  # effects; rather, we create an placeholder OldStyleTestList object
  # (which can be Load()ed on demand).
  for d in [CUSTOM_DIR, factory.TEST_LISTS_PATH]:
    # Do this in sorted order to make sure that it's deterministic,
    # and we see test_list before test_list.generic.
    for path in sorted(glob.glob(os.path.join(d, 'test_list*'))):
      if path.endswith('~') or path.endswith('#'):
        continue

      match = re.match(
          r'test_list'    # test_list prefix
          r'(?:\.(.+))?'  # optional dot plus suffix
          r'$',
          os.path.basename(path))
      if not match:
        continue
      test_list_id = match.group(1)

      # Use MAIN_TEST_LIST_ID for either 'test_list' or
      # 'test_list.generic'.
      if test_list_id in [None, 'generic']:
        test_list_id = MAIN_TEST_LIST_ID

      # Never override a new-style test list; and never let
      # test_list.generic override test_list.
      if test_list_id in test_lists:
        continue

      with open(path) as f:
        # Look for the test list name, if specified in the test list.
        match = re.search(r"^\s*TEST_LIST_NAME\s*=\s*"
                          r"u?"        # Optional u for unicode
                          r"([\'\"])"  # Single or double quote
                          r"(.+)"      # The actual name
                          r"\1",       # The quotation mark
                          f.read(), re.MULTILINE)
      name = match.group(2) if match else test_list_id
      test_lists[test_list_id] = OldStyleTestList(test_list_id, name, path)

  test_list_descriptions = []
  for k, v in sorted(test_lists.items()):
    if isinstance(v, OldStyleTestList):
      test_list_descriptions.append('%s (old-style)' % k)
    else:
      test_list_descriptions.append(k)
  logging.info('Loaded test lists: [%s]', ', '.join(test_list_descriptions))
  return test_lists


def GetActiveTestListId():
  """Returns the ID of the active test list.

  This is read from the py/test/test_lists/ACTIVE file, if it exists.
  If there is no ACTIVE file, then 'main' is returned.
  """
  # Make sure it's a real file (and the user isn't trying to use the
  # old symlink method).
  if os.path.islink(ACTIVE_PATH):
    raise TestListError(
        '%s is a symlink (should be a file containing a '
        'test list ID)' % ACTIVE_PATH)

  # Make sure "active" doesn't exist; it should be ACTIVE.
  wrong_caps_file = os.path.join(os.path.dirname(ACTIVE_PATH),
                                 os.path.basename(ACTIVE_PATH).lower())
  if os.path.lexists(wrong_caps_file):
    raise TestListError('Wrong spelling (%s) for active test list file ('
                        'should be %s)' % (wrong_caps_file, ACTIVE_PATH))

  if not os.path.exists(ACTIVE_PATH):
    return MAIN_TEST_LIST_ID

  with open(ACTIVE_PATH) as f:
    test_list_id = f.read().strip()
    if re.search(r'\s', test_list_id):
      raise TestListError('%s should contain only a test list ID' %
                          test_list_id)
    return test_list_id


def SetActiveTestList(id):  # pylint: disable=W0622
  """Sets the active test list.

  This writes the name of the new active test list to ACTIVE_PATH.
  """
  with open(ACTIVE_PATH, 'w') as f:
    f.write(id + '\n')
    f.flush()
    os.fdatasync(f)
