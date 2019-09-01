#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.lib import probe_function
from cros.factory.utils import arg_utils
from cros.factory.utils.arg_utils import Arg


class InterpretFunctionTest(unittest.TestCase):
  class MockFunction(probe_function.ProbeFunction):
    ARGS = [
        Arg('key', str, 'The key of data.', default='default_key'),
        Arg('value', str, 'The value of data.')
    ]
    def Probe(self):
      return {self.args.key: self.args.value}

  def setUp(self):
    function.RegisterFunction('mock', self.MockFunction, force=True)

  def testInterpret(self):
    func = function.InterpretFunction({'mock': {'key': 'foo', 'value': 'bar'}})
    self.assertEquals(func.args.key, 'foo')
    self.assertEquals(func.args.value, 'bar')

  def testWrongFunction(self):
    with self.assertRaisesRegexp(
        function.FunctionException,
        'Function "NOT_EXISTED" is not registered.'):
      function.InterpretFunction({'NOT_EXISTED': {}})

  def testWrongArgument(self):
    with self.assertRaisesRegexp(
        function.FunctionException,
        'Invalid argument: .* should be string or dict.'):
      function.InterpretFunction({'mock': ['key', 'foo']})
    with self.assertRaisesRegexp(
        arg_utils.ArgError, 'Required argument value not specified'):
      function.InterpretFunction({'mock': {'key': 'foo'}})
    with self.assertRaisesRegexp(
        arg_utils.ArgError, r"Extra arguments \['extra'\]"):
      function.InterpretFunction(
          {'mock': {'key': 'foo', 'value': 'FOO', 'extra': 'lala'}})

  def testWrongStringArgument(self):
    class MockFunction(function.Function):
      ARGS = [
          Arg('key1', str, 'help string'),
          Arg('key2', str, 'help string')
      ]
      def Apply(self, data):
        pass
    function.RegisterFunction('mock', MockFunction, force=True)

    with self.assertRaisesRegexp(
        function.FunctionException,
        r"Function .* requires more than one argument: \['key1', 'key2'\]"):
      function.InterpretFunction({'mock': 'foo'})

  def testSyntaxSuger(self):
    # A function containing only one argument with default value.
    class MockFunction(function.Function):
      ARGS = [
          Arg('value', str, 'The value of data.', default='DATA')
      ]
      def Apply(self, data):
        pass
    function.RegisterFunction('mock', MockFunction, force=True)

    func = function.InterpretFunction({'mock': {'value': 'bar'}})
    self.assertEquals(func.args.value, 'bar')
    func = function.InterpretFunction({'mock': 'bar'})
    self.assertEquals(func.args.value, 'bar')
    func = function.InterpretFunction('mock:bar')
    self.assertEquals(func.args.value, 'bar')
    func = function.InterpretFunction('mock')
    self.assertEquals(func.args.value, 'DATA')


class UtilTest(unittest.TestCase):
  # pylint: disable=protected-access
  def testLoadFunctions(self):
    function.LoadFunctions()
    self.assertIn('file', function._function_map)
    # Should not raise exception while loading twice.
    self.assertIsNone(function.LoadFunctions())

  def testRegisterFunction(self):
    with self.assertRaisesRegexp(function.FunctionException, ''):
      function.RegisterFunction('object', object)

  def testRegisterTwice(self):
    class TestFunction(function.Function):
      def Apply(self, data):
        pass
    function.RegisterFunction('TEST', TestFunction)
    with self.assertRaisesRegexp(
        function.FunctionException, 'Function "TEST" is already registered.'):
      function.RegisterFunction('TEST', TestFunction)


if __name__ == '__main__':
  unittest.main()
