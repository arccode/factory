#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re
import unittest

from cros.factory.probe.runtime_probe import probe_config_types
from cros.factory.utils import json_utils


class ProbeStatementDefinitionBuilderTest(unittest.TestCase):
  def testBuildProbeStatementDefinition(self):
    builder = probe_config_types.ProbeStatementDefinitionBuilder('category_x')
    builder.AddProbeFunction('func_1', 'This is func 1.')
    builder.AddProbeFunction('func2', 'This is func 2.')
    builder.AddIntOutputField('field1', 'This is field1')
    builder.AddStrOutputField('field2', 'This is field2')
    builder.AddHexOutputField('field3', 'This is field3')
    builder.AddIntOutputField('field_only_func1',
                              'This is field ?',
                              probe_function_names=['func_1'])
    d = builder.Build()
    self.assertEqual(d.category_name, 'category_x')
    self.assertCountEqual(list(d.expected_fields.keys()),
                          ['field1', 'field2', 'field3', 'field_only_func1'])
    self.assertCountEqual(list(d.probe_functions.keys()), ['func_1', 'func2'])
    self.assertCountEqual(
        [f.name for f in d.probe_functions['func_1'].output_fields],
        ['field1', 'field2', 'field3', 'field_only_func1'])
    self.assertCountEqual(
        [f.name for f in d.probe_functions['func2'].output_fields],
        ['field1', 'field2', 'field3'])


class ConcreteProbeStatementDefinitionTestBase(unittest.TestCase):
  def setUp(self):
    builder = probe_config_types.ProbeStatementDefinitionBuilder('category_x')
    builder.AddProbeFunction('func_1', 'This is func 1.')
    builder.AddProbeFunction('func2', 'This is func 2.')
    builder.AddIntOutputField('int_field', '')
    builder.AddStrOutputField('str_field', '')
    builder.AddStrOutputField('str_field_started_with_a',
                              '',
                              value_pattern=re.compile('a.*'))
    builder.AddHexOutputField('hex_field', '')
    builder.AddHexOutputField('hex_field_three_digits', '', num_value_digits=3)
    self.probe_statement_definition = builder.Build()


class ProbeStatementDefinitionTest(ConcreteProbeStatementDefinitionTestBase):
  def _GenerateExpectResult(self, comp_name, func_name, expect_field):
    return {
        'category_x': {
            comp_name: {
                'eval': {
                    func_name: {}
                },
                'expect': expect_field
            }
        }
    }

  def testGenerateProbeStatementNoField(self):
    result = self.probe_statement_definition.GenerateProbeStatement(
        'comp_1', 'func_1', {})
    self.assertEqual(result,
                     self._GenerateExpectResult('comp_1', 'func_1', {}))

  def testGenerateProbeStatementIntField(self):
    result = self.probe_statement_definition.GenerateProbeStatement(
        'comp_1', 'func_1', {'int_field': None})
    self.assertEqual(
        result,
        self._GenerateExpectResult('comp_1', 'func_1',
                                   {'int_field': [False, 'int']}))

    result = self.probe_statement_definition.GenerateProbeStatement(
        'comp_1', 'func_1', {'int_field': 3})
    self.assertEqual(
        result,
        self._GenerateExpectResult('comp_1', 'func_1',
                                   {'int_field': [True, 'int', '!eq 3']}))

  def testGenerateProbeStatementStrField(self):
    result = self.probe_statement_definition.GenerateProbeStatement(
        'comp_1', 'func_1', {'str_field': None})
    self.assertEqual(
        result,
        self._GenerateExpectResult('comp_1', 'func_1',
                                   {'str_field': [False, 'str']}))

    result = self.probe_statement_definition.GenerateProbeStatement(
        'comp_1', 'func_1', {'str_field': 'sss'})
    self.assertEqual(
        result,
        self._GenerateExpectResult('comp_1', 'func_1',
                                   {'str_field': [True, 'str', '!eq sss']}))

    result = self.probe_statement_definition.GenerateProbeStatement(
        'comp_1', 'func_1', {'str_field_started_with_a': 'a_value'})
    self.assertEqual(
        result,
        self._GenerateExpectResult(
            'comp_1', 'func_1',
            {'str_field_started_with_a': [True, 'str', '!eq a_value']}))
    with self.assertRaises(ValueError):  # format error
      self.probe_statement_definition.GenerateProbeStatement(
          'comp_1', 'func_1', {'str_field_started_with_a': 'b_value'})

    # Ignore the regular expression check if the given expected value is also
    # an regular expression pattern.
    result = self.probe_statement_definition.GenerateProbeStatement(
        'comp_1', 'func_1',
        {'str_field_started_with_a': re.compile('x.*')})
    self.assertEqual(
        result,
        self._GenerateExpectResult('comp_1', 'func_1', {
            'str_field_started_with_a': [True, 'str', '!re x.*']
        }))

  def testGenerateProbeStatementHexField(self):
    result = self.probe_statement_definition.GenerateProbeStatement(
        'comp_1', 'func_1', {'hex_field': '0AAAA'})
    self.assertEqual(
        result,
        self._GenerateExpectResult(
            'comp_1', 'func_1', {'hex_field': [True, 'hex', '!eq 0x0AAAA']}))

    with self.assertRaises(ValueError):
      self.probe_statement_definition.GenerateProbeStatement(
          'comp_1', 'func_1', {'hex_field': 'xyz'})

    result = self.probe_statement_definition.GenerateProbeStatement(
        'comp_1', 'func_1', {'hex_field_three_digits': None})
    self.assertEqual(
        result,
        self._GenerateExpectResult('comp_1', 'func_1',
                                   {'hex_field_three_digits': [False, 'hex']}))

    result = self.probe_statement_definition.GenerateProbeStatement(
        'comp_1', 'func_1', {'hex_field_three_digits': 'B3F'})
    self.assertEqual(
        result,
        self._GenerateExpectResult(
            'comp_1', 'func_1',
            {'hex_field_three_digits': [True, 'hex', '!eq 0xB3F']}))

    with self.assertRaises(ValueError):
      self.probe_statement_definition.GenerateProbeStatement(
          'comp_1', 'func_1', {'hex_field_three_digits': 'B3FF'})


class ProbeConfigPayloadTest(ConcreteProbeStatementDefinitionTestBase):
  def testAll(self):
    p = probe_config_types.ProbeConfigPayload()
    p.AddComponentProbeStatement(
        self.probe_statement_definition.GenerateProbeStatement(
            'comp_1', 'func_1', {'int_field': 1}))
    p.AddComponentProbeStatement(
        self.probe_statement_definition.GenerateProbeStatement(
            'comp_2', 'func_1', {'int_field': 2}))
    p.AddComponentProbeStatement(
        self.probe_statement_definition.GenerateProbeStatement(
            'comp_3', 'func_2', {'int_field': 3}))

    with self.assertRaises(ValueError):  # component name confliction
      p.AddComponentProbeStatement(
          self.probe_statement_definition.GenerateProbeStatement(
              'comp_2', 'func_1', {'int_field': 2}))

    result = p.DumpToString()
    self.assertEqual(
        json_utils.LoadStr(result),
        {
            'category_x': {
                'comp_1': {
                    'eval': {'func_1': {}},
                    'expect': {'int_field': [True, 'int', '!eq 1']}
                },
                'comp_2': {
                    'eval': {'func_1': {}},
                    'expect': {'int_field': [True, 'int', '!eq 2']}
                },
                'comp_3': {
                    'eval': {'func_2': {}},
                    'expect': {'int_field': [True, 'int', '!eq 3']}
                },
            }
        })


if __name__ == '__main__':
  unittest.main()
