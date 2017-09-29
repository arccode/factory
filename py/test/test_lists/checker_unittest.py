#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import factory
from cros.factory.test.test_lists import checker
from cros.factory.test.test_lists import manager
from cros.factory.test.test_lists import test_object
from cros.factory.utils import arg_utils


class CheckerTest(unittest.TestCase):
  def setUp(self):
    self.checker = checker.Checker()

  def testAssertValidEval(self):
    expression = 'while True: a = a + 3'
    with self.assertRaises(checker.CheckerError):
      self.checker.AssertValidEval(expression)

    expression = 'dut.info.serial_number + station.var + abs(options.value)'
    self.checker.AssertValidEval(expression)

    expression = '[(a, d, c) for a in dut.arr for c in a for d in c]'
    self.checker.AssertValidEval(expression)

    expression = '[(a, d, c) for a in dut.arr for d in c for c in a]'
    # failed because c is used before define
    with self.assertRaises(checker.CheckerError):
      self.checker.AssertValidEval(expression)

    expression = '{k: str(k) for k in dut.arr}'
    self.checker.AssertValidEval(expression)

    expression = '{k: v for (k, v) in dut.dct.itertiems() if v}'
    self.checker.AssertValidEval(expression)

    expression = '(x * x for x in xrange(3))'
    # generator is not allowed
    with self.assertRaises(checker.CheckerError):
      self.checker.AssertValidEval(expression)

    expression = '({x for x in [1]}, x)'
    # the second x is not defined
    with self.assertRaises(checker.CheckerError):
      self.checker.AssertValidEval(expression)

    expression = '[([y for y in [x]], x) for x in [1]]'
    self.checker.AssertValidEval(expression)

  def testAssertValidRunIf(self):
    expression = 'dut.info.serial_number + station.var + abs(options.value)'
    with self.assertRaises(checker.CheckerError):
      self.checker.AssertValidRunIf(expression)
    expression = 'device.serials.serial_number + constants.foo.bar'
    self.checker.AssertValidRunIf(expression)

  def testCheckArgsType(self):
    constants = {
        'foo': 'FOO',
        'bar': 'BAR',
    }
    test = test_object.FactoryTest(
        pytest_name='message',
        dargs={
            'html': 'eval! constants.foo + constants.bar',
            'text_size': 'eval! dut.CheckOutput("bc 1 + 1")', })
    options = factory.Options()
    test_list = test_object.FactoryTestList(
        subtests=[test], state_instance=None,
        test_list_id='main', constants=constants, options=options)
    test_list = manager.LegacyTestList(test_list, self.checker)

    expected_args = {
        'html': 'FOOBAR',
        'text_size': checker.UnresolvableException,
    }

    resolved_args = self.checker.StaticallyResolveTestArgs(test, test_list)
    for key, expected_value in expected_args.iteritems():
      if expected_value == checker.UnresolvableException:
        self.assertEqual(resolved_args[key].eval_string, test.dargs[key])
      else:
        self.assertEqual(resolved_args[key], expected_value)

    self.checker.CheckArgsType(test, test_list)

  def testCheckArgsTypeInvalidArgs(self):
    constants = {
        'foo': 'FOO',
        'bar': 'BAR',
    }
    test = test_object.FactoryTest(
        pytest_name='message',
        dargs={
            'html': 'eval! constants.foo + constants.bar + ', })
    options = factory.Options()
    test_list = test_object.FactoryTestList(
        subtests=[test], state_instance=None,
        test_list_id='main', constants=constants, options=options)
    test_list = manager.LegacyTestList(test_list, self.checker)

    with self.assertRaises(checker.CheckerError):
      self.checker.CheckArgsType(test, test_list)

    test.dargs['html'] = 'eval! constants.foo + 1'
    with self.assertRaises(TypeError):
      self.checker.CheckArgsType(test, test_list)

    test.dargs['html'] = 'valid string'
    test.dargs['seconds'] = 'invalid string'
    with self.assertRaises(arg_utils.ArgError):
      self.checker.CheckArgsType(test, test_list)


if __name__ == '__main__':
  unittest.main()
