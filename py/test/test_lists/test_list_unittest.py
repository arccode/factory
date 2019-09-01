#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import state
from cros.factory.test.test_lists import manager
from cros.factory.test.test_lists import test_list as test_list_module
from cros.factory.utils import type_utils


class FactoryTestListTest(unittest.TestCase):
  def testGetNextSibling(self):
    test_list = manager.BuildTestListForUnittest(
        test_list_config={
            'tests': [
                {'id': 'G',
                 'subtests': [
                     {'id': 'G',
                      'subtests': [
                          {'id': 'a', 'pytest_name': 't_GGa'},
                          {'id': 'b', 'pytest_name': 't_GGb'},
                      ]},
                     {'id': 'b', 'pytest_name': 't_Gb'},
                 ]}
            ]
        })
    test = test_list.LookupPath('G.G')
    self.assertEqual(test.GetNextSibling(), test_list.LookupPath('G.b'))
    test = test_list.LookupPath('G.G.a')
    self.assertEqual(test.GetNextSibling(), test_list.LookupPath('G.G.b'))
    test = test_list.LookupPath('G.G.b')
    self.assertIsNone(test.GetNextSibling())

  def testResolveRequireRun(self):
    self.assertEqual(
        'e.f',
        test_list_module.FactoryTestList.ResolveRequireRun('a.b.c.d', 'e.f'))
    self.assertEqual(
        'a.b.c.e.f',
        test_list_module.FactoryTestList.ResolveRequireRun('a.b.c.d', '.e.f'))
    self.assertEqual(
        'a.b.e.f',
        test_list_module.FactoryTestList.ResolveRequireRun('a.b.c.d', '..e.f'))
    self.assertEqual(
        'a.e.f',
        test_list_module.FactoryTestList.ResolveRequireRun('a.b.c.d', '...e.f'))


class EvaluateRunIfTest(unittest.TestCase):
  def setUp(self):
    state_instance = state.StubFactoryState()
    constants = {}

    self.test = type_utils.AttrDict(run_if=None, path='path.to.test')
    # run_if function should only use these attributes
    self.test_list = type_utils.AttrDict(state_instance=state_instance,
                                         constants=constants)

  def _EvaluateRunIf(self):
    return test_list_module.ITestList.EvaluateRunIf(self.test, self.test_list)

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
