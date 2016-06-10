# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""End-to-end test framework."""

import inspect
import threading
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.goofy import invocation
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test.e2e_test import ui_actuator
from cros.factory.utils.arg_utils import Args


class E2ETestError(Exception):
  """E2E test error."""
  pass


class E2ETestMetaclass(type):
  """A metaclass for setting up args for E2E tests."""
  def __init__(cls, name, bases, attrs):
    """Initializes the ARGS attribute of a E2ETest subclass.

    Scans through all the TestCase classes in the module specified by
    pytest_name and look for one that has the ARGS attribute.  The found ARGS
    attribute is set to the E2ETest subclass.
    """
    if (getattr(cls, 'pytest_name', None) and not getattr(cls, 'ARGS', None)):
      module = invocation.LoadPytestModule(cls.pytest_name)
      cls.pytest_module = module

      for name, obj in module.__dict__.iteritems():
        if (inspect.isclass(obj) and
            issubclass(obj, unittest.TestCase)):
          args_list = getattr(obj, 'ARGS', None)
          if args_list:
            if cls.ARGS:
              raise E2ETestError(
                  'Only one TestCase subclass with ARGS attribute is allowed '
                  'in a pytest')
            cls.ARGS = args_list
    super(E2ETestMetaclass, cls).__init__(name, bases, attrs)


class E2ETest(unittest.TestCase):
  """The base E2ETest class.

  E2E test can be used to test factory tests.  An E2E test may contain several
  test cases.  When being executed, the E2E test starts each test case in a
  clean process and invoked the factory test in a separate daemon thread.

  This class provides basic APIs to start a factory test and to wait and verify
  its state.  An E2E test for a factory test should inherit this class, assign
  pytest_name, and use these APIs in their test cases.

  Properties:
    pytest_name: The name of the factory test to test.
    pytest_module: The loaded Python module of the factory test.  This is set by
      E2ETest's metaclass.
    uictl: The UI actuator that can be used to interact with the UI of the
      factory test.  This is initialized by _InitFactoryTest().
    pytest_thread: The thread that runs the factory test.  This is initialized
      by _InitFactoryTest().
    pytest_state: The test state of the factory test.
  """
  __metaclass__ = E2ETestMetaclass

  # The name of the factory test to test.
  pytest_name = None
  # Set by metaclass.
  pytest_module = None
  # The UI actuator.
  uictl = None
  # The thread that starts the factory test process.
  pytest_thread = None
  # Internal variable to store factory test state.
  pytest_state = None

  # Placeholder for the factory test's ARGS spec.
  ARGS = None
  # Failure messages of pytest_thread.
  _pytest_failures = []
  # Is the pytest thread started?
  _pytest_thread_started = False

  def _InitFactoryTest(self, dargs=None):
    """Initializes the thread that runs the factory test.

    Args:
      dargs: A dict of override dargs to pass to the factory test.  This
        overrides the default dargs specified in E2ETest.dargs (for E2E tests)
        or in test list (for automators).
    """
    def FactoryTestThreadInit():
      runner = unittest.TextTestRunner()
      suite = unittest.TestLoader().loadTestsFromModule(self.pytest_module)

      # Recursively set test info and dargs.
      def SetTestInfo(test):
        if isinstance(test, unittest.TestCase):
          test.test_info = self.test_info
          test.args = self.args
        elif isinstance(test, unittest.TestSuite):
          for x in test:
            SetTestInfo(x)

      SetTestInfo(suite)
      self.pytest_state = factory.TestState.ACTIVE
      result = runner.run(suite)

      self._pytest_failures += (
          result.failures + result.errors + test_ui.exception_list)
      if self._pytest_failures:
        self.pytest_state = factory.TestState.FAILED
      else:
        self.pytest_state = factory.TestState.PASSED

    # Update dargs with override dargs.
    if not getattr(self, 'args', None):
      args_dict = {}
    else:
      # Convert 'Dargs' object to dict. 'Dargs' object is created by
      # Args.Parse(). It is what we get if the the args object were created
      # through the 'ARGS' attribute of E2ETest class.
      args_dict = self.args.ToDict()    # pylint: disable=E0203

    # Set the dargs values of the E2E test as the default args.
    e2e_default_args = getattr(self, 'dargs', {})
    args_dict.update(e2e_default_args)

    # Override args with the dargs argumnet passed in.
    override_args = dargs or {}
    args_dict.update(override_args)
    self.args = Args(*self.ARGS).Parse(args_dict)   # pylint: disable=W0201

    self.pytest_thread = threading.Thread(target=FactoryTestThreadInit)
    self.pytest_thread.daemon = True
    self.uictl = ui_actuator.UIActuator(self)

  def StartFactoryTest(self):
    """Starts the factory test."""
    if not self._pytest_thread_started:
      self.pytest_thread.start()
      self._pytest_thread_started = True

  def WaitForFactoryTest(self, timeout_secs, raise_exception=True):
    """Waits for the factory test to finish.

    Args:
      timeout_secs: Timeout in seconds.
      raise_exception: True to raise exception if factory test does not finish
        in time.
    """
    self.StartFactoryTest()

    if not self.pytest_thread:
      raise E2ETestError('No factory test is running')

    self.pytest_thread.join(timeout_secs)
    if self.pytest_thread.isAlive():
      if raise_exception:
        raise E2ETestError('Factory test did not finish in %d seconds' %
                           timeout_secs)

  def WaitTestStateEquals(self, state, timeout_secs=5, msg=None):
    """Waits until the test state equals to the given state.

    The test fails if the state is not correct within the given amount of time.

    Args:
      state: The test state to compare.
      timeout_secs: If not None, wait for at most timeout_secs for the factory
        test to finish.
      msg: A message to include in the error message if the function fails.
    """
    self.StartFactoryTest()

    if state not in factory.TestState.__dict__:
      raise E2ETestError('Invalid test state: %r' % state)
    if timeout_secs:
      self.WaitForFactoryTest(timeout_secs, raise_exception=False)

    failure_msg = '\n'.join(trace for _, trace in self._pytest_failures)
    if msg:
      result_msg = '\n'.join([msg, failure_msg])
    else:
      result_msg = failure_msg

    self.assertEquals(state, self.pytest_state, result_msg)

  def WaitForPass(self, timeout_secs=5, msg=None):
    """Waits until the test state is passed.

    Args:
      timeout_secs: If not None, wait for at most timeout_secs for the factory
        test to finish.
      msg: A message to display if the function fails.
    """
    self.WaitTestStateEquals(factory.TestState.PASSED,
                             timeout_secs=timeout_secs,
                             msg=msg)

  def WaitForFail(self, timeout_secs=5, msg=None):
    """Waits until the test state is failed.

    Args:
      timeout_secs: If not None, wait for at most timeout_secs for the factory
        test to finish.
      msg: A message to display if the function fails.
    """
    self.WaitTestStateEquals(factory.TestState.FAILED,
                             timeout_secs=timeout_secs,
                             msg=msg)

  def WaitForActive(self, timeout_secs=5, msg=None):
    """Waits and checks that the test state is active.

    Args:
      timeout_secs: If not None, wait for at most timeout_secs for the factory
        test to finish.
      msg: A message to display if the function fails.
    """
    self.WaitTestStateEquals(factory.TestState.ACTIVE,
                             timeout_secs=timeout_secs,
                             msg=msg)


def E2ETestCase(dargs=None):
  """Decorator generator to perform common works for an E2E test case.

  The decorator modifies kwargs to create the arguments for calling
  StartFactoryTest().  When being executed, the decorator creates and starts the
  factory test in another process, and sets up a UI actuator instance and binds
  the instance to self.ui.  Users can use self.ui directly to interact with the
  factory test front-end.

  Args:
    dargs: The dargs to the factory test.  This is directly passed to
      StartFactoryTest(), which in turn uses it to update the default dargs.

  Returns:
    A decorator to wrap up an E2E test case.
  """
  def Decorator(test_case_function):
    # We must go deeper...
    def WrappedTestCaseFunction(self):
      self._InitFactoryTest(dargs)    # pylint: disable=W0212
      test_case_function(self)

    return WrappedTestCaseFunction

  return Decorator
