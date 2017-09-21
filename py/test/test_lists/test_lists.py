# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test list builder."""


from collections import namedtuple
from contextlib import contextmanager
import glob
import imp
import importlib
import logging
import os
import re
import sys
import threading

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test import factory


# Directory for test lists.
TEST_LISTS_PATH = os.path.join(paths.FACTORY_DIR, 'py', 'test', 'test_lists')

# State used to build test lists.
#
# Properties:
#   stack: A stack of items being built.  stack[0] is always a TestList
#       (if one is currently being built).
#   test_lists: A dictionary (id, test_list_object) of all test lists
#       that have been built or are being built.
#   in_teardown: A boolean, we are in a subtree of teardown tests.
builder_state = threading.local()

# Sampling is the helper class to control sampling of tests in test list.
# key: The key used in device_data which will be evaluated in run_if argument.
# rate:
#   0.0: 0% sampling rate
#   1.0: 100% sampling rate
SamplingRate = namedtuple('SamplingRate', ['key', 'rate'])

# String prefix to indicate this value needs to be evaluated
EVALUATE_PREFIX = 'eval! '


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
  if builder_state.in_teardown:
    test.SetTeardown()
  builder_state.stack[-1].subtests.append(test)
  return Context(test)


@contextmanager
def Subtests():
  """New tests added in this context will be appended as subtests.

  By default, tests are always appended to 'subtests', this function is just for
  making APIs symmetric.
  """
  if not builder_state.stack:
    raise TestListError('Cannot switch to subtests: not within a test list')
  if builder_state.in_teardown:
    raise TestListError('Subtests of teardown tests must be teardown tests')
  yield


@contextmanager
def Teardowns():
  """New tests added in this context will be appended as teardown tests.

  Tests added with in this context will be marked as teardown.
  """
  if not builder_state.stack:
    raise TestListError('Cannot switch to teardowns: not within a test list')
  if builder_state.in_teardown:
    raise TestListError('You don\'t need to switch to teardown test again')
  builder_state.in_teardown = True
  yield
  builder_state.in_teardown = False


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
    label: A i18n label.
    pytest_name: The name of the pytest to run (relative to
      cros.factory.test.pytests).
    invocation_target: The function to execute to run the test
      (within the Goofy process).
    dargs: pytest arguments.
    parallel: Whether the subtests should run in parallel.
    subtests: A list of tests to run inside this test.  In order
      to make conditional construction easier, this may contain None items
      (which are removed) or nested arrays (which are flattened).
    id: A unique ID for the test.
    has_ui: Deprecated. Has no effect now.
    never_fails: True if the test never fails, but only returns to an
      untested state.
    disable_abort: True if the test can not be aborted
      while it is running.
    exclusive_resources: Resources that the test may require exclusive access
      to. May be a list or a single string. Items must all be in
      `cros.factory.goofy.plugins.plugin.RESOURCE`.
    enable_services: Services to enable for the test to run correctly.
    disable_services: Services to disable for the test to run correctly.
    require_run: A list of RequireRun objects indicating which
      tests must have been run (and optionally passed) before this
      test may be run.  If the specified path includes this test, then
      all tests up to (but not including) this test must have been run
      already. For instance, if this test is ``SMT.FlushEventLogs``, and
      require_run is ``"SMT"``, then all tests in SMT before
      ``FlushEventLogs`` must have already been run. ALL may be used to
      refer to the root (i.e., all tests in the whole test list before
      this one must already have been run). Examples::

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
      ``invocation.TestArgsEnv`` object), or a string of the format::

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
      This function has one parameter indicated test result:
      ``TestState.PASSED`` or ``TestState.FAILED``.
    _root: True only if this is the root node (for internal use
      only).
  """
  return Add(factory.FactoryTest(*args, **kwargs))


def AutomatedSequence(*args, **kwargs):
  return Add(factory.AutomatedSequence(*args, **kwargs))


def TestGroup(*args, **kwargs):
  """Adds a test group to the current test list.

  This should always be used inside a ``with`` keyword, and tests
  to be included in that test group should be placed inside the
  contained block, e.g.::

    with TestGroup(label=_('some_test_group')):
      FactoryTest(label=_('foo'), ...)
      OperatorTest(label=_('bar'), ...)

  This creates a test group ``some_test_group`` containing the ``foo``
  and ``bar`` tests.  The top-level nodes ``foo`` and ``bar`` can be
  independently run.

  Args:
    id: Optional, the ID of the test (see :ref:`test-paths`).
    label: The i18n label of the group.
    run_if: Condition under which the test should be run. Checks the docstring
      of FactoryTest.
  """
  return Add(factory.TestGroup(*args, **kwargs))


# This is same as
# :py:func:`cros.factory.test.test_lists.test_lists.FactoryTest`, and is kept
# here for backward compatibility.
OperatorTest = FactoryTest


def HaltStep(*args, **kwargs):
  return Add(factory.HaltStep(*args, **kwargs))


def ShutdownStep(*args, **kwargs):
  return Add(factory.ShutdownStep(*args, **kwargs))


def RebootStep(*args, **kwargs):
  return Add(factory.RebootStep(*args, **kwargs))


def FullRebootStep(*args, **kwargs):
  return Add(factory.FullRebootStep(*args, **kwargs))


def Passed(name):
  return factory.RequireRun(name, passed=True)


@contextmanager
def TestList(id, label=None): # pylint: disable=redefined-builtin
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
    label: Label for the test list.
  """
  if id in builder_state.test_lists:
    raise TestListError('Duplicate test list with id %r' % id)
  if builder_state.stack:
    raise TestListError(
        'Cannot create test list %r within another test list %r',
        id, builder_state.stack[0].id)
  test_list = factory.FactoryTestList(
      [], None, factory.Options(), id, label=label, finish_construction=False)
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


def BuildTestListFromString(test_items, options=''):
  """Build a test list from string for *unittests*.

  Args:
    test_items: the body of "with test_lists.TestList(...)" statement.  The
      'test_lists' module is imported, so you can use test_lists.FactoryTest or
      other functions to generate test items.  The top level should indent "4"
      spaces.
    options: set test list options, the "options" variable is imported.  Should
      indent "4" spaces.
  """

  _TEST_LIST_TEMPLATE = """
import factory_common
from cros.factory.test.test_lists import test_lists
from cros.factory.utils.net_utils import WLAN

def CreateTestLists():
  with test_lists.TestList(id='id', label='label') as test_list:
    options = test_list.options

    # Load dummy plugin config as default.
    options.plugin_config_name = 'goofy_plugin_goofy_unittest'
    {options}
    {test_items}
  """
  source = _TEST_LIST_TEMPLATE.format(test_items=test_items, options=options)
  module = imp.new_module('stub_test_list')
  module.__file__ = '/dev/null'
  exec source in module.__dict__

  created_test_lists = BuildTestLists(module)
  assert len(created_test_lists) == 1
  return created_test_lists.values()[0]


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
  builder_state.in_teardown = False

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


def BuildAllTestLists(force_generic=False):
  """Builds all test lists in this package.

  See README for an explanation of the test-list loading process.

  Args:
    force_generic: Whether to force loading generic test list.  Defaults to
      False so that generic test list is loaded only when there is no main test
      list.

  Returns:
    A 2-element tuple, containing: (1) A dict mapping test list IDs to test list
    objects.  Values are TestList objects.  (2) A dict mapping files that failed
    to load to the output of sys.exc_info().
  """
  test_lists = {}
  failed_files = {}

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
    except Exception:
      logging.exception('Unable to import %s', module_name)
      failed_files[f] = sys.exc_info()
      continue

    method = getattr(module, 'CreateTestLists', None)
    if method:
      try:
        new_test_lists = BuildTestLists(module)
        dups = set(new_test_lists) & set(test_lists.keys())
        if dups:
          logging.warning('Duplicate test lists: %s', dups)
        test_lists.update(new_test_lists)
      except Exception:
        logging.exception('Unable to read test lists from %s', module_name)
        failed_files[f] = sys.exc_info()

  return test_lists, failed_files


def DescribeTestLists(test_lists):
  """Returns a friendly description of a dict of test_lists.

  Args:
    test_lists: A dict of test_list_id->test_lists (as returned by
        BuildAllTestLists)

  Returns:
    A string like "bar, foo (old-style), main".
  """
  ret = []
  for k in sorted(test_lists.keys()):
    ret.append(k)
  return ', '.join(ret)


def BuildTestList(id):  # pylint: disable=redefined-builtin
  """Builds only a single test list.

  Args:
    id: ID of the test list to build.

  Raises:
    KeyError: If the test list cannot be found.
  """
  test_lists, _ = BuildAllTestLists()
  test_list = test_lists.get(id)
  if not test_list:
    raise KeyError('Unknown test list %r; available test lists are: [%s]' % (
        id, DescribeTestLists(test_lists)))
  return test_list
