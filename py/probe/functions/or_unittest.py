#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.lib import probe_function
from cros.factory.utils.arg_utils import Arg


class OrFunctionTest(unittest.TestCase):
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

  def testOr(self):
    func_expression = {
        'or': {
            'functions': [
                {'fail': {}},
                {'mock': {'data': {'foo': 'FOO'}}},
                {'mock': {'data': {'bar': 'BAR'}}}]}}
    expected_value = [{'foo': 'FOO'}]
    ret = function.InterpretFunction(func_expression)()
    self.assertEquals(ret, expected_value)

    func_expression = {
        'or': {
            'functions': [
                {'mock': {'data': {'foo': 'FOO'}}},
                {'fail': {}},
                {'mock': {'data': {'bar': 'BAR'}}}]}}
    expected_value = [{'foo': 'FOO'}]
    ret = function.InterpretFunction(func_expression)()
    self.assertEquals(ret, expected_value)

    func_expression = {
        'or': {
            'functions': [
                {'fail': {}},
                {'fail': {}}]}}
    ret = function.InterpretFunction(func_expression)()
    self.assertEquals(ret, function.NOTHING)


if __name__ == '__main__':
  unittest.main()
