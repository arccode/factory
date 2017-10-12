#!/usr/bin/python -u
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
    self.state.close()
    try:
      shutil.rmtree(state.DEFAULT_FACTORY_STATE_FILE_DIR)
    except Exception:
      pass

  def testUpdateTestState(self):
    """Test update_test_state

    This test also covers get_test_state.
    """
    # Pick some of the fields and update them.
    test_state, changed = self.state.update_test_state(
        'a.b.c', status=state.TestState.PASSED)
    self.assertEqual(state.TestState.PASSED, test_state.status)
    self.assertTrue(changed)

    test_state, changed = self.state.update_test_state(
        'a.b.c', status=state.TestState.PASSED)
    self.assertEqual(state.TestState.PASSED, test_state.status)
    self.assertFalse(changed)

  def testGetTestPaths(self):
    test_paths = ['a', 'a.b', 'a.c', 'a.b.a', 'a.b.b']
    for test in test_paths:
      self.state.update_test_state(test)

    self.assertItemsEqual(test_paths, self.state.get_test_paths())

  def testGetTestStates(self):
    self.state.update_test_state('a', status=state.TestState.PASSED)
    self.state.update_test_state('a.b', status=state.TestState.PASSED)
    self.state.update_test_state('a.b.c', status=state.TestState.SKIPPED)

    states = self.state.get_test_states()
    self.assertEqual(state.TestState.PASSED, states['a'].status)
    self.assertEqual(state.TestState.PASSED, states['a.b'].status)
    self.assertEqual(state.TestState.SKIPPED, states['a.b.c'].status)

  def testClearTestState(self):
    self.state.update_test_state('a', status=state.TestState.PASSED)
    self.state.update_test_state('a.b', status=state.TestState.PASSED)
    self.state.update_test_state('a.b.c', status=state.TestState.SKIPPED)
    self.state.clear_test_state()

    self.assertSequenceEqual([], self.state.get_test_paths())

  def testSetSharedData(self):
    self.state.set_shared_data('a', 1)
    self.state.set_shared_data('b', 'abc')

    self.assertEqual(1, self.state.get_shared_data('a'))
    self.assertEqual('abc', self.state.get_shared_data('b'))

  def testGetSharedData(self):
    self.state.set_shared_data('a', 1)
    self.state.set_shared_data('b', 'abc')

    self.assertEqual(1, self.state.get_shared_data('a'))
    self.assertEqual('abc', self.state.get_shared_data('b'))
    self.assertIsNone(self.state.get_shared_data('c', optional=True))

  def testHasSharedData(self):
    self.state.set_shared_data('a', 1)
    self.state.set_shared_data('b', 'abc')
    self.assertTrue(self.state.has_shared_data('a'))
    self.assertFalse(self.state.has_shared_data('c'))

  def testDelSharedData(self):
    self.state.set_shared_data('a', 1)
    self.state.set_shared_data('b', 'abc')
    self.state.del_shared_data('a')
    self.state.del_shared_data('c', optional=True)

    self.assertFalse(self.state.has_shared_data('a'))

  def testUpdateSharedDataDict(self):
    self.state.set_shared_data('data', {'a': 1})
    self.state.update_shared_data_dict('data', {'a': 2, 'b': 3})

    self.assertEqual({'a': 2, 'b': 3}, self.state.get_shared_data('data'))

    self.state.update_shared_data_dict('data', {'c': 4, 'b': 2})
    self.assertEqual({'a': 2, 'b': 2, 'c': 4},
                     self.state.get_shared_data('data'))

  def testDeleteSharedDataDictItem(self):
    self.state.set_shared_data('data', {'a': 1, 'b': 2})
    self.state.del_shared_data('data.b')
    self.state.del_shared_data('data.c', optional=True)

    self.assertEqual({'a': 1}, self.state.get_shared_data('data'))

  def testAppendSharedDataList(self):
    self.state.set_shared_data('data', [1, 2])
    self.state.append_shared_data_list('data', 3)

    self.assertEqual([1, 2, 3], self.state.get_shared_data('data'))

  def testLayers(self):
    self.state.data_shelf_set_value('data', {'a': 0, 'b': 2})
    self.assertEqual({'a': 0, 'b': 2},
                     self.state.data_shelf_get_value('data'))

    self.state.AppendLayer()
    self.assertEqual({'a': 0, 'b': 2},
                     self.state.data_shelf_get_value('data'))

    self.state.data_shelf_set_value('data.c', 5)
    self.assertEqual({'a': 0, 'b': 2, 'c': 5},
                     self.state.data_shelf_get_value('data'))

    with self.assertRaises(state.FactoryStateLayerException):
      self.state.AppendLayer()

    self.state.PopLayer()
    self.assertEqual({'a': 0, 'b': 2},
                     self.state.data_shelf_get_value('data'))

    with self.assertRaises(state.FactoryStateLayerException):
      self.state.PopLayer()

  def testSerializeLayer(self):
    layer = state.FactoryStateLayer()

    tests = {'tests': state.TestState()}
    data = {'data': {'a': 1, 'b': 2}}
    layer.tests_shelf.SetValue('', tests)
    layer.data_shelf.SetValue('', data)

    serialized_data = layer.dumps(True, True)
    self.assertTrue(isinstance(serialized_data, basestring))

    layer = state.FactoryStateLayer()
    layer.loads(serialized_data)

    self.assertEqual(data, layer.data_shelf.GetValue(''))
    self.assertEqual(tests, layer.tests_shelf.GetValue(''))


if __name__ == '__main__':
  unittest.main()
