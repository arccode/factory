#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import itertools
import logging

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy import invocation
from cros.factory.test import factory
from cros.factory.test import shopfloor


class TestListIterator(object):
  """An iterator of test list.

  https://chromium.googlesource.com/chromiumos/platform/factory/+/master/py/test/test_lists/TEST_LIST.md

  * The iterator will return next test to run when "next()" is called.
  * A status filter can be applied to skip some tests according to their states.
  * The iterator is loosely bind to FactoryTestList, that is you can change the
    test list object of the iterator.  If the iterator can find the last test it
    returned, the iterator will continue on next test in the new test list.
  * This object should implement pickle protocol to be able to save and reload
    by python shelve.
    (https://docs.python.org/2/library/pickle.html#pickle-protocol)

  The iterator will go through each tests in the test list start from a given
  node in depth first search order.
  self.stack is the execution stack of the iterator.

  For example, consider a test list like this:

  root (path='')
    A (path='a')
    G (path='G')
      B (path='G.b')
      G (path='G.H')
        C (path='G.H.c')

  If we start at root, then `self.stack = ['']` initially, and will become
  `self.stack = ['', 'G', 'G.H', 'G.H.c']` when we reach test C.

  If we start at test G, then `self.stack = ['G']` initially, and will become
  `self.stack = ['G', 'G.H', 'G.H.c']` when we reach test C.
  """

  _SERIALIZE_FIELDS = ('stack', 'status_filter', 'inited', 'teardown_only')

  def __init__(self, root=None, status_filter=None, test_list=None):
    """Constructor of TestListIterator.

    Args:
      root: the root of the subtree to iterate.  The iterator will only iterates
        tests that is in the subtree.  Use 'test_list' object as root will make
        this iterator walks entire tree.
      status_filter: if given, only tests with these statuses will be returned.
        The filter only applies on leaf tests (tests without subtests) or
        parallel tests, doesn't apply on test groups.
      test_list: a FactoryTestList object this iterator should iterate.  Can be
        updated by `set_test_list()` function.
    """
    if isinstance(root, factory.FactoryTest):
      self.stack = [root.path]
    elif isinstance(root, str):
      self.stack = [root]
    elif root is None:
      self.stack = []
    else:
      raise ValueError('root must be one of FactoryTest, string or None')

    self.status_filter = status_filter
    self.test_list = test_list
    self.inited = False
    self.teardown_only = False

  def __getstate__(self):
    return {key: self.__dict__[key] for key in self._SERIALIZE_FIELDS}

  def __setstate__(self, pickled_state):
    for key in self._SERIALIZE_FIELDS:
      self.__dict__[key] = pickled_state[key]
    self.test_list = None  # we didn't serialize the test_list, set it to None

  def set_test_list(self, test_list):
    assert isinstance(test_list, factory.FactoryTestList)
    self.test_list = test_list

  def check_skip(self, test):
    if isinstance(test, str):
      test = self.test_list.LookupPath(test)
    if self.status_filter:
      # status filter only applies to leaf tests
      if ((test.IsLeaf() or test.IsParallel()) and
          not self._check_status_filter(test)):
        logging.info('test %s is filtered (skipped) because its status',
                     test.path)
        logging.info('%s (skip list: %r)',
                     test.GetState().status, self.status_filter)
        return True
    if not self._check_run_if(test):
      logging.info('test %s is skipped because run_if evaluated to False',
                   test.path)
      test.UpdateState(skip=True)
      return True
    elif test.IsSkipped():
      # this test was skipped before, but now we might need to run it
      test.UpdateState(status=factory.TestState.UNTESTED, error_msg='')
      # check again (for status filter)
      return self.check_skip(test)
    return False

  # pylint: disable=method-hidden
  # This function will be mocked in `self.get_pending_tests`.
  def _check_run_if(self, test, test_arg_env=None, get_data=None):
    if test_arg_env is None:
      test_arg_env = invocation.TestArgEnv()
    if get_data is None:
      get_data = shopfloor.get_selected_aux_data
    return test.EvaluateRunIf(test_arg_env, get_data)

  def _check_status_filter(self, test):
    if not self.status_filter:
      return True
    status = test.GetState().status
    # an active test should always pass the filter (to resume a previous test)
    return status == factory.TestState.ACTIVE or status in self.status_filter

  def get(self):
    """Returns the current test item.

    If self.next() is never called before (self.inited == False), this function
    will return None.

    If the last invocation of self.next() returned a test path, then this
    function will return the same test path.

    If the last invocation of self.next() raised `StopIteration` exception, this
    function will return None.
    """
    if not self.inited:
      return None
    if not self.stack:
      return None
    return self.stack[-1]

  def _find_first_valid_test_in_subtree(self):
    """Find first valid test in the subtree.

    Assume that currently we have `self.stack = ['G', 'G.H', 'G.H.I']`.
    This function will check if G.H.I is a valid test to run, if yes, just
    return True.  If it's not valid because it contains subtests, this function
    will recursively search the subtests.

    Returns:
      True if a valid test is found, `self.stack` will indicate the test it
      found, e.g. `self.stack = ['G', 'G.H', 'G.H.I', 'G.H.I.J', 'G.H.I.J.x']`

      False if no valid test found.  In this case, `self.stack` will not be
      changed.
    """
    assert self.stack, "stack cannot be empty"

    path = self.stack[-1]
    test = self.test_list.LookupPath(path)
    if test.IsLeaf() or test.IsParallel():
      if not self.check_skip(test):
        return True

    for subtest in test.subtests:
      if not self.check_skip(subtest):
        self.stack.append(subtest.path)
        if self._find_first_valid_test_in_subtree():
          return True
        # none of the test in the subtree is valid
        self.stack.pop()
    # cannot find anything
    return False

  def _continue_depth_first_search(self):
    """Continue the depth first search starting from current node.

    Assume that currently we have `self.stack = ['G', 'G.H', 'G.H.I']`.
    This function will skip any subtests of G.H.I, and go to G.H.J (the next
    subtest of G.H after G.H.I).

    Returns:
      True if we found next test to run.  `self.stack` will indicate the test it
      found, e.g. `self.stack = ['G', 'G.H', 'G.H.J', 'G.H.J.K', 'G.H.J.K.x']`

    Raises:
      StopIteration if no next test found.
    """
    while self.stack:
      path = self.stack.pop()
      test = self.test_list.LookupPath(path)
      jump_to_teardown = False

      if not test:
        # cannot find the test we were running, maybe the test list is changed
        # between serialization and deserialization, just stop
        raise StopIteration

      if not self.stack:
        # oh, there is no parent
        raise StopIteration

      success = test.GetState().status != factory.TestState.FAILED
      if not success:
        # create an alias
        ACTION_ON_FAILURE = factory.FactoryTest.ACTION_ON_FAILURE
        if test.action_on_failure == ACTION_ON_FAILURE.NEXT:
          pass  # does nothing, just find the next test
        elif test.action_on_failure == ACTION_ON_FAILURE.PARENT:
          jump_to_teardown = True
        elif test.action_on_failure == ACTION_ON_FAILURE.STOP:
          jump_to_teardown = True
          self.teardown_only = True

      subtests = iter(test.parent.subtests)
      if jump_to_teardown or self.teardown_only:
        # we only want to run teardown tests, filter out normal tests,
        # however, to make the checking code easier to implement, current test
        # is not filtered.
        subtests = itertools.ifilter(
            lambda subtest: subtest.path == path or subtest.IsTeardown(),
            subtests)

      # find next test in parent
      found_current_test = False
      for subtest in subtests:
        if found_current_test:
          if not self.check_skip(subtest.path):
            self.stack.append(subtest.path)
            if self._find_first_valid_test_in_subtree():
              return True
            self.stack.pop()
        if path == subtest.path:
          # find current test, the next one is what we want
          found_current_test = True
      assert found_current_test

  def next(self):
    """Returns path to the test that should start now.

    The returned test could be a leaf factory test (factory test that does not
    have any subtests), or a parallel test (a factory test that has subtests but
    all of them will be run in parallel).

    Returns:
      a string the is the path of the test (use test_list.lookup_path(path) to
      get the real test object).
    """
    assert isinstance(self.test_list, factory.FactoryTestList), (
        'test_list is not set (call set_test_list() to set test list)')

    if not self.stack:
      raise StopIteration

    if not self.inited:
      # this is a special case, we try to find a test under current node first.
      # if we failed to do so, find next test as normal.
      self.inited = True
      if self._find_first_valid_test_in_subtree():
        return self.stack[-1]

    self._continue_depth_first_search()
    return self.stack[-1]

  def stop(self):
    self.stack = []

  def copy(self):
    # make a copy of myself
    it = TestListIterator(None, self.status_filter, self.test_list)
    it.stack = list(self.stack)
    return it

  def __iter__(self):
    return self

  def __repr__(self):
    return repr(self.__getstate__())

  def get_pending_tests(self):
    """List all tests that *might* be run.

    This function will return a list of test paths that are the tests that
    will be run if their run_if functions return True.

    That is, the status filter will apply correctly, but we assume that run_if
    function will return True.  So the returned list is a super set of the tests
    that are actually going to be run.

    Returns:
      list of str, which are test paths.
    """
    it = self.copy()
    # pylint: disable=protected-access
    it._check_run_if = lambda *args, **kwargs: True
    return list(it)
