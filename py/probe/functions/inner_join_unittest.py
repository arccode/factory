#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

from cros.factory.probe import function
from cros.factory.probe.lib import probe_function
from cros.factory.utils.arg_utils import Arg


class InnerJoinFunctionTest(unittest.TestCase):
  class MockFunction(probe_function.ProbeFunction):
    ARGS = [Arg('data', (list, dict), 'The probed data.')]
    def Probe(self):
      return self.args.data

  class FailFunction(function.Function):
    def Apply(self, data):
      return function.NOTHING

  def setUp(self):
    function.RegisterFunction('mock', self.MockFunction, force=True)
    function.RegisterFunction('fail', self.FailFunction, force=True)

  def testInnerJoin(self):
    expected_value = [
        {'idx': '1', 'foo': 'FOO1', 'bar': 'BAR1'},
        {'idx': '3', 'foo': 'FOO3', 'bar': 'BAR3'}]
    func_expression = {
        'inner_join': {
            'index': 'idx',
            'functions': [
                {'mock': {'data': [
                    {'idx': '1', 'foo': 'FOO1'},
                    {'idx': '2', 'foo': 'FOO2'},
                    {'idx': '3', 'foo': 'FOO3'}]}},
                {'mock': {'data': [
                    {'idx': '1', 'bar': 'BAR1'},
                    {'idx': '3', 'bar': 'BAR3'}]}}]}}
    ret = function.InterpretFunction(func_expression)()
    self.assertEqual(sorted(ret, key=lambda d: sorted(d.items())),
                     sorted(expected_value, key=lambda d: sorted(d.items())))

    func_expression = {
        'inner_join': {
            'index': 'idx',
            'functions': [
                {'mock': {'data': [
                    {'idx': '1', 'foo': 'FOO1'},
                    {'idx': '2', 'foo': 'FOO2'},
                    {'idx': '3', 'foo': 'FOO3'}]}},
                'fail',
                {'mock': {'data': [
                    {'idx': '1', 'bar': 'BAR1'},
                    {'idx': '3', 'bar': 'BAR3'}]}}]}}
    ret = function.InterpretFunction(func_expression)()
    self.assertEqual(ret, function.NOTHING)


if __name__ == '__main__':
  unittest.main()
