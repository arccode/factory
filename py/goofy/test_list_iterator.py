# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging

from cros.factory.test import state
from cros.factory.test.test_lists import test_list as test_list_module
from cros.factory.test.test_lists import test_object
from cros.factory.utils import type_utils


class PickableFrame:
  """Represent a frame of call stack.

  This object is used to store a frame of recursive call, for example:

    def compute_gcd(a, b):
      if b != 0:
        return compute_gcd(b, a % b)
      else:
        return a

  The call stack when this function is called by a=10, b=5 will be:

    compute_gcd(5, 10)
      compute_gcd(10, 5)
        compute_gcd(5, 0)
          return 5

  Each recursive call will create a new frame and the frame will store necessary
  variables to allow interrupting and resuming.

  Fields:
    node: the argument of this frame, the meaning of each frame.node should be
      the same, for example, in `compute_gcd`, all of them will be a tuple of
      integers.
    next_step: the recursive function can have several checkpoints.  This
      variable represents the current checkpoint (i.e, the next step in
      recursive function)
    locals: all other variables that need to be stored should be saved here.
  """

  def __init__(self, node):
    self.node = node
    self.next_step = TestListIterator.OnEnter.__name__
    self.locals = {}


class TestListIterator:
  """An iterator of test list.

  https://chromium.googlesource.com/chromiumos/platform/factory/+/HEAD/py/test/test_lists/JSON_TEST_LIST.md

  * The iterator will return the test to be run next when "next()" is called.
  * A status filter can be applied to skip some tests according to their states.
  * The iterator is loosely bind to FactoryTestList, that is you can change the
    test list object of the iterator.  If the iterator can find the last test it
    just returned, the iterator will continue on next test in the new test list.
    Otherwise, a StopIteration exception will be raised.
  * This object must implement pickle protocol to be able to save and reload by
    python shelve.
    (https://docs.python.org/2/library/pickle.html#pickle-protocol)

  The iterator will go through each test in the test list, starting from a given
  node in depth first search order.
  self.stack is the execution stack of the iterator.  Each element of self.stack
  is a PickableFrame object.

  For example, consider a test list like this:

  root (path='')
    A (path='a')
    G (path='G')
      B (path='G.b')
      H (path='G.H')
        C (path='G.H.c')

  If we start at root, then `self.stack = [Frame('')]` initially.  And the stack
  will become `self.stack = [Frame(''), Frame('G'), Frame('G.H'),
  Frame('G.H.c')]` when we reach test C.

  If we start at test G, then `self.stack = ['G']` initially.  And the stack
  will become `self.stack = [Frame('G'), Frame('G.H'), Frame('G.H.c')]` when we
  reach test C.

  TestListIterator implements the behavior of following depth first search
  function::

      def dfs(node):
        if not OnEnter(node):
          return
        while CheckContinue(node):
          Body(node)
        OnLeave(node)
  """

  Frame = PickableFrame

  _SERIALIZE_FIELDS = ('stack', 'status_filter', 'teardown_only')
  """fields in self.__dict__ that should be serialized."""

  RETURN_CODE = type_utils.Enum(
      ['POP_FRAME', 'NEW_FRAME', 'CONTINUE', 'RETURN'])
  """Represents how state transistion should be done to the state machine.

  Each transition function should return a tuple of (return_code, value).
  TestListIterator will call a transition function (decided by next_step of top
  frame) and receive a tuple.  And the TestListIterator will do the following
  according to the return_code:

  POP_FRAME: the top frame should be popped, `value` is ignored.  The state
    machine should try to make transition again.
  NEW_FRAME: a new frame is pushed according to `value`.  The state machine
    should try to make transition again.
  CONTINUE: don't push or pop a frame, just try to make another transition.
    `value` is ignored.
  RETURN: return `value`
  """

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
        updated by `SetTestList()` function.
    """
    self.stack = []
    self.test_list = test_list
    self.status_filter = status_filter or []
    self.teardown_only = False

    if isinstance(root, test_object.FactoryTest):
      self.Push(root.path)
    elif isinstance(root, str):
      self.Push(root)
    elif isinstance(root, test_list_module.ITestList):
      self.Push(root.path)
    elif root is None:
      self.stack = []
    else:
      raise ValueError(
          'root must be one of ITestList, FactoryTest, string or None '
          '(got %r)' % root)

  # define __getstate__ and __setstate__ to make this object pickable
  def __getstate__(self):
    return {key: self.__dict__[key] for key in self._SERIALIZE_FIELDS}

  def __setstate__(self, pickled_state):
    for key in self._SERIALIZE_FIELDS:
      self.__dict__[key] = pickled_state[key]
    self.test_list = None  # we didn't serialize the test_list, set it to None

  def Push(self, node):
    self.stack.append(self.Frame(node))

  def Pop(self):
    self.stack.pop()

  def Top(self):
    return self.stack[-1]

  def __next__(self):
    """Returns path to the test that should start now.

    The returned test could be a leaf factory test (factory test that does not
    have any subtests), or a parallel test (a factory test that has subtests but
    all of them will be run in parallel).

    Returns:
      a string the is the path of the test (use test_list.LookupPath(path) to
      get the real test object).
    """
    if not self.stack:
      raise StopIteration

    frame = self.Top()

    # check if frame.node is still a valid test in self.test_list
    if not self._GetTestFromFrame(frame):
      raise StopIteration

    func = getattr(self, frame.next_step)

    returncode, value = func()

    if returncode == self.RETURN_CODE.POP_FRAME:
      self.Pop()
      return next(self)
    if returncode == self.RETURN_CODE.NEW_FRAME:
      self.Push(value)
      return next(self)
    if returncode == self.RETURN_CODE.CONTINUE:
      return next(self)
    if returncode == self.RETURN_CODE.RETURN:
      return value
    raise AssertionError

  #####################
  # Exposed Functions #
  #####################
  def Get(self):
    """Get current test.

    Returns current test, which should be the same value returned by previous
    next() call.  If next() is never called before, the return value is
    undefined.
    """
    if not self.stack:
      return None
    test = self._GetTestFromFrame(self.Top())
    return test.path

  def SetTestList(self, test_list):
    """Set test list of iterator.

    Since we are not serializing test list when pickling TestListIterator, users
    need to invoke SetTestList to set current test list of the runner.
    """
    assert isinstance(test_list, test_list_module.ITestList)
    self.test_list = test_list

  def Stop(self, subtree_root=None):
    """Stops all tests under `subtree_root`.

    for example, a test list looks like:
    ''
      'G'
        'G.a'
        'G.b'
      'H'
        'H.b'

    when the TestListIterator is running 'G.a', and calling Stop('G'), the next
    test to run will be 'H.b'.
    """
    if subtree_root is None:
      subtree_root = ''

    if isinstance(subtree_root, str):
      subtree_root = self.test_list.LookupPath(subtree_root)

    while self.stack:
      test = self._GetTestFromFrame(self.Top())
      if test.HasAncestor(subtree_root):
        self.Pop()
      else:
        break

  def GetPendingTests(self):
    if not self.stack:
      return []
    root = self._GetTestFromFrame(self.stack[0])
    return [test.path for test in root.Walk() if test.IsLeaf()]

  def RestartLastTest(self):
    # if next step is not CheckContinue, then there are something wrong during
    # the shutdown / reboot process.  For example, the iterator state is not
    # properly written back to file system.  Or the system crashed during boot
    # up, thus the next_step is changed, but the active test is still shutdown
    # test.
    next_step = self.Top().next_step
    self.Top().next_step = self.Body.__name__
    if next_step != self.CheckContinue.__name__:
      return 'test_list_iterator: unexpected next_step %r' % next_step
    return None

  ###########################
  # State Machine Functions #
  ###########################
  def OnEnter(self):
    frame = self.Top()
    test = self._GetTestFromFrame(frame)

    if self.CheckSkip(test):
      return self.RETURN_CODE.POP_FRAME, None

    status = test.GetState().status
    if state == state.TestState.SKIPPED:
      raise ValueError('SKIPPED test should be skipped by `CheckSkip`')

    if (status == state.TestState.PASSED and
        self.status_filter and
        state.TestState.PASSED not in self.status_filter):
      # We are sure we don't need to run this again.
      return self.RETURN_CODE.POP_FRAME, None

    self._ResetIterations(test)
    frame.next_step = self.CheckContinue.__name__

    if test.IsTopLevelTest():
      # We definitely need to rerun everything.
      self._ResetSubtestStatus(test)

    return self.RETURN_CODE.CONTINUE, None

  def CheckContinue(self):
    frame = self.Top()
    test = self._GetTestFromFrame(frame)

    if frame.locals.get('executed', False):
      success = self._DetermineSuccess(test)
      if success:
        test.UpdateState(decrement_iterations_left=1)
      else:
        test_state = test.UpdateState(decrement_retries_left=1)
        if test_state.retries_left >= 0:
          # since you allow try, let's reset teardown_only flags
          self.teardown_only = False
          frame.locals.pop('teardown_only', None)

    test_state = test.GetState()
    if test_state.iterations_left > 0 and test_state.retries_left >= 0:
      # should continue
      frame.next_step = self.Body.__name__
      if frame.locals.get('executed', False):
        self._ResetSubtestStatus(test)
      return self.RETURN_CODE.CONTINUE, None
    # should not continue
    frame.next_step = self.OnLeave.__name__
    return self.RETURN_CODE.CONTINUE, None

  def Body(self):
    frame = self.Top()
    frame.locals['executed'] = True

    test = self._GetTestFromFrame(frame)

    if self._IsRunnableTest(test):
      frame.next_step = self.CheckContinue.__name__
      return self.RETURN_CODE.RETURN, test.path

    subtest = frame.locals.get('subtest', None)
    if subtest is None:
      next_subtest = test.subtests[0]
    else:
      subtest = self.test_list.LookupPath(subtest)
      next_subtest = subtest.GetNextSibling()

      # result of previous subtest
      success = self._DetermineSuccess(subtest)
      if not success:
        # create an alias
        ACTION_ON_FAILURE = test_object.FactoryTest.ACTION_ON_FAILURE
        if subtest.action_on_failure == ACTION_ON_FAILURE.NEXT:
          pass  # does nothing, just find the next test
        elif subtest.action_on_failure == ACTION_ON_FAILURE.PARENT:
          # stop executing normal tests under this test, only teardown tests can
          # be run.
          frame.locals['teardown_only'] = True
        elif subtest.action_on_failure == ACTION_ON_FAILURE.STOP:
          # stop executing normal tests under *root*, only teardown tests can be
          # run.
          frame.locals['teardown_only'] = True
          self.teardown_only = True

    while next_subtest:
      # if we can only run teardown tests, skip next_subtest until we find a
      # teardown test.
      if self.teardown_only or frame.locals.get('teardown_only', False):
        if not next_subtest.teardown:
          next_subtest = next_subtest.GetNextSibling()
          continue
      # okay, this is a valid test (any test when teardown_only == False,
      # teardown test when teardown_only == True).  Let's update local variable
      # and create a new frame (recursive call).
      frame.locals['subtest'] = next_subtest.path
      return self.RETURN_CODE.NEW_FRAME, next_subtest.path

    # no next subtest, go to CheckContinue to check if we need to run again
    frame.next_step = self.CheckContinue.__name__
    # unset local variable subtest
    frame.locals.pop('subtest', None)

    return self.RETURN_CODE.CONTINUE, None

  def OnLeave(self):
    # Before we leave current frame, if this is a group, we need to compute
    # overall status again.
    test = self._GetTestFromFrame(self.Top())
    test.UpdateStatusFromChildren()
    return self.RETURN_CODE.POP_FRAME, None

  ####################
  # Helper Functions #
  ####################
  def CheckSkip(self, test):
    # status filter only applies to leaf tests
    if (self._IsRunnableTest(test) and
        not self.CheckStatusFilter(test)):
      logging.debug('test %s is skipped because its status '
                    '%s (status_filter: %r)', test.path,
                    test.GetState().status, self.status_filter)
      return True  # we need to skip it
    if not self.CheckRunIf(test):
      logging.info('test %s is skipped because run_if evaluated to False',
                   test.path)
      test.Skip()
      return True  # we need to skip it
    if test.IsSkipped():
      need_retest = False
      # All of the subtests are either skipped or passed, let's check if all of
      # them are still skipped now.
      for t in test.Walk():
        if t.IsSkipped():
          # For test groups, they need retest if their run_if are set, and
          # evaluate to True.
          # For leaf tests, they need retest if their run_if are not set, or
          # evaluate to True.
          # (If run_if is not set, default return value of CheckRunIf is True).
          if self.CheckRunIf(t) and (t.IsLeaf() or t.run_if):
            need_retest = True
            break
      if need_retest:
        test.UpdateState(status=state.TestState.UNTESTED)
        # check again (for status filter)
        return self.CheckSkip(test)
      # this test is still skipped
      return True
    return False

  def CheckStatusFilter(self, test):
    if not self.status_filter:
      return True
    status = test.GetState().status
    # An active test should always pass the filter (to resume a previous test).
    # A skipped test should always pass the filter and let CheckSkip to decide.
    return (status == state.TestState.ACTIVE or
            status == state.TestState.SKIPPED or
            status in self.status_filter)

  def CheckRunIf(self, test):
    return test_list_module.ITestList.EvaluateRunIf(test, self.test_list)

  def _ResetIterations(self, test):
    test.UpdateState(iterations_left=test.iterations,
                     retries_left=test.retries,
                     shutdown_count=0)

  def _GetTestFromFrame(self, frame):
    """Returns test object corresponding to `frame`.

    :rtype: cros.factory.test.test_lists.test_object.FactoryTest
    """
    return self.test_list.LookupPath(frame.node)

  def _IsRunnableTest(self, test):
    return test.IsLeaf() or test.parallel

  def _DetermineSuccess(self, test):
    """Determines success / fail of a test.

    A test is considered fail iff. it really FAILED.  All other statuses
    (SKIPPED, FAILED_AND_WAIVED, UNTESTED) are not.
    """
    return test.GetState().status != state.TestState.FAILED

  def _ResetSubtestStatus(self, test):
    for subtest in test.Walk():
      subtest.UpdateState(status=state.TestState.UNTESTED)
