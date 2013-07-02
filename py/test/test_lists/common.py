# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""New-style test list builder."""


import logging
import threading
from contextlib import contextmanager

from cros.factory.test import factory

# Imports needed for test list modules.
from cros.factory.test.factory import RequireRun
from cros.factory.goofy.connection_manager import WLAN  # pylint: disable=W0611


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
      [], None, factory.Options(), label_en, finish_construction=False)
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
      or object with a CreateTestLists method.
  """
  builder_state.stack = []
  builder_state.test_lists = {}

  try:
    if isinstance(module, str):
      module = __import__(module, fromlist=['CreateTestLists'])
    module.CreateTestLists()
    logging.info('Created test lists from %r: %r',
                 module, sorted(builder_state.test_lists.keys()))
    if not builder_state.test_lists:
      raise TestListError('No test lists were created in %r', module)
    return builder_state.test_lists
  finally:
    # Clear out the state, to avoid unnecessary references or
    # accidental reuse.
    builder_state.__dict__.clear()
