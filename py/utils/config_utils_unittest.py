#!/usr/bin/env python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import config_utils


class ConfigUtilsTest(unittest.TestCase):

  def assertOverrideConfigEqual(self, val, val_override, val_expected):
    config_utils.OverrideConfig(val, val_override)
    self.assertEqual(val_expected, val)

  def testOverrideConfig(self):
    self.assertOverrideConfigEqual(
        {'a': {'b': 1, 'c': 2}},
        {'a': {'c': 3}},
        {'a': {'b': 1, 'c': 3}})

  def testOverrideConfigReplace(self):
    self.assertOverrideConfigEqual(
        {'a': {'b': 1, 'c': 2}},
        {'a': {'__replace__': True, 'c': 3}},
        {'a': {'c': 3}})
    self.assertOverrideConfigEqual(
        {'a': 1},
        {'a': {'__replace__': True, 'c': 3}},
        {'a': {'c': 3}})
    self.assertOverrideConfigEqual(
        {'a': {'b': 1, 'c': 2}},
        {'b': {'__replace__': True, 'c': 3}},
        {'a': {'b': 1, 'c': 2}, 'b': {'c': 3}})
    self.assertOverrideConfigEqual(
        {'a': {'b': 1, 'c': 2}},
        {'a': {'__replace__': True, 'c': {'__replace__': True, 'd': 3}}},
        {'a': {'c': {'d': 3}}})

  def testOverrideConfigDelete(self):
    self.assertOverrideConfigEqual(
        {'a': {'b': 1, 'c': 2}},
        {'a': {'__delete__': True}},
        {})
    self.assertOverrideConfigEqual(
        {'a': {'b': 1, 'c': 2}},
        {'a': {'__delete__': True, 'd': 3}},
        {})
    self.assertOverrideConfigEqual(
        {'a': {'b': 1, 'c': 2}},
        {'a': {'c': {'__delete__': True}, 'd': 3}},
        {'a': {'b': 1, 'd': 3}})
    self.assertOverrideConfigEqual(
        {'a': {'b': 1, 'c': 2}},
        {'a': {'d': {'__delete__': True}}},
        {'a': {'b': 1, 'c': 2}})

  def testMappingToNamedTuple(self):
    val = {'a': {'b': 1, 'c': 2}}
    val_tuple = config_utils.GetNamedTuple(val)
    self.assertEqual(val['a']['b'], val_tuple.a.b)

  def testLoadConfig(self):
    config_m = config_utils.LoadConfig(
        'testdata/config_utils_unittest',
        allow_inherit=True,
        generate_depend=True)
    config = config_utils.GetNamedTuple(config_m)

    # default values from ./config_utils_unittest.json
    self.assertEqual(config.sample_int, 1)
    self.assertEqual(config.sample_str, 'test')
    self.assertEqual(config.sample_mapping.contents, 'abc')

    self.assertEqual(config.depend, [
        'testdata/config_utils_unittest',
        'testdata/config_utils_unittest_middle_b',
        'testdata/config_utils_unittest_middle_a',
        'testdata/config_utils_unittest_base',
    ])

    # the inherited value.
    self.assertEqual(config.sample_base_int, 10)
    self.assertEqual(config.sample_base_overrided_str, 'middle_b')

    # overrided values
    self.assertEqual(config.sample_partial_int, 5)
    self.assertEqual(config_m['sample_replace_sibling_mapping'], {'b': 42})
    self.assertIsNone(config_m.get('sample_delete_sibling_int'))

    # build values from ../config/config_utils_unittest.json
    self.assertEqual(config.sample_mapping.contents, 'abc')
    self.assertIsNone(config_m.get('sample_runtime_str'))

  def testLoadConfigStringType(self):
    config = config_utils.LoadConfig(
        'testdata/config_utils_unittest', convert_to_str=False)
    self.assertEqual(type(config['sample_str']), unicode)

    config = config_utils.LoadConfig(
        'testdata/config_utils_unittest', convert_to_str=True)
    self.assertEqual(type(config['sample_str']), str)

  def testLoopDetection(self):
    with self.assertRaisesRegexp(
        AssertionError, 'Detected loop inheritance dependency .*'):
      config_utils.LoadConfig(
          'testdata/config_utils_unittest_loop',
          validate_schema=False,
          allow_inherit=True)

  def testC3LinearizationFail(self):
    with self.assertRaisesRegexp(
        RuntimeError, 'C3 linearization failed for .*'):
      config_utils.LoadConfig(
          'testdata/config_utils_unittest_c3',
          validate_schema=False,
          allow_inherit=True)


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  unittest.main()
