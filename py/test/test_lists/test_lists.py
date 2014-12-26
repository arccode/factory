# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test list builder."""


import glob
import importlib
import logging
import os
import re
import threading
import yaml
from collections import namedtuple
from contextlib import contextmanager

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory

# Imports needed for test list modules.  Some may be unused by this
# module (hence disable=W06110), but they are included here so that
# they can be imported directly by test lists.
from cros.factory.test.factory import RequireRun
from cros.factory.utils.net_utils import WLAN  # pylint: disable=W0611


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

# Sampling is the helper class to control sampling of tests in test list.
# key: The key used in device_data which will be evaluated in run_if argument.
# rate:
#   0.0: 0% sampling rate
#   1.0: 100% sampling rate
SamplingRate = namedtuple('SamplingRate', ['key', 'rate'])

class TestListError(Exception):
  """TestList exception"""
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

  Returns a context that can be used to add subtests.
  """
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
  """Adds a factory test to the test list.

  Args:
    label_en: An English label.
    label_zh: A Chinese label.
    autotest_name: The name of the autotest to run.
    pytest_name: The name of the pytest to run (relative to
      cros.factory.test.pytests).
    invocation_target: The function to execute to run the test
      (within the Goofy process).
    kbd_shortcut: The keyboard shortcut for the test.
    dargs: Autotest arguments.
    backgroundable: Whether the test may run in the background.
    subtests: A list of tests to run inside this test.  In order
      to make conditional construction easier, this may contain None items
      (which are removed) or nested arrays (which are flattened).
    id: A unique ID for the test (defaults to the autotest name).
    has_ui: True if the test has a UI. (This defaults to True for
      OperatorTest.) If has_ui is not True, then when the test is
      running, the statuses of the test and its siblings will be shown in
      the test UI area instead.
    never_fails: True if the test never fails, but only returns to an
      untested state.
    disable_abort: True if the test can not be aborted
      while it is running.
    exclusive: Items that the test may require exclusive access to.
      May be a list or a single string. Items must all be in
      EXCLUSIVE_OPTIONS. Tests may not be backgroundable.
    enable_services: Services to enable for the test to run correctly.
    disable_services: Services to disable for the test to run correctly.
    _default_id: A default ID to use if no ID is specified.
    require_run: A list of RequireRun objects indicating which
      tests must have been run (and optionally passed) before this
      test may be run.  If the specified path includes this test, then
      all tests up to (but not including) this test must have been run
      already. For instance, if this test is SMT.FlushEventLogs, and
      require_run is "SMT", then all tests in SMT before
      FlushEventLogs must have already been run. ALL may be used to
      refer to the root (i.e., all tests in the whole test list before
      this one must already have been run).

      Examples:
        require_run='x'                 # These three are equivalent;
        require_run=RequireRun('x')     # requires that X has been run
        require_run=[RequireRun('x')]   # (but not necessarily passed)

        require_run=Passed('x')         # These are equivalent;
        require_run=[Passed('x')]       # requires that X has passed

        require_run=Passed(ALL)         # Requires that all previous tests
                                        # have passed

        require_run=['x', Passed('y')]  # Requires that x has been run
                                        # and y has passed
    run_if: Condition under which the test should be run.  This
      must be either a function taking a single argument (an
      invocation.TestArgsEnv object), or a string of the format

        table_name.col
        !table_name.col

      If the auxiliary table 'table_name' is available, then its column 'col'
      is used to determine whether the test should be run.
    iterations: Number of times to run the test.
    retries: Maximum number of retries allowed to pass the test.
      If it's 0, then no retries are allowed (the usual case). If, for example,
      iterations=60 and retries=2, then the test would be run up to 62 times
      and could fail up to twice.
    prepare: A callback function before test starts to run.
    finish: A callback function when test case completed.
      This function has one parameter indicated test result: TestState.PASSED
      or TestState.FAILED.
    _root: True only if this is the root node (for internal use
      only).
  """
  return Add(factory.FactoryTest(*args, **kwargs))


def AutomatedSequence(*args, **kwargs):
  return Add(factory.AutomatedSequence(*args, **kwargs))

def TestGroup(id, label_en='', label_zh='', run_if=None, no_host=False):
  # pylint: disable=W0622
  """Adds a test group to the current test list.

  This should always be used inside a ``with`` keyword, and tests
  to be included in that test group should be placed inside the
  contained block, e.g.::

    with TestGroup(id='some_test_group'):
      FactoryTest(id='foo', ...)
      OperatorTest(id='bar', ...)

  This creates a test group ``some_test_group`` containing the ``foo``
  and ``bar`` tests.  The top-level nodes ``foo`` and ``bar`` can be
  independently run.

  Args:
    id: The ID of the test (see :ref:`test-paths`).
    label_en: The label of the group, in English.  This defaults
      to the value of ``id`` if none is specified.
    label_zh: The label of the group, in Chinese.  This defaults
      to the value of ``label_en`` if none is specified.
    run_if: Condition under which the test should be run. Checks the docstring
      of FactoryTest.
  """
  return Add(factory.TestGroup(id=id, label_en=label_en, label_zh=label_zh,
                               run_if=run_if, no_host=no_host))


def OperatorTest(*args, **kwargs):
  """Adds an operator test (a test with a UI) to the test list.

  This is simply a synonym for
  :py:func:`cros.factory.test.test_lists.test_lists.FactoryTest`, with
  ``has_ui=True``.  It should be used instead of ``FactoryTest`` for
  tests that have a UI to be displayed to the operator.

  See :py:func:`cros.factory.test.test_lists.FactoryTest` for a
  description of all arguments.
  """
  return Add(factory.OperatorTest(*args, **kwargs))


def HaltStep(*args, **kwargs):
  return Add(factory.HaltStep(*args, **kwargs))


def ShutdownStep(*args, **kwargs):
  return Add(factory.ShutdownStep(*args, **kwargs))


def RebootStep(*args, **kwargs):
  return Add(factory.RebootStep(*args, **kwargs))


def FullRebootStep(*args, **kwargs):
  return Add(factory.FullRebootStep(*args, **kwargs))


def Passed(name):
  return RequireRun(name, passed=True)


@contextmanager
def TestList(id, label_en):  # pylint: disable=W0622
  """Context manager to create a test list.

  This should be used inside a ``CreateTestLists`` function,
  as the target of a ``with`` statement::

    def CreateTestLists():
      with TestList('main', 'Main Test List') as test_list:
        # First set test list options.
        test_list.options.auto_run_on_start = False
        # Now start creating tests.
        FactoryTest(...)
        OperatorTest(...)

  If you wish to modify the test list options (see
  :ref:`test-list-options`), you can use the ``as`` keyword to capture
  the test list into an object (here, ``test_list``).  You can then
  use ``test_list.options`` to refer to the test list options.

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

    for v in builder_state.test_lists.values():
      # Set the source path, replacing .pyc with .py
      v.source_path = re.sub(r'\.pyc$', '.py', module.__file__)
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

    Returns:
      A FactoryTestList object.
    """
    logging.info('Loading old-style test list %s', self.path)
    test_list = factory.read_test_list(self.path, state_instance)
    # Set test_list_id: old-style test lists don't know their own ID.
    test_list.test_list_id = self.test_list_id
    return test_list


def BuildAllTestLists(force_generic=False):
  """Builds all test lists in this package.

  See README for an explanation of the test-list loading process.

  Args:
    force_generic: Whether to force loading generic test list.  Defaults to
      False so that generic test list is loaded only when there is no main test
      list.

  Returns:
    A dict mapping test list IDs to test list objects.  Values are either
    OldStyleTestList objects (for old-style test lists), or TestList objects
    (for new-style test lists).
  """
  test_lists = {}

  def IsGenericTestList(f):
    return os.path.basename(f) == 'generic.py'

  def MainTestListExists():
    return ('main' in test_lists or
            os.path.exists(os.path.join(TEST_LISTS_PATH, 'main.py')))

  test_list_files = glob.glob(os.path.join(TEST_LISTS_PATH, '*.py'))
  test_list_files.sort(key=lambda f: (IsGenericTestList(f), f))
  for f in test_list_files:
    if f.endswith('_unittest.py') or os.path.basename(f) == '__init__.py':
      continue
    # Skip generic test list if there is already a main test list loaded
    # and generic test list is not forced.
    if (IsGenericTestList(f) and MainTestListExists() and
        not force_generic):
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

  return test_lists


def DescribeTestLists(test_lists):
  """Returns a friendly description of a dict of test_lists.

  Args:
    test_lists: A dict of test_list_id->test_lists (as returned by
        BuildAllTestLists)

  Returns:
    A string like "bar, foo (old-style), main".
  """
  ret = []
  for k, v in sorted(test_lists.items()):
    if isinstance(v, OldStyleTestList):
      ret.append('%s (old-style)' % k)
    else:
      ret.append(k)
  return ', '.join(ret)


def BuildTestList(id):  # pylint: disable=W0622
  """Builds only a single test list.

  Args:
    id: ID of the test list to build.

  Raises:
    KeyError: If the test list cannot be found.
  """
  test_lists = BuildAllTestLists()
  test_list = test_lists.get(id)
  if not test_list:
    raise KeyError('Unknown test list %r; available test lists are: [%s]' % (
        id, DescribeTestLists(test_lists)))
  return test_list


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


def YamlDumpTestListDestructive(test_list, stream=None):
  """Dumps a test list in YAML format.

  This modifies the test list in certain ways that makes it useless,
  hence "Destructive".

  Args:
    test_list: The test list to be dumped.
    stream: A stream to serialize into, or None to return a string
        (same as yaml.dump).
  """
  del test_list.path_map
  del test_list.state_instance
  del test_list.test_list_id
  for t in test_list.walk():
    del t.parent
    del t.root
    for r in t.require_run:
      # Delete the test object.  But r.path is still present, so we'll
      # still verify that.
      del r.test
    for k, v in t.dargs.items():
      if callable(v):
        # Replace all lambdas with "lambda: None" to make them
        # consistent
        t.dargs[k] = lambda: None
  return yaml.safe_dump(test_list, stream)
