# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import re
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


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
