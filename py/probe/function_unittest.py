#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mock
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils import arg_utils
from cros.factory.utils.arg_utils import Arg


class ProbeFunctionTest(unittest.TestCase):
  class MockProbeFunction(function.ProbeFunction):
    def Probe(self):
      return {'result': 'FOO'}

  class MockProbeFunction2(function.ProbeFunction):
    def Probe(self):
      return [{'result': 'FOO1'}, {'result': 'FOO2'}]

  def testProbeFunction(self):
    """Probe function returns a dict."""
    func = self.MockProbeFunction()
    self.assertEquals(func(function.INITIAL_DATA), [{'result': 'FOO'}])
    self.assertEquals(func([{'other': 'BAR'}]),
                      [{'result': 'FOO', 'other': 'BAR'}])
    self.assertEquals(func([{'other': 'BAR1'},
                            {'other': 'BAR2'}]),
                      [{'result': 'FOO', 'other': 'BAR1'},
                       {'result': 'FOO', 'other': 'BAR2'}])

  def testProbeFunctionWithList(self):
    """Probe function returns a list of dict."""
    func = self.MockProbeFunction2()
    self.assertEquals(func(function.INITIAL_DATA),
                      [{'result': 'FOO1'}, {'result': 'FOO2'}])
    self.assertEquals(func([{'other': 'BAR1'},
                            {'other': 'BAR2'}]),
                      [{'result': 'FOO1', 'other': 'BAR1'},
                       {'result': 'FOO1', 'other': 'BAR2'},
                       {'result': 'FOO2', 'other': 'BAR1'},
                       {'result': 'FOO2', 'other': 'BAR2'}])

  def testNotProbeWhenFail(self):
    func = self.MockProbeFunction()
    func.Probe = mock.MagicMock()
    ret = func(function.NOTHING)
    func.Probe.assert_not_called()
    self.assertEquals(ret, function.NOTHING)


class ActionFunctionTest(unittest.TestCase):
  def setUp(self):
    self.func = function.ActionFunction()

  def testCall(self):
    self.func.Action = mock.MagicMock(return_value=True)
    ret = self.func(function.INITIAL_DATA)
    self.func.Action.assert_called_once_with()
    self.assertEquals(ret, function.INITIAL_DATA)

  def testNotCall(self):
    self.func.Action = mock.MagicMock(return_value=True)
    ret = self.func(function.NOTHING)
    self.func.Action.assert_not_called()
    self.assertEquals(ret, function.NOTHING)

  def testCallFail(self):
    self.func.Action = mock.MagicMock(return_value=False)
    ret = self.func([{}])
    self.func.Action.assert_called_once_with()
    self.assertEquals(ret, function.NOTHING)


class InterpretFunctionTest(unittest.TestCase):
  class MockFunction(function.ProbeFunction):
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
    self.assertEquals(func(), [{'foo': 'bar'}])

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
    expected_value = [{'default_key': 'bar'}]
    func = function.InterpretFunction({'mock': {'value': 'bar'}})
    self.assertEquals(func(), expected_value)
    func = function.InterpretFunction({'mock': 'bar'})
    self.assertEquals(func(), expected_value)
    func = function.InterpretFunction('mock:bar')
    self.assertEquals(func(), expected_value)


class InterpretCombinationFunctionTest(unittest.TestCase):
  class MockFunction(function.ProbeFunction):
    ARGS = [Arg('data', (list, dict), 'The probed data.')]
    def Probe(self):
      return self.args.data

  class FailFunction(function.Function):
    def Apply(self, data):
      return function.NOTHING

  def setUp(self):
    function.RegisterFunction('mock', self.MockFunction, force=True)
    function.RegisterFunction('fail', self.FailFunction, force=True)

  def testSequence(self):
    expected_value = [{'foo': 'FOO', 'bar': 'BAR'}]
    func_expression = {
        'sequence': {
            'functions': [
                {'mock': {'data': {'foo': 'FOO'}}},
                {'mock': {'data': {'bar': 'BAR'}}}]}}
    expected_value = [{'foo': 'FOO', 'bar': 'BAR'}]
    ret = function.InterpretFunction(func_expression)()
    self.assertEquals(ret, expected_value)

    # Syntax sugar
    func_expression = [
        {'mock': {'data': {'foo': 'FOO'}}},
        {'mock': {'data': {'bar': 'BAR'}}}]
    ret = function.InterpretFunction(func_expression)()
    self.assertEquals(ret, expected_value)

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
    self.assertEquals(ret, expected_value)

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
    self.assertEquals(ret, function.NOTHING)


class UtilTest(unittest.TestCase):
  # pylint: disable=protected-access
  def testLoadFunctions(self):
    self.assertNotIn('file', function._function_map)
    function.LoadFunctions()
    self.assertIn('file', function._function_map)

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
