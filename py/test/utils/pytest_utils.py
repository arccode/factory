# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import logging
import os
import re
import sys
import traceback
import unittest

from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


PYTESTS_RELPATH = os.path.join('py', 'test', 'pytests')

_PATTERNS = (
    r'^class .*\((unittest|test_case)\.TestCase\):',
    r'^\s+ARGS = '
)


def GetPytestList(base_dir):
  """Returns a sorted list of pytest relative paths."""

  def IsPytest(filepath):
    # We don't directly load the file by pytest_utils because it doesn't support
    # private overlays now.
    root, ext = os.path.splitext(filepath)
    if root.endswith('_unittest') or ext != '.py':
      return False
    content = file_utils.ReadFile(filepath)
    return any(re.search(p, content, re.MULTILINE) for p in _PATTERNS)

  res = []
  pytest_dir = os.path.join(base_dir, 'py', 'test', 'pytests')
  for dirpath, unused_dirnames, filenames in os.walk(pytest_dir):
    for basename in filenames:
      filepath = os.path.join(dirpath, basename)
      if IsPytest(filepath):
        res.append(os.path.relpath(filepath, pytest_dir))
  res.sort()
  return res


def LoadPytestModule(pytest_name):
  """Loads the given pytest module.

  This function tries to load the module

      :samp:`cros.factory.test.pytests.{pytest_name}`.

  Args:
    pytest_name: The name of the pytest module.

  Returns:
    The loaded pytest module object.
  """
  return __import__(
      'cros.factory.test.pytests.%s' % pytest_name, fromlist=[None])


def FindTestCase(pytest_module):
  """Find the TestCase class in the given module.

  There should be one and only one TestCase in the module.
  """
  # To simplify things, we only allow one TestCase per pytest, and the method
  # must be runTest.
  test_case_types = []
  for name in dir(pytest_module):
    obj = getattr(pytest_module, name)
    if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
      test_case_types.append(obj)

  if len(test_case_types) != 1:
    raise type_utils.TestFailure(
        'Only exactly one TestCase per pytest is supported, but found %r. '
        'Use test.AddTask if multiple tasks need to be done in a single pytest.'
        % test_case_types)

  return test_case_types[0]


def LoadPytest(pytest_name):
  """Load pytest type from pytest_name.

  See `LoadPytestModule` to know how pytest_name is resolved.  Also notice that
  there should be one and only one test case in each pytest.
  """
  return FindTestCase(LoadPytestModule(pytest_name))


def RelpathToPytestName(relpath):
  """Convert a pytest relpath to dotted pytest name."""
  return os.path.splitext(relpath)[0].replace('/', '.')


class IndirectException(Exception):
  @property
  def exception(self):
    return self.args[0]

  @property
  def traceback(self):
    return self.args[1]


class TestResult(unittest.TestResult):
  """Customized test result placeholder.

  Properties:
    failure_details: A list of pairs of the cought exceptions and their
        corresponding traceback objects.
  """
  def __init__(self):
    super(TestResult, self).__init__()
    self.failure_details = []

  def DumpStr(self):
    return '\n=====\n'.join(''.join(traceback.format_tb(tb)) + repr(exc)
                            for exc, tb in self.failure_details)

  def addError(self, test, err):
    super(TestResult, self).__init__(test, err)
    self._RecordFailureDetail(err)

  def addFailure(self, test, err):
    super(TestResult, self).__init__(test, err)
    self._RecordFailureDetail(err)

  def _RecordFailureDetail(self, err):
    unused_exc_type, exc, tb = err
    if isinstance(exc, IndirectException):
      tb = exc.traceback
      exc = exc.exception
    self.failure_details.append((exc, tb))


def RunTestCase(test_case):
  """Runs the given test case.

  This is the actual test case runner.  It runs the test case and returns the
  test results.

  Args:
    test_case: The test case to run.

  Returns:
    The test result of the test case.
  """
  logging.debug('[%s] Really run test case: %s', os.getpid(), test_case.id())
  result = TestResult()
  test_case.run(result)
  return result


PytestExceptionInfo = collections.namedtuple('PytestExceptionInfo',
                                             ['exc_repr', 'tb_list'])

class PytestExecutionResult:
  """A placeholder to record the execution result of a pytest.

  The class is designed to be pickle-serializable.  Please note that this
  class can't be defined in `py/test/pytest_runner.py` because that python
  module is also a stand-alone executable program.  When that program runs
  `pickle.dump`, the function will treat the this class as defined in the
  global scope, which is not true for the receiver (i.e. invocation.py).

  Properties:
    status: The test status.  See `cros.factory.test.state.TestState` for
        detail.
    failure_details: A list of `ExceptionInfo` instance.
  """

  def __init__(self, status, failures=None):
    """Constructor.

    Args:
      status: The test status.
      failure_details: A list of failures.  Each list item is a pair of
          the exception that causes the failure and the corresponding traceback.
    """
    self.status = status
    self.failures = failures or []

  @classmethod
  def GenerateFromTestResultFailureDetails(cls, status, failure_details):
    return cls(status, [PytestExceptionInfo(repr(e), traceback.extract_tb(t))
                        for e, t in failure_details])

  @classmethod
  def GenerateFromException(cls, status):
    unused_exc_type, exc, tb = sys.exc_info()
    return cls(status,
               [PytestExceptionInfo(repr(exc), traceback.extract_tb(tb))])
