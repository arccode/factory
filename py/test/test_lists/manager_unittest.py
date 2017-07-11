#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import glob
import json
import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test.test_lists import manager


class TestListConfigTest(unittest.TestCase):
  def testTestListConfig(self):
    json_object = {'a': 1, 'b': 2}
    test_list_id = 'test_list_id'
    timestamp = 123456

    config = manager.TestListConfig(
        json_object=json_object,
        test_list_id=test_list_id,
        timestamp=timestamp)

    self.assertEqual(config.test_list_id, test_list_id)
    self.assertEqual(config.timestamp, timestamp)
    # TestListConfig object should act like json_object.
    self.assertEqual({k: config[k] for k in config}, json_object)


class TestListLoaderTest(unittest.TestCase):
  def setUp(self):
    test_lists_dir = os.path.abspath(os.path.dirname(__file__))
    self.temp_dir = tempfile.mkdtemp(prefix='cros-factory.manager_unittest.')

    self.loader = manager.Loader(config_dir=self.temp_dir)
    self.manager = manager.Manager(loader=self.loader)

    # copy necessary files into self.temp_dir
    for filepath in glob.glob(os.path.join(test_lists_dir,
                                           'manager_unittest',
                                           '*.test_list.json')):
      shutil.copy(filepath, self.temp_dir)
    shutil.copy(os.path.join(test_lists_dir, 'base.test_list.json'),
                self.temp_dir)
    shutil.copy(os.path.join(test_lists_dir, 'test_list.schema.json'),
                self.temp_dir)

  def tearDown(self):
    shutil.rmtree(self.temp_dir, ignore_errors=True)

  def testGetTestListByID(self):
    test_list = self.manager.GetTestListByID('a')

    factory_test_list = test_list.ToFactoryTestList()
    self.assertListEqual(
        ['SMT.FirstLEDTest', 'SMT.SecondLEDTest', 'SMT.verify_components',
         'SMT.Halt', 'SMT.LEDTest', 'SMT.LEDTest-2'],
        [test.path for test in factory_test_list.Walk() if test.IsLeaf()])
    self.assertEqual('a', factory_test_list.test_list_id)
    options = {
        'engineering_password_sha1': 'dummy_password_sha1',
        'ui_lang': 'zh',
        'sync_event_log_period_secs': 0,
        'disable_cros_shortcut_keys': True,
        'core_dump_watchlist': [], }

    for key in options:
      self.assertEqual(
          options[key],
          getattr(factory_test_list.options, key))

  def testResolveTestArgs(self):
    test_args = {
        'a': 'eval! \'eval! \'',
        'b': 'eval! constants.timestamp',
        'c': 'eval! constants.timestamp + 3',
        'd': 'eval! options.ui_lang.upper()',
        'e': 'eval! [x * x for x in xrange(3)]', }

    test_list = self.manager.GetTestListByID('a')
    constants = test_list.ToTestListConfig()['constants']
    options = test_list.ToTestListConfig()['options']

    self.assertDictEqual(
        {'a': 'eval! ',
         'b': constants['timestamp'],
         'c': constants['timestamp'] + 3,
         'd': options['ui_lang'].upper(),
         'e': [x * x for x in xrange(3)], },
        test_list.ResolveTestArgs(test_args, None, None))

  def testListTestListIDs(self):
    self.assertItemsEqual(
        ['a', 'b', 'base'],
        self.loader.FindTestListIDs())

  def testChildActionOnFailure(self):
    """Test if `child_action_on_failure` is properly propagated."""
    test_list = self.manager.GetTestListByID('b')
    factory_test_list = test_list.ToFactoryTestList()

    expected = collections.OrderedDict([
        ('SMT.RebootStep', 'PARENT'),
        ('SMT.Group.RebootStep', 'PARENT'),
        ('SMT.Group.RebootStep-2', 'PARENT'),
        ('SMT.Group-2.RebootStep', 'STOP'),
        ('SMT.Group-2.RebootStep-2', 'STOP'),
        ('SMT.RebootStep-2', 'PARENT'),
        ('SMT.RebootStep-3', 'PARENT'),
        ('SMT.RebootStep-4', 'STOP')])

    self.assertListEqual(
        expected.keys(),
        [test.path for test in factory_test_list.Walk() if test.IsLeaf()])

    for key, value in expected.iteritems():
      self.assertEqual(
          value,
          factory_test_list.LookupPath(key).action_on_failure)

    self.assertEqual(
        'NEXT',
        factory_test_list.LookupPath('SMT.Group').action_on_failure)

  def testModifiedDetection(self):
    test_list = self.manager.GetTestListByID('b')
    self.assertFalse(test_list.modified)

    # 'b' is modified
    os.utime(self.loader.GetConfigPath('b'), None)
    self.assertTrue(test_list.modified)

    # let's go back in time
    os.utime(self.loader.GetConfigPath('b'), (0, 0))
    self.assertFalse(test_list.modified)

    # b inherits base
    os.utime(self.loader.GetConfigPath('base'), None)
    self.assertTrue(test_list.modified)

  def testAutoReloadTestList(self):
    # load test list config
    test_list = self.manager.GetTestListByID('a')

    self.assertTrue(test_list.LookupPath('SMT'))

    # modified content
    with open(self.loader.GetConfigPath('a'), 'r') as f:
      json_object = json.load(f)
    with open(self.loader.GetConfigPath('a'), 'w') as f:
      json_object['constants']['timestamp'] = 123
      json_object['tests'] = [
          {
              'id': 'RunIn',
              'subtests': []
          }
      ]
      json.dump(json_object, f)
    os.utime(self.loader.GetConfigPath('a'), None)

    # test list should be automatically reloaded
    self.assertEqual(test_list.constants.timestamp, 123)
    # SMT doesn't exist
    self.assertIsNone(test_list.LookupPath('SMT'))
    self.assertTrue(test_list.LookupPath('RunIn'))


class CheckerTest(unittest.TestCase):
  def setUp(self):
    self.checker = manager.Checker()

  def testAssertExpressionIsValid(self):
    expression = 'while True: a = a + 3'
    with self.assertRaises(manager.CheckerError):
      self.checker.AssertExpressionIsValid(expression)

    expression = 'dut.info.serial_number + station.var + abs(options.value)'
    self.checker.AssertExpressionIsValid(expression)

    expression = '[(a, d, c) for a in dut.arr for c in a for d in c]'
    self.checker.AssertExpressionIsValid(expression)

    expression = '[(a, d, c) for a in dut.arr for d in c for c in a]'
    # failed because c is used before define
    with self.assertRaises(manager.CheckerError):
      self.checker.AssertExpressionIsValid(expression)

    expression = '{k: str(k) for k in dut.arr}'
    self.checker.AssertExpressionIsValid(expression)

    expression = '{k: v for (k, v) in dut.dct.itertiems() if v}'
    self.checker.AssertExpressionIsValid(expression)

    expression = '(x * x for x in xrange(3))'
    # generator is not allowed
    with self.assertRaises(manager.CheckerError):
      self.checker.AssertExpressionIsValid(expression)

    expression = '({x for x in [1]}, x)'
    # the second x is not defined
    with self.assertRaises(manager.CheckerError):
      self.checker.AssertExpressionIsValid(expression)

    expression = '[([y for y in [x]], x) for x in [1]]'
    self.checker.AssertExpressionIsValid(expression)


if __name__ == '__main__':
  unittest.main()
