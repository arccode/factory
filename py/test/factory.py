# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common types and routines for factory test infrastructure.

This library provides common types and routines for the factory test
infrastructure. This library explicitly does not import gtk, to
allow its use by the autotest control process.
"""

from __future__ import print_function

import factory_common  # pylint: disable=unused-import
from cros.factory.test import session
from cros.factory.utils import type_utils


# TODO(hungte) Remove this when everyone is using new location session.console.
console = session.console


class TestState(object):
  """The complete state of a test.

  Properties:
    status: The status of the test (one of ACTIVE, PASSED, FAILED, or UNTESTED).
    count: The number of times the test has been run.
    error_msg: The last error message that caused a test failure.
    shutdown_count: The number of times the test has caused a shutdown.
    invocation: The currently executing invocation.
    iterations_left: For an active test, the number of remaining iterations
        after the current one.
    retries_left: Maximum number of retries allowed to pass the test.
  """
  ACTIVE = 'ACTIVE'
  PASSED = 'PASSED'
  FAILED = 'FAILED'
  UNTESTED = 'UNTESTED'
  FAILED_AND_WAIVED = 'FAILED_AND_WAIVED'
  SKIPPED = 'SKIPPED'

  def __init__(self, status=UNTESTED, count=0, error_msg=None,
               shutdown_count=0, invocation=None, iterations_left=0,
               retries_left=0):
    self.status = status
    self.count = count
    self.error_msg = error_msg
    self.shutdown_count = shutdown_count
    self.invocation = invocation
    self.iterations_left = iterations_left
    self.retries_left = retries_left

  def __repr__(self):
    return type_utils.StdRepr(self)

  def update(self, status=None, increment_count=0, error_msg=None,
             shutdown_count=None, increment_shutdown_count=0,
             invocation=None,
             decrement_iterations_left=0, iterations_left=None,
             decrement_retries_left=0, retries_left=None):
    """Updates the state of a test.

    Args:
      status: The new status of the test.
      increment_count: An amount by which to increment count.
      error_msg: If non-None, the new error message for the test.
      shutdown_count: If non-None, the new shutdown count.
      increment_shutdown_count: An amount by which to increment shutdown_count.
      invocation: The currently executing or last invocation, if any.
      iterations_left: If non-None, the new iterations_left.
      decrement_iterations_left: An amount by which to decrement
          iterations_left.
      retries_left: If non-None, the new retries_left.
          The case retries_left = -1 means the test had already used the first
          try and all the retries.
      decrement_retries_left: An amount by which to decrement retries_left.

    Returns:
      True if anything was changed.
    """
    old_dict = dict(self.__dict__)

    if status:
      self.status = status
    if error_msg is not None:
      self.error_msg = error_msg
    if shutdown_count is not None:
      self.shutdown_count = shutdown_count
    if iterations_left is not None:
      self.iterations_left = iterations_left
    if retries_left is not None:
      self.retries_left = retries_left

    if invocation is not None:
      self.invocation = invocation

    self.count += increment_count
    self.shutdown_count += increment_shutdown_count
    self.iterations_left = max(
        0, self.iterations_left - decrement_iterations_left)
    # If retries_left is 0 after update, it is the usual case, so test
    # can be run for the last time. If retries_left is -1 after update,
    # it had already used the first try and all the retries.
    self.retries_left = max(
        -1, self.retries_left - decrement_retries_left)

    return self.__dict__ != old_dict

  @classmethod
  def from_dict_or_object(cls, obj):
    if isinstance(obj, dict):
      return TestState(**obj)
    else:
      assert isinstance(obj, TestState), type(obj)
      return obj

  def __eq__(self, other):
    return all(getattr(self, attr) == getattr(other, attr)
               for attr in self.__dict__)

  def ToStruct(self):
    result = dict(self.__dict__)
    for key in ['retries_left', 'iterations_left']:
      if result[key] == float('inf'):
        result[key] = -1
    return result


def overall_status(statuses):
  """Returns the "overall status" given a list of statuses.

  This is the first element of

    [ACTIVE, FAILED, UNTESTED, FAILED_AND_WAIVED, PASSED]

  (in that order) that is present in the status list.
  """
  status_set = set(statuses)
  for status in [TestState.ACTIVE, TestState.FAILED,
                 TestState.UNTESTED, TestState.FAILED_AND_WAIVED,
                 TestState.SKIPPED, TestState.PASSED]:
    if status in status_set:
      return status

  # E.g., if statuses is empty
  return TestState.UNTESTED


class FactoryTestFailure(Exception):
  """Failure of a factory test."""
