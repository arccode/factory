#!/usr/bin/env python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import logging
import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import config_utils
from cros.factory.utils import type_utils


class ConfigUtilsTest(unittest.TestCase):

  def assertOverrideConfigEqual(self, val, val_override, val_expected):
    config_utils.OverrideConfig(val, val_override)
    self.assertEqual(val_expected, val)

  def testOverrideConfig(self):
    self.assertOverrideConfigEqual(
        {'a': {'b': 1, 'c': 2}},
        {'a': {'c': 3}},
        {'a': {'b': 1, 'c': 3}})
    # override a non-dict value by dict value
    self.assertOverrideConfigEqual(
        {'a': {'b': 1, 'c': 2}},
        {'a': {'b': {'d': 1}}},
        {'a': {'b': {'d': 1}, 'c': 2}})
    # override a dict value by non-dict value
    self.assertOverrideConfigEqual(
        {'a': {'b': {'d': 1}, 'c': 2}},
        {'a': {'b': 1}},
        {'a': {'b': 1, 'c': 2}})

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

  def testOverrideConfigCopyOnWrite(self):
    old_config = {
        'a': {
            'b': 'B',
            'c': 'C',
        },
        'd': 'D',
    }
    new_config = config_utils.OverrideConfig(
        old_config, {'a': {'b': 'BB'}, 'd': 'DD'}, copy_on_write=True)

    self.assertEqual(new_config, {'a': {'b': 'BB', 'c': 'C'}, 'd': 'DD'})
    self.assertEqual(old_config, {'a': {'b': 'B', 'c': 'C'}, 'd': 'D'})

  def testMappingToNamedTuple(self):
    val = {'a': {'b': 1, 'c': 2}}
    val_tuple = config_utils.GetNamedTuple(val)
    self.assertEqual(val['a']['b'], val_tuple.a.b)

  def testLoadConfig(self):
    config_m = config_utils.LoadConfig(
        'testdata/config_utils_unittest',
        default_config_dirs=[os.path.join(os.path.dirname(__file__),
                                          'testdata', 'extra_dir'),
                             config_utils.CALLER_DIR],
        allow_inherit=True,
        generate_depend=True)
    config = config_utils.GetNamedTuple(config_m)

    # default values from ./config_utils_unittest.json
    self.assertEqual(config.sample_int, 1)
    self.assertEqual(config.sample_str, 'test')
    self.assertEqual(config.sample_mapping.contents, 'abc')

    expected = [
        'config/testdata/config_utils_unittest.json',
        'utils/testdata/config_utils_unittest.json',
        'utils/testdata/config_utils_unittest_middle_b.json',
        'utils/testdata/config_utils_unittest_middle_a.json',
        'utils/testdata/config_utils_unittest_base.json', ]

    for expected_path, config_path in zip(expected, config_m.GetDepend()):
      self.assertTrue(config_path.endswith(expected_path))

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


class ResolvedConfigTest(unittest.TestCase):
  """Test ResolvedConfig"""

  def testSubclass(self):
    self.assertTrue(issubclass(config_utils.ResolvedConfig, dict))

  def testDictBehavior(self):
    d = {
        'a': 1,
        'b': "string",
        'c': [1, 2, 3],
        'd': {'x': 1, 'y': 2}
    }

    resolved_config = config_utils.ResolvedConfig(d)
    self.assertEqual(resolved_config, d)

    # it can be serialized, deserialized, as if it's a normal
    # dictionary.
    self.assertEqual(json.loads(json.dumps(resolved_config)), d)

    # it can be passed to AttrDict
    attr_dict = type_utils.AttrDict(resolved_config)
    self.assertEqual(attr_dict.a, 1)
    self.assertEqual(attr_dict.b, "string")
    self.assertEqual(attr_dict.c, [1, 2, 3])
    self.assertEqual(attr_dict.d, {'x': 1, 'y': 2})
    self.assertEqual(attr_dict.d.x, 1)
    self.assertEqual(attr_dict.d.y, 2)


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  unittest.main()
