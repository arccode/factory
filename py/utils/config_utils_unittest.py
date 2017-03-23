#!/usr/bin/env python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.utils import config_utils


class ConfigUtilsUnitTest(unittest.TestCase):

  def testOverrideConfig(self):
    val = {'a': {'b': 1, 'c': 2}}
    val_override = {'a': {'c': 3}}
    val_expected = {'a': {'b': 1, 'c': 3}}
    config_utils.OverrideConfig(val, val_override)
    self.assertEqual(val_expected, val)

  def testMappingToNamedTuple(self):
    val = {'a': {'b': 1, 'c': 2}}
    val_tuple = config_utils.GetNamedTuple(val)
    self.assertEqual(val['a']['b'], val_tuple.a.b)

  def testLoadConfig(self):
    config_m = config_utils.LoadConfig(
        'testdata/config_utils_unittest', allow_inherit=True)
    config = config_utils.GetNamedTuple(config_m)

    # default values from ./config_utils_unittest.json
    self.assertEqual(config.sample_int, 1)
    self.assertEqual(config.sample_str, 'test')
    self.assertEqual(config.sample_mapping.contents, 'abc')

    # the inherited value.
    self.assertEqual(config.sample_base_int, 10)
    self.assertEqual(config.sample_base_str_overrided, "middle_b")

    # build values from ../config/config_utils_unittest.json
    self.assertEqual(config.sample_mapping.contents, 'abc')
    self.assertEqual(config_m.get('sample_runtime', None), None)

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


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  unittest.main()
