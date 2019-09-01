#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.lib import probe_function
from cros.factory.utils.arg_utils import Arg


class ConcatFunctionTest(unittest.TestCase):
  class MockFunction(probe_function.ProbeFunction):
    ARGS = [Arg('data', (list, dict), 'The probed data.')]
    def Probe(self):
      return self.args.data

  class FailFunction(function.Function):
    def Apply(self, data):
      return 0

  def setUp(self):
    function.RegisterFunction('mock', self.MockFunction, force=True)
    function.RegisterFunction('fail', self.FailFunction, force=True)

  def testConcat(self):
    expected_value = [{'foo': 'FOO'}, {'bar': 'BAR'}]
    func_expression = {
        'concat': {
            'functions': [
                {'mock': {'data': [{'foo': 'FOO'}]}},
                {'mock': {'data': [{'bar': 'BAR'}]}}]}}
    ret = function.InterpretFunction(func_expression)()
    self.assertEquals(ret, expected_value)

  def testConcatFail(self):
    func_expression = {
        'concat': {
            'functions': [
                {'mock': {'data': [{'foo': 'FOO'}]}},
                'fail']}}
    self.assertRaises(TypeError,
                      function.InterpretFunction(func_expression).Apply,
                      function.INITIAL_DATA)


if __name__ == '__main__':
  unittest.main()
