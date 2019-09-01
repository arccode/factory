#!/usr/bin/env python2
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for e5071c_scpi module.

Currently, the test list covered some complicated logic on auxiliary
function only, in the future, we might want to use the e5071c_mock to
extend the test coverage as well.
"""
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.rf.e5071c_scpi import CheckTraceValid
from cros.factory.test.rf.e5071c_scpi import Interpolate

X_VALUES = [10, 10, 15, 18, 20, 20, 30, 30, 40]
Y_VALUES = [0.5, 0.7, 0.9, 1.2, 0.6, 0.7, 0.1, 1.1, 9.1]


class TestInterpolation(unittest.TestCase):

  def testInterpolateNormal(self):
    """Tests whether the Interpolate function works for query in range."""
    # Test cases for non-ambiguous situation.
    self.assertAlmostEqual(0.90, Interpolate(X_VALUES, Y_VALUES, 15))
    self.assertAlmostEqual(1.10, Interpolate(X_VALUES, Y_VALUES, 17))
    self.assertAlmostEqual(9.10, Interpolate(X_VALUES, Y_VALUES, 40))

    # Test cases for duplicated values presented in X_VALUES.
    self.assertAlmostEqual(0.50, Interpolate(X_VALUES, Y_VALUES, 10))
    self.assertAlmostEqual(0.78, Interpolate(X_VALUES, Y_VALUES, 12))
    self.assertAlmostEqual(0.90, Interpolate(X_VALUES, Y_VALUES, 19))
    self.assertAlmostEqual(0.40, Interpolate(X_VALUES, Y_VALUES, 25))
    self.assertAlmostEqual(6.70, Interpolate(X_VALUES, Y_VALUES, 37))

  def testInterpolateException(self):
    """Tests whether the Interpolate function raises exception as expected."""
    # Should fail in TraceValid function.
    self.assertRaises(ValueError, Interpolate, [10, 50], [0.1], 44)
    # Out of range exceptions.
    self.assertRaises(ValueError, Interpolate, X_VALUES, Y_VALUES, 5)
    self.assertRaises(ValueError, Interpolate, X_VALUES, Y_VALUES, 45)


class TestTraceValid(unittest.TestCase):

  def testCheckTraceValid(self):
    # Check whether x_values is empty.
    self.assertRaises(ValueError, CheckTraceValid, [], [])
    # Check whether x_values and values are not equal in length.
    self.assertRaises(ValueError, CheckTraceValid, [10, 20], [0.5])
    # Check whether x_values is not an increasing sequence.
    self.assertRaises(ValueError, CheckTraceValid, [10, 20, 19], [0, 0, 0])
    # Check for valid case
    CheckTraceValid([10, 50], [0, 1])

if __name__ == '__main__':
  unittest.main()
