#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import common
from cros.factory.probe import function
from cros.factory.utils.arg_utils import Arg


class EvaluateStatementTest(unittest.TestCase):
  class MockFunction(function.Function):
    ARGS = [Arg('data', list, 'help message')]
    def Apply(self, data):
      return self.args.data

  def setUp(self):
    function.RegisterFunction('mock', self.MockFunction, force=True)

  def testNormal(self):
    results = common.EvaluateStatement(
        {'eval': {'mock': {'data': [{'foo': 'FOO1', 'bar': 'BAR1'},
                                    {'foo': 'FOO2', 'bar': 'BAR2'}]}},
         'expect': {'foo': 'FOO1'}})
    self.assertEquals(results, [{'values': {'foo': 'FOO1', 'bar': 'BAR1'}}])

  def testNormalWithKeys(self):
    results = common.EvaluateStatement(
        {'eval': {'mock': {'data': [{'foo': 'FOO1', 'bar': 'BAR1'},
                                    {'foo': 'FOO2', 'bar': 'BAR2'}]}},
         'expect': {'foo': 'FOO1'},
         'keys': ['foo']})
    self.assertEquals(results, [{'values': {'foo': 'FOO1'}}])

  def testNormalWithApproxMatch(self):
    results = common.EvaluateStatement(
        {'eval': {'mock': {'data': [{'foo': 'FOO1', 'bar': 'BAR1'},
                                    {'foo': 'FOO2', 'bar': 'BAR2'}]}},
         'expect': {'foo': 'FOO1', 'bar': 'BAR2'}},
        approx_match=True,
        max_mismatch=1)
    self.assertEqual(len(results), 2)


if __name__ == '__main__':
  unittest.main()
