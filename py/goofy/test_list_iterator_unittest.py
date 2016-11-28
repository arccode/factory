#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import cPickle as pickle
import imp
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy import test_list_iterator
from cros.factory.test import state
from cros.factory.test import factory
from cros.factory.test.test_lists import test_lists


def _BuildTestList(test_items, options):
  """Build a test list

  Args:
    test_items: the body of "with test_lists.TestList(...)" statement.  The
      'test_lists' module is imported, so you can use test_lists.FactoryTest or
      other functions to generate test items.  The top level should indent "4"
      spaces.
    options: set test list options, the "options" variable is imported.  Should
      indent "4" spaces.
  """

  _TEST_LIST_TEMPLATE = """
import factory_common
from cros.factory.test.test_lists import test_lists
from cros.factory.utils.net_utils import WLAN

def CreateTestLists():
  with test_lists.TestList(id='stub_test_list', label_en='label') as test_list:
    options = test_list.options

    # Load dummy plugin config as default.
    options.plugin_config_name = 'goofy_unittest'
    {options}
    {test_items}
  """

  source = _TEST_LIST_TEMPLATE.format(test_items=test_items, options=options)
  module = imp.new_module('stub_test_list')
  module.__file__ = '/dev/null'
  exec source in module.__dict__

  created_test_lists = test_lists.BuildTestLists(module)
  assert len(created_test_lists) == 1
  return created_test_lists.values()[0]


class TestListIteratorTest(unittest.TestCase):
  """Base class for TestListIterator unittests"""
  OPTIONS = ''  # Overriden by subclasses
  TEST_LIST = ''  # Overriden by subclasses

  def setUp(self):
    self.test_list = self._BuildTestList(self.TEST_LIST, self.OPTIONS)

  def _BuildTestList(self, test_list_code, options_code):
    return _BuildTestList(test_list_code, options_code)

  def _SetStubStateInstance(self, test_list):
    state_instance = state.StubFactoryState()
    test_list.state_instance = state_instance
    for test in test_list.get_all_tests():
      test.update_state(update_parent=False, visible=False)
    return test_list

  def _testPickleSerializable(self, iterator):
    """A TestListIterator object should be pickleable.

    Call this function after some operations to check if the object persists
    after `pickle.dump()` and `pickle.load()`.
    """
    pickled_string = pickle.dumps(iterator)
    deserialized_object = pickle.loads(pickled_string)
    self.assertTrue(isinstance(deserialized_object,
                               test_list_iterator.TestListIterator))
    self.assertListEqual(iterator.stack, deserialized_object.stack)
    self.assertEqual(iterator.status_filter,
                     deserialized_object.status_filter)
    return deserialized_object

  def _AssertTestSequence(self, test_list, expected_sequence,
                          root=None, max_iteration=10,
                          test_persistency=False, aux_data=None,
                          run_test=None):
    """Helper function to check the test order.

    Args:
      test_list: the test_list to run
      expected_sequence: the expected test order
      root: starting from which test
      max_iteration: a big enough number that should exhaust the iterator.
      test_persistency: will serialize and deserialize the iterator between each
          next call.
      aux_data: initial stub aux_data
      run_test: a function will be called for each test returned by the
          iterator.  The signature is run_test(test_path, current_aux_data).
          This function must return True if the test is considered passed, False
          otherwise.  This function can modify current_aux_data or cause other
          side effects to affect the next or following tests.
    """
    if not root:
      root = test_list
    aux_data = aux_data or {}
    test_list = self._SetStubStateInstance(test_list)
    iterator = test_list_iterator.TestListIterator(root, test_list=test_list)
    actual_sequence = []
    if not run_test:
      run_test = lambda unused_path, unused_aux_data: True

    # mock _check_run_if
    # pylint: disable=protected-access
    def _GetData(db_name):
      return aux_data.get(db_name, {})
    def _MockedCheckRunIf(path):
      return test_list_iterator.TestListIterator._check_run_if(
          iterator,
          path,
          test_arg_env={},
          get_data=_GetData)
    iterator._check_run_if = _MockedCheckRunIf

    with self.assertRaises(StopIteration):
      for unused_i in xrange(max_iteration):
        test_path = iterator.next()
        actual_sequence.append(test_path)
        test = test_list.lookup_path(test_path)
        if run_test(test_path, aux_data):
          test.update_state(status=factory.TestState.PASSED)
        else:
          test.update_state(status=factory.TestState.FAILED)
        if test_persistency:
          iterator = self._testPickleSerializable(iterator)
          # the persistency of state instance is provided by
          # `cros.factory.goofy.goofy`
          # and `cros.factory.test.state`.  We assume that it just works.
          # So the test list itself won't be changed.
          iterator.set_test_list(test_list)
    self.assertListEqual(expected_sequence, actual_sequence)


class TestListIteratorBaseTest(TestListIteratorTest):
  """Test test_list_iterator.TestListIterator.

  http://go/cros-factory-test-list#heading=h.e6unooltup1a
  """

  OPTIONS = ''
  TEST_LIST = """
    test_lists.FactoryTest(id='a', autotest_name='t_a')
    test_lists.FactoryTest(id='b', autotest_name='t_b')
    with test_lists.FactoryTest(id='G'):
      test_lists.FactoryTest(id='a', autotest_name='t_Ga')
      test_lists.FactoryTest(id='b', autotest_name='t_Gb')
      with test_lists.TestGroup(id='G'):
        test_lists.FactoryTest(id='a', autotest_name='t_GGa')
        test_lists.FactoryTest(id='b', autotest_name='t_GGb')
    test_lists.FactoryTest(id='c', autotest_name='t_c')
  """

  def testInitFromRoot(self):
    root_path = self.test_list.path
    iterator = test_list_iterator.TestListIterator(root_path)

    self._testPickleSerializable(iterator)
    self.assertListEqual([root_path], iterator.stack)

    iterator = test_list_iterator.TestListIterator(self.test_list)
    self._testPickleSerializable(iterator)
    self.assertListEqual([root_path], iterator.stack)

  def testInitFromNonRoot(self):
    # 1. specify starting test by path string
    root_path = self.test_list.subtests[0].path
    iterator = test_list_iterator.TestListIterator(root_path)
    self._testPickleSerializable(iterator)
    self.assertListEqual([root_path], iterator.stack)

    # 2. specify starting test by test object
    iterator = test_list_iterator.TestListIterator(self.test_list.subtests[0])
    self._testPickleSerializable(iterator)
    self.assertListEqual([root_path], iterator.stack)

  def testInitWithStatusFilter(self):
    for status_filter in ([],
                          [factory.TestState.FAILED],
                          [factory.TestState.FAILED,
                           factory.TestState.UNTESTED]):
      iterator = test_list_iterator.TestListIterator(
          self.test_list, status_filter)
      self.assertListEqual(status_filter, iterator.status_filter)
      self._testPickleSerializable(iterator)

  def testNext(self):
    self._AssertTestSequence(
        self.test_list,
        ['a', 'b', 'G.a', 'G.b', 'G.G.a', 'G.G.b', 'c'],
        test_persistency=False)
    self._AssertTestSequence(
        self.test_list,
        ['a', 'b', 'G.a', 'G.b', 'G.G.a', 'G.G.b', 'c'],
        test_persistency=True)

  def testNextStartFromNonRoot(self):
    self._AssertTestSequence(
        self.test_list,
        ['G.a', 'G.b', 'G.G.a', 'G.G.b'],
        root='G',
        test_persistency=True)
    self._AssertTestSequence(
        self.test_list,
        ['G.a', 'G.b', 'G.G.a', 'G.G.b'],
        root='G',
        test_persistency=False)
    self._AssertTestSequence(
        self.test_list,
        ['G.G.a', 'G.G.b'],
        root='G.G',
        test_persistency=False)
    self._AssertTestSequence(
        self.test_list,
        ['a'],
        root='a',
        test_persistency=False)
    self._AssertTestSequence(
        self.test_list,
        ['G.a'],
        root='G.a',
        test_persistency=False)

  def testNextAndUpdateTestList(self):
    test_list = self._SetStubStateInstance(self.test_list)
    iterator = test_list_iterator.TestListIterator(
        test_list, test_list=test_list)
    actual_sequence = []

    for unused_i in xrange(3):
      test_path = iterator.next()
      actual_sequence.append(test_path)
      test = test_list.lookup_path(test_path)
      test.update_state(status=factory.TestState.PASSED)

    self.assertListEqual(['a', 'b', 'G.a'], actual_sequence)

    # switch to new test list
    test_list = self._BuildTestList(
        """
    test_lists.FactoryTest(id='a', autotest_name='t_a')
    test_lists.FactoryTest(id='b', autotest_name='t_b')
    with test_lists.FactoryTest(id='G'):
      test_lists.FactoryTest(id='a', autotest_name='t_Ga')  # <- at here
      # test_lists.FactoryTest(id='b', autotest_name='t_Gb')  # removed
      with test_lists.TestGroup(id='G'):
        test_lists.FactoryTest(id='a', autotest_name='t_GGa')
        test_lists.FactoryTest(id='b', autotest_name='t_GGb')
        test_lists.FactoryTest(id='c', autotest_name='t_GGc')  # new
    test_lists.FactoryTest(id='c', autotest_name='t_c')
        """, self.OPTIONS)
    test_list = self._SetStubStateInstance(test_list)
    iterator.set_test_list(test_list)

    with self.assertRaises(StopIteration):
      for unused_i in xrange(10):
        test_path = iterator.next()
        actual_sequence.append(test_path)
        test = test_list.lookup_path(test_path)
        test.update_state(status=factory.TestState.PASSED)

    self.assertListEqual(
        ['a', 'b', 'G.a', 'G.G.a', 'G.G.b', 'G.G.c', 'c'], actual_sequence)

  def testGet(self):
    self._SetStubStateInstance(self.test_list)
    iterator = test_list_iterator.TestListIterator(
        self.test_list, test_list=self.test_list)

    # in the beginning, the iterator is not initialized, shall return None
    self.assertIsNone(iterator.get())
    with self.assertRaises(StopIteration):
      for unused_i in xrange(10):
        test_path = iterator.next()
        # get() shall return the same value as previous next()
        for unused_j in xrange(2):
          self.assertEqual(test_path, iterator.get())
    # get() shall return None when we reach the end (StopIteration).
    self.assertIsNone(iterator.get())

  def testRunIf(self):
    test_list = self._BuildTestList(
        """
    test_lists.FactoryTest(id='a', autotest_name='t_a')
    with test_lists.FactoryTest(id='G', run_if='foo.a'):
      test_lists.FactoryTest(id='a', autotest_name='t_Ga')
      with test_lists.TestGroup(id='G'):
        test_lists.FactoryTest(id='a', autotest_name='t_GGa')
    test_lists.FactoryTest(id='c', autotest_name='t_c')
        """, self.OPTIONS)
    self._AssertTestSequence(
        test_list,
        ['a', 'c'],
        aux_data={
            'foo': {
                'a': False,
            },
        })
    self._AssertTestSequence(
        test_list,
        ['a', 'G.a', 'G.G.a', 'c'],
        aux_data={
            'foo': {
                'a': True,
            },
        })

    test_list = self._BuildTestList(
        """
    test_lists.FactoryTest(id='a', autotest_name='t_a')
    with test_lists.FactoryTest(id='G'):
      test_lists.FactoryTest(id='a', autotest_name='t_Ga', run_if='foo.a')
      with test_lists.TestGroup(id='G', run_if='!foo.a'):
        test_lists.FactoryTest(id='a', autotest_name='t_GGa')
    test_lists.FactoryTest(id='c', autotest_name='t_c')
        """, self.OPTIONS)
    self._AssertTestSequence(
        test_list,
        ['a', 'G.G.a', 'c'],
        aux_data={
            'foo': {
                'a': False,
            },
        })
    self._AssertTestSequence(
        test_list,
        ['a', 'G.a', 'c'],
        aux_data={
            'foo': {
                'a': True,
            },
        })

  def testRunIfCannotSkipParent(self):
    """Make sure we cannot skip a parent test.

    If a test group starts running, changing to its run_if state won't make the
    reset of its child stop running.
    """
    test_list = self._BuildTestList(
        """
    with test_lists.FactoryTest(id='G', run_if='foo.a'):
      test_lists.FactoryTest(id='a', autotest_name='t_Ga', run_if='foo.a')
      with test_lists.TestGroup(id='G', run_if='foo.a'):
        test_lists.FactoryTest(id='a', autotest_name='t_GGa')
        test_lists.FactoryTest(id='b', autotest_name='t_GGa')
      test_lists.FactoryTest(id='b', autotest_name='t_Gb')
        """, self.OPTIONS)

    def run_test_1(path, aux_data):
      if path == 'G.G.a':
        aux_data['foo']['a'] = False
      return True
    self._AssertTestSequence(
        test_list,
        ['G.a', 'G.G.a', 'G.G.b', 'G.b'],
        aux_data={
            'foo': {
                'a': True,
            },
        },
        run_test=run_test_1)

    def run_test_2(path, aux_data):
      if path == 'G.a':
        aux_data['foo']['a'] = False
      return True
    self._AssertTestSequence(
        test_list,
        ['G.a', 'G.b'],
        aux_data={
            'foo': {
                'a': True,
            },
        },
        run_test=run_test_2)

  def testRunIfSetByOtherTest(self):
    """Changing aux data also changes run_if result for other tests.

    Test A that is prior to test B can change aux data and turn on / off test
    B.
    """
    test_list = self._BuildTestList(
        """
    test_lists.FactoryTest(id='a', autotest_name='t_a')
    test_lists.FactoryTest(id='b', autotest_name='t_b', run_if='foo.a')
        """, self.OPTIONS)

    # case 1: test 'a' set foo.a to True
    def run_test_1(path, aux_data):
      if path == 'a':
        aux_data['foo'] = {
            'a': True
        }
      return True
    self._AssertTestSequence(
        test_list,
        ['a', 'b'],
        run_test=run_test_1)

    # case 2: normal case
    self._AssertTestSequence(
        test_list,
        ['a'])

    # case 3: foo.a was True, but test 'a' set it to False
    def run_test_3(path, aux_data):
      if path == 'a':
        aux_data['foo'] = {
            'a': False
        }
      return True
    self._AssertTestSequence(
        test_list,
        ['a'],
        aux_data={
            'foo': {
                'a': True
            },
        },
        run_test=run_test_3)


if __name__ == '__main__':
  unittest.main()
