#!/usr/bin/env python
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import state


class FactoryStateTest(unittest.TestCase):

  def setUp(self):
    state.DEFAULT_FACTORY_STATE_FILE_DIR = tempfile.mkdtemp()
    self.state = state.FactoryState()

  def tearDown(self):
    self.state.Close()
    try:
      shutil.rmtree(state.DEFAULT_FACTORY_STATE_FILE_DIR)
    except Exception:
      pass

  def testUpdateTestState(self):
    """Test UpdateTestState

    This test also covers GetTestState.
    """
    # Pick some of the fields and update them.
    test_state, changed = self.state.UpdateTestState(
        'a.b.c', status=state.TestState.PASSED)
    self.assertEqual(state.TestState.PASSED, test_state.status)
    self.assertTrue(changed)

    test_state, changed = self.state.UpdateTestState(
        'a.b.c', status=state.TestState.PASSED)
    self.assertEqual(state.TestState.PASSED, test_state.status)
    self.assertFalse(changed)

  def testGetTestPaths(self):
    test_paths = ['a', 'a.b', 'a.c', 'a.b.a', 'a.b.b']
    for test in test_paths:
      self.state.UpdateTestState(test)

    self.assertItemsEqual(test_paths, self.state.GetTestPaths())

  def testGetTestStates(self):
    self.state.UpdateTestState('a', status=state.TestState.PASSED)
    self.state.UpdateTestState('a.b', status=state.TestState.PASSED)
    self.state.UpdateTestState('a.b.c', status=state.TestState.SKIPPED)

    states = self.state.GetTestStates()
    self.assertEqual(state.TestState.PASSED, states['a'].status)
    self.assertEqual(state.TestState.PASSED, states['a.b'].status)
    self.assertEqual(state.TestState.SKIPPED, states['a.b.c'].status)

  def testClearTestState(self):
    self.state.UpdateTestState('a', status=state.TestState.PASSED)
    self.state.UpdateTestState('a.b', status=state.TestState.PASSED)
    self.state.UpdateTestState('a.b.c', status=state.TestState.SKIPPED)
    self.state.ClearTestState()

    self.assertSequenceEqual([], self.state.GetTestPaths())

  def testSetSharedData(self):
    self.state.SetSharedData('a', 1)
    self.state.SetSharedData('b', 'abc')

    self.assertEqual(1, self.state.GetSharedData('a'))
    self.assertEqual('abc', self.state.GetSharedData('b'))

  def testGetSharedData(self):
    self.state.SetSharedData('a', 1)
    self.state.SetSharedData('b', 'abc')

    self.assertEqual(1, self.state.GetSharedData('a'))
    self.assertEqual('abc', self.state.GetSharedData('b'))
    self.assertIsNone(self.state.GetSharedData('c', optional=True))

  def testHasSharedData(self):
    self.state.SetSharedData('a', 1)
    self.state.SetSharedData('b', 'abc')
    self.assertTrue(self.state.HasSharedData('a'))
    self.assertFalse(self.state.HasSharedData('c'))

  def testDeleteSharedData(self):
    self.state.SetSharedData('a', 1)
    self.state.SetSharedData('b', 'abc')
    self.state.DeleteSharedData('a')
    self.state.DeleteSharedData('c', optional=True)

    self.assertFalse(self.state.HasSharedData('a'))

  def testUpdateSharedDataDict(self):
    self.state.SetSharedData('data', {'a': 1})
    self.state.UpdateSharedDataDict('data', {'a': 2, 'b': 3})

    self.assertEqual({'a': 2, 'b': 3}, self.state.GetSharedData('data'))

    self.state.UpdateSharedDataDict('data', {'c': 4, 'b': 2})
    self.assertEqual({'a': 2, 'b': 2, 'c': 4},
                     self.state.GetSharedData('data'))

  def testDeleteSharedDataDictItem(self):
    self.state.SetSharedData('data', {'a': 1, 'b': 2})
    self.state.DeleteSharedData('data.b')
    self.state.DeleteSharedData('data.c', optional=True)

    self.assertEqual({'a': 1}, self.state.GetSharedData('data'))

  def testAppendSharedDataList(self):
    self.state.SetSharedData('data', [1, 2])
    self.state.AppendSharedDataList('data', 3)

    self.assertEqual([1, 2, 3], self.state.GetSharedData('data'))

  def testLayers(self):
    self.state.DataShelfSetValue('data', {'a': 0, 'b': 2})
    self.assertEqual({'a': 0, 'b': 2},
                     self.state.DataShelfGetValue('data'))

    self.state.AppendLayer()
    self.assertEqual({'a': 0, 'b': 2},
                     self.state.DataShelfGetValue('data'))

    self.state.DataShelfSetValue('data.c', 5)
    self.assertEqual({'a': 0, 'b': 2, 'c': 5},
                     self.state.DataShelfGetValue('data'))

    with self.assertRaises(state.FactoryStateLayerException):
      self.state.AppendLayer()

    self.state.PopLayer()
    self.assertEqual({'a': 0, 'b': 2},
                     self.state.DataShelfGetValue('data'))

    with self.assertRaises(state.FactoryStateLayerException):
      self.state.PopLayer()

  def testMergeLayer(self):
    self.state.DataShelfSetValue('data', {'a': 0, 'b': 2})
    self.assertEqual({'a': 0, 'b': 2},
                     self.state.DataShelfGetValue('data'))

    self.state.AppendLayer()
    self.assertEqual({'a': 0, 'b': 2},
                     self.state.DataShelfGetValue('data'))

    self.state.DataShelfSetValue('data.c', 5)
    self.assertEqual({'a': 0, 'b': 2, 'c': 5},
                     self.state.DataShelfGetValue('data'))

    with self.assertRaises(state.FactoryStateLayerException):
      self.state.AppendLayer()

    # tests_shelf of top layer is empty, this shouldn't be an issue.
    self.state.MergeLayer(1)
    self.assertEqual({'a': 0, 'b': 2, 'c': 5},
                     self.state.DataShelfGetValue('data'))

    with self.assertRaises(state.FactoryStateLayerException):
      self.state.PopLayer()

    # tests_shelf of top layer should still be empty.
    self.assertEqual(self.state.layers[0].tests_shelf.GetKeys(), [])

  def testSerializeLayer(self):
    layer = state.FactoryStateLayer()

    tests = {'tests': state.TestState()}
    data = {'data': {'a': 1, 'b': 2}}
    layer.tests_shelf.SetValue('', tests)
    layer.data_shelf.SetValue('', data)

    serialized_data = layer.Dumps(True, True)
    self.assertTrue(isinstance(serialized_data, basestring))

    layer = state.FactoryStateLayer()
    layer.Loads(serialized_data)

    self.assertEqual(data, layer.data_shelf.GetValue(''))
    self.assertEqual(tests, layer.tests_shelf.GetValue(''))


if __name__ == '__main__':
  unittest.main()
