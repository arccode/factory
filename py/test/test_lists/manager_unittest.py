#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mock
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.test_lists import manager


class CheckerTest(unittest.TestCase):
  def setUp(self):
    self.manager = mock.MagicMock(manager.Manager)
    self.checker = manager.Checker(self.manager)

  def testAssertExpressionIsValid(self):
    expression = 'while True: a = a + 3'
    with self.assertRaises(manager.CheckerError):
      self.checker.AssertExpressionIsValid(expression)

    expression = 'dut.info.serial_number + station.var + abs(options.value)'
    self.checker.AssertExpressionIsValid(expression)

    expression = '[(a, d, c) for a in dut.arr for c in a for d in c]'
    self.checker.AssertExpressionIsValid(expression)

    expression = '[(a, d, c) for a in dut.arr for d in c for c in a]'
    # failed because c is used before define
    with self.assertRaises(manager.CheckerError):
      self.checker.AssertExpressionIsValid(expression)

    expression = '{k: str(k) for k in dut.arr}'
    self.checker.AssertExpressionIsValid(expression)

    expression = '{k: v for (k, v) in dut.dct.itertiems() if v}'
    self.checker.AssertExpressionIsValid(expression)

    expression = '(x * x for x in xrange(3))'
    # generator is not allowed
    with self.assertRaises(manager.CheckerError):
      self.checker.AssertExpressionIsValid(expression)

    expression = '({x for x in [1]}, x)'
    # the second x is not defined
    with self.assertRaises(manager.CheckerError):
      self.checker.AssertExpressionIsValid(expression)

    expression = '[([y for y in [x]], x) for x in [1]]'
    self.checker.AssertExpressionIsValid(expression)


if __name__ == '__main__':
  unittest.main()
