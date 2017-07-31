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
from cros.factory.test import state
from cros.factory.test.test_lists import manager
from cros.factory.utils import type_utils


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
        ['SMT.FirstLEDTest', 'SMT.SecondLEDTest', 'SMT.VerifyComponents',
         'SMT.Halt', 'SMT.LEDTest', 'SMT.LEDTest-2'],
        [test.path for test in factory_test_list.Walk() if test.IsLeaf()])
    self.assertEqual('a', factory_test_list.test_list_id)
    options = {
        'engineering_password_sha1': 'dummy_password_sha1',
        'ui_locale': 'zh-CN',
        'sync_event_log_period_secs': 0,
        'disable_cros_shortcut_keys': True, }

    for key in options:
      self.assertEqual(
          options[key],
          getattr(factory_test_list.options, key))

  def testResolveTestArgs(self):
    test_args = {
        'a': 'eval! \'eval! \'',
        'b': 'eval! constants.timestamp',
        'c': 'eval! constants.timestamp + 3',
        'd': 'eval! options.ui_locale.upper()',
        'e': 'eval! [x * x for x in xrange(3)]',
        'f': 'eval! constants.some_label', }

    test_list = self.manager.GetTestListByID('a')
    constants = test_list.ToTestListConfig()['constants']
    options = test_list.ToTestListConfig()['options']
    resolved_test_args = test_list.ResolveTestArgs(test_args, None, None)

    self.assertDictEqual(
        {'a': 'eval! ',
         'b': constants['timestamp'],
         'c': constants['timestamp'] + 3,
         'd': options['ui_locale'].upper(),
         'e': [x * x for x in xrange(3)],
         'f': {'en-US': 'us', 'zh-CN': 'cn'}, },
        resolved_test_args)

    # We expect test arguments to be type dict instead of AttrDict, so yaml
    # serialization of test metadata would work.
    self.assertEqual(dict, type(resolved_test_args['f']))

  def testListTestListIDs(self):
    self.assertItemsEqual(
        ['a', 'b', 'base', 'locals', 'override_args', "flatten_group"],
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

  def testOverrideArgs(self):
    test_list = self.manager.GetTestListByID('override_args')
    test_list = test_list.ToFactoryTestList()

    expected = {
        'SMT.FirstLEDTest': ['RED'],
        'SMT.SecondLEDTest': ['BLUE'],
        'SMT.LEDTest': ['GREEN'],
        'SMT.LEDTest-2': ['WHITE'],
    }

    for path, colors in expected.iteritems():
      self.assertEqual(
          colors, test_list.LookupPath(path).dargs['colors'])

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

  def testLocals(self):
    test_list = self.manager.GetTestListByID('locals')
    self.assertEqual(
        test_list.LookupPath('SMT.NOP').locals_,
        {'foo': 'FOO', 'bar': 'BAR'})
    self.assertEqual(
        test_list.LookupPath('SMT.NOP-2').locals_,
        {'foo': 'FOO', 'bar': 'BAZ'})
    self.assertEqual(
        test_list.LookupPath('SMT.NOP-3').locals_,
        {'foo': 'BAR', 'bar': 'BAZ'})

  def testFlattenGroup(self):
    test_list = self.manager.GetTestListByID('flatten_group')

    expected = collections.OrderedDict([
        ("NOP", {"foo": "FOO"}),
        ("NOP-2", {"foo": "FOO", "bar": "BAR"}),
        ("NOP-3", {"foo": "FOO", "bar": "BAR"}),
        ("Group3.NOP", {"foo": "FOO", "baz": "BAZ"}),
        ("Group3.NOP-2", {"baz": "BAZ"}),
    ])

    self.assertListEqual(
        expected.keys(),
        [test.path for test in test_list.Walk() if test.IsLeaf()])

    for test in test_list.Walk():
      if test.IsLeaf():
        self.assertEqual(test.locals_, expected[test.path])


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

class EvaluateRunIfTest(unittest.TestCase):
  def setUp(self):
    state_instance = state.StubFactoryState()
    constants = {}

    self.test = type_utils.AttrDict(run_if=None, path='path.to.test')
    # run_if function should only use these attributes
    self.test_list = type_utils.AttrDict(state_instance=state_instance,
                                         constants=constants)

  def _EvaluateRunIf(self):
    return manager.ITestList.EvaluateRunIf(self.test, self.test_list, None)

  def testInvalidRunIfString(self):
    self.test.run_if = '!device.foo.bar'
    self.assertTrue(self._EvaluateRunIf())

  def testDeviceData(self):
    self.test.run_if = 'device.foo.bar'

    self.assertFalse(self._EvaluateRunIf())

    self.test_list.state_instance.data_shelf['device.foo.bar'].Set(True)
    self.assertTrue(self._EvaluateRunIf())

    self.test_list.state_instance.data_shelf['device.foo.bar'].Set(False)
    self.assertFalse(self._EvaluateRunIf())

  def testConstant(self):
    self.test.run_if = 'constants.foo.bar'

    self.assertFalse(self._EvaluateRunIf())

    self.test_list.constants['foo'] = {'bar': True}
    self.assertTrue(self._EvaluateRunIf())

    self.test_list.constants['foo'] = {'bar': False}
    self.assertFalse(self._EvaluateRunIf())

  def testComplexExpression(self):
    self.test.run_if = 'not device.foo.bar or constants.x.y'

    self.assertTrue(self._EvaluateRunIf())

    self.test_list.constants['x'] = {'y': True}
    self.assertTrue(self._EvaluateRunIf())

    self.test_list.constants['x'] = {'y': False}
    self.assertTrue(self._EvaluateRunIf())

    self.test_list.state_instance.data_shelf['device.foo.bar'].Set(True)
    self.test_list.constants['x'] = {'y': False}
    self.assertFalse(self._EvaluateRunIf())

    self.test_list.state_instance.data_shelf['device.foo.bar'].Set(True)
    self.test_list.constants['x'] = {}
    self.assertFalse(self._EvaluateRunIf())

    self.test_list.state_instance.data_shelf['device.foo.bar'].Set(True)
    self.test_list.constants['x'] = {'y': True}
    self.assertTrue(self._EvaluateRunIf())


if __name__ == '__main__':
  unittest.main()
