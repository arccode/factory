#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import cPickle as pickle
import logging
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy import test_list_iterator
from cros.factory.test import state
from cros.factory.test.test_lists import manager


PLAY_BUTTON_STATUS_FILTER = [
    'UNTESTED', 'ACTIVE', 'FAILED', 'FAILED_AND_WAIVED',
]


class TestListIteratorTest(unittest.TestCase):
  TEST_LIST = {}  # Overriden by subclasses

  def setUp(self):
    self.test_list_manager = mock.MagicMock(spec=manager.Manager)
    self.test_list = self._BuildTestList(self.TEST_LIST)

  def _BuildTestList(self, test_list_config):
    return manager.BuildTestListForUnittest(
        test_list_config=test_list_config)

  def _SetStubStateInstance(self, test_list):
    state_instance = state.StubFactoryState()
    test_list.state_instance = state_instance
    for test in test_list.GetAllTests():
      test.UpdateState(update_parent=False)
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
    self.assertListEqual(
        [frame.__dict__ for frame in iterator.stack],
        [frame.__dict__ for frame in deserialized_object.stack])
    self.assertEqual(iterator.status_filter,
                     deserialized_object.status_filter)
    return deserialized_object

  def _AssertTestSequence(self, test_list, expected_sequence,
                          root=None, test_persistency=False, device_data=None,
                          run_test=None, set_state=True, status_filter=None):
    """Helper function to check the test order.

    Args:
      test_list: the test_list to run
      expected_sequence: the expected test order
      root: starting from which test
      test_persistency: will serialize and deserialize the iterator between each
          next call.
      device_data: initial stub device_data
      run_test: a function will be called for each test returned by the
          iterator.  The signature is run_test(test_path, current_device_data).
          This function must return True if the test is considered passed, False
          otherwise.  This function can modify current_device_data or cause
          other side effects to affect the next or following tests.
      set_state: override current state of test_list
    """
    if not root:
      root = test_list
    if set_state:
      test_list = self._SetStubStateInstance(test_list)
    iterator = test_list_iterator.TestListIterator(
        root, test_list=test_list, status_filter=status_filter)
    actual_sequence = []
    if not run_test:
      run_test = lambda unused_path, unused_device_data: True

    device_data = device_data or {}
    # mock CheckRunIf
    def _MockedCheckRunIf(path):
      if device_data:
        test_list.state_instance.DataShelfSetValue('device', device_data)

      return test_list_iterator.TestListIterator.CheckRunIf(
          iterator,
          path)
    iterator.CheckRunIf = _MockedCheckRunIf

    max_iteration = len(expected_sequence) + 1

    try:
      with self.assertRaises(StopIteration):
        for unused_i in xrange(max_iteration):
          test_path = iterator.next()
          actual_sequence.append(test_path)
          test = test_list.LookupPath(test_path)
          if run_test(test_path, device_data):
            test.UpdateState(status=state.TestState.PASSED)
          else:
            test.UpdateState(status=state.TestState.FAILED)
          if test_persistency:
            iterator = self._testPickleSerializable(iterator)
            # the persistency of state instance is provided by
            # `cros.factory.goofy.goofy`
            # and `cros.factory.test.state`.  We assume that it just works.
            # So the test list itself won't be changed.
            iterator.SetTestList(test_list)
    except Exception:
      logging.error('actual_sequence: %r', actual_sequence)
      raise
    self.assertListEqual(expected_sequence, actual_sequence)


class TestListIteratorBaseTest(TestListIteratorTest):
  """Test test_list_iterator.TestListIterator.

  https://chromium.googlesource.com/chromiumos/platform/factory/+/master/py/test/test_lists/TEST_LIST.md
  """

  TEST_LIST = {
      'tests': [
          {'id': 'a', 'pytest_name': 't_a'},
          {'id': 'b', 'pytest_name': 't_b'},
          {'id': 'G',
           'subtests': [
               {'id': 'a', 'pytest_name': 't_Ga'},
               {'id': 'b', 'pytest_name': 't_Gb'},
               {'id': 'G',
                'subtests': [
                    {'id': 'a', 'pytest_name': 't_GGa'},
                    {'id': 'b', 'pytest_name': 't_GGb'},
                ]},
           ]},
          {'id': 'c', 'pytest_name': 't_c'},
      ]
  }

  def testInitFromRoot(self):
    root_path = self.test_list.ToFactoryTestList().path
    iterator = test_list_iterator.TestListIterator(root_path)

    self._testPickleSerializable(iterator)
    self.assertListEqual([root_path], [frame.node for frame in iterator.stack])

    iterator = test_list_iterator.TestListIterator(self.test_list)
    self._testPickleSerializable(iterator)
    self.assertListEqual([root_path], [frame.node for frame in iterator.stack])

  def testInitFromNonRoot(self):
    # 1. specify starting test by path string
    root_test = self.test_list.ToFactoryTestList().subtests[0]
    root_path = root_test.path
    iterator = test_list_iterator.TestListIterator(root_path)
    self._testPickleSerializable(iterator)
    self.assertListEqual([root_path], [frame.node for frame in iterator.stack])

    # 2. specify starting test by test object
    iterator = test_list_iterator.TestListIterator(root_test)
    self._testPickleSerializable(iterator)
    self.assertListEqual([root_path], [frame.node for frame in iterator.stack])

  def testInitWithStatusFilter(self):
    for status_filter in ([],
                          [state.TestState.FAILED],
                          [state.TestState.FAILED,
                           state.TestState.UNTESTED]):
      iterator = test_list_iterator.TestListIterator(
          root=self.test_list, status_filter=status_filter)
      self.assertListEqual(status_filter, iterator.status_filter)
      self._testPickleSerializable(iterator)

  def testStop(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'G', 'iterations': 2,
                 'subtests': [
                     {'id': 'G', 'iterations': 2,
                      'subtests': [
                          {'id': 'a', 'pytest_name': 't_Ga', 'iterations': 2},
                          {'id': 'b', 'pytest_name': 't_Gb', 'iterations': 2},
                      ]},
                     {'id': 'H', 'iterations': 2,
                      'subtests': [
                          {'id': 'a', 'pytest_name': 't_Ha', 'iterations': 2},
                          {'id': 'b', 'pytest_name': 't_Hb', 'iterations': 2},
                      ]},
                 ]}
            ]
        })
    test_list = self._SetStubStateInstance(test_list)
    iterator = test_list_iterator.TestListIterator(
        root=test_list, test_list=test_list)
    self.assertEqual('test:G.G.a', iterator.next())
    self.assertEqual('test:G.G.a', iterator.next())
    iterator.Stop('test:G.G')
    self.assertEqual('test:G.H.a', iterator.next())
    self.assertEqual('test:G.H.a', iterator.next())

  def testNext(self):
    self._AssertTestSequence(
        self.test_list,
        ['test:a', 'test:b', 'test:G.a', 'test:G.b', 'test:G.G.a', 'test:G.G.b',
         'test:c'],
        test_persistency=False)
    self._AssertTestSequence(
        self.test_list,
        ['test:a', 'test:b', 'test:G.a', 'test:G.b', 'test:G.G.a', 'test:G.G.b',
         'test:c'],
        test_persistency=True)

  def testNextStartFromNonRoot(self):
    self._AssertTestSequence(
        self.test_list,
        ['test:G.a', 'test:G.b', 'test:G.G.a', 'test:G.G.b'],
        root='G',
        test_persistency=True)
    self._AssertTestSequence(
        self.test_list,
        ['test:G.a', 'test:G.b', 'test:G.G.a', 'test:G.G.b'],
        root='G',
        test_persistency=False)
    self._AssertTestSequence(
        self.test_list,
        ['test:G.G.a', 'test:G.G.b'],
        root='G.G',
        test_persistency=False)
    self._AssertTestSequence(
        self.test_list,
        ['test:a'],
        root='a',
        test_persistency=False)
    self._AssertTestSequence(
        self.test_list,
        ['test:G.a'],
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
      test = test_list.LookupPath(test_path)
      test.UpdateState(status=state.TestState.PASSED)

    self.assertListEqual(['test:a', 'test:b', 'test:G.a'], actual_sequence)

    # switch to new test list
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'a', 'pytest_name': 't_a'},
                {'id': 'b', 'pytest_name': 't_b'},
                {'id': 'G',
                 'subtests': [
                     {'id': 'a', 'pytest_name': 't_Ga'},  # at here
                     # {'id': 'b', 'pytest_name': 't_Gb'},  # removed
                     {'id': 'G',
                      'subtests': [
                          {'id': 'a', 'pytest_name': 't_GGa'},
                          {'id': 'b', 'pytest_name': 't_GGb'},
                          {'id': 'c', 'pytest_name': 't_GGc'},  # new
                      ]},
                 ]},
                {'id': 'c', 'pytest_name': 't_c'},
            ]
        }
    )
    test_list = self._SetStubStateInstance(test_list)
    iterator.SetTestList(test_list)

    with self.assertRaises(StopIteration):
      for unused_i in xrange(10):
        test_path = iterator.next()
        actual_sequence.append(test_path)
        test = test_list.LookupPath(test_path)
        test.UpdateState(status=state.TestState.PASSED)

    self.assertListEqual(
        ['test:a', 'test:b', 'test:G.a', 'test:G.G.a', 'test:G.G.b',
         'test:G.G.c', 'test:c'], actual_sequence)

  def testGet(self):
    self._SetStubStateInstance(self.test_list)
    iterator = test_list_iterator.TestListIterator(
        self.test_list, test_list=self.test_list)

    with self.assertRaises(StopIteration):
      for unused_i in xrange(10):
        test_path = iterator.next()
        # Get() shall return the same value as previous next()
        for unused_j in xrange(2):
          self.assertEqual(test_path, iterator.Get())
    # Get() shall return None when we reach the end (StopIteration).
    self.assertIsNone(iterator.Get())

  def testRunIf(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'a', 'pytest_name': 't_a'},
                {'id': 'G', 'run_if': 'device.foo.a', 'subtests': [
                    {'id': 'a', 'pytest_name': 't_Ga'},
                    {'id': 'G', 'subtests': [
                        {'id': 'a', 'pytest_name': 't_GGa'},
                    ]},
                ]},
                {'id': 'c', 'pytest_name': 't_c'},
            ]
        })
    self._AssertTestSequence(
        test_list,
        ['test:a', 'test:c'],
        device_data={
            'foo': {
                'a': False,
            },
        })
    self._AssertTestSequence(
        test_list,
        ['test:a', 'test:G.a', 'test:G.G.a', 'test:c'],
        device_data={
            'foo': {
                'a': True,
            },
        })

    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'a', 'pytest_name': 't_a'},
                {'id': 'G', 'subtests': [
                    {'id': 'a', 'run_if': 'device.foo.a',
                     'pytest_name': 't_Ga'},
                    {'id': 'G', 'run_if': 'not device.foo.a', 'subtests': [
                        {'id': 'a', 'pytest_name': 't_GGa'},
                    ]},
                ]},
                {'id': 'c', 'pytest_name': 't_c'},
            ]
        })
    self._AssertTestSequence(
        test_list,
        ['test:a', 'test:G.G.a', 'test:c'],
        device_data={
            'foo': {
                'a': False,
            },
        })
    self._AssertTestSequence(
        test_list,
        ['test:a', 'test:G.a', 'test:c'],
        device_data={
            'foo': {
                'a': True,
            },
        })

  def testStatusFilter(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'G', 'inherit': 'TestGroup', 'subtests': [
                    {'id': 'a', 'pytest_name': 't_Ga'},
                    {'id': 'G', 'inherit': 'TestGroup', 'subtests': [
                        {'id': 'a', 'pytest_name': 't_GGa'},
                        {'id': 'b', 'pytest_name': 't_GGb'},
                    ]},
                    {'id': 'b', 'pytest_name': 't_Gb'},
                ]},
            ]
        })

    # no filter, all tests should be run
    test_list = self._SetStubStateInstance(test_list)
    test_list.LookupPath('G.a').UpdateState(status=state.TestState.PASSED)
    test_list.LookupPath('G.G.a').UpdateState(status=state.TestState.FAILED)
    self._AssertTestSequence(
        test_list,
        ['test:G.a', 'test:G.G.a', 'test:G.G.b', 'test:G.b'],
        set_state=False,
        status_filter=None)

    # only UNTESTED tests will be run
    test_list = self._SetStubStateInstance(test_list)
    test_list.LookupPath('G.a').UpdateState(status=state.TestState.PASSED)
    test_list.LookupPath('G.G.a').UpdateState(status=state.TestState.FAILED)
    self._AssertTestSequence(
        test_list,
        ['test:G.G.b', 'test:G.b'],
        set_state=False,
        status_filter=[state.TestState.UNTESTED])

    # UNTESTED or FAILED
    test_list = self._SetStubStateInstance(test_list)
    test_list.LookupPath('G.a').UpdateState(status=state.TestState.PASSED)
    test_list.LookupPath('G.G.a').UpdateState(status=state.TestState.FAILED)
    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:G.G.b', 'test:G.b'],
        set_state=False,
        status_filter=[state.TestState.UNTESTED, state.TestState.FAILED])

    # filter doesn't apply on non-leaf tests
    test_list = self._SetStubStateInstance(test_list)
    test_list.LookupPath('G.a').UpdateState(status=state.TestState.PASSED)
    test_list.LookupPath('G.G.a').UpdateState(status=state.TestState.FAILED)
    test_list.LookupPath('G').UpdateState(status=state.TestState.FAILED)
    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:G.G.b', 'test:G.b'],
        set_state=False,
        status_filter=[state.TestState.UNTESTED, state.TestState.FAILED])

  def testTestGroup(self):
    """Tests if we can handle TestGroup correctly.

    A test group means that the subtests have no dependency, for example,

      G
      |- G.a
      `- G.b

    If we passed G.a and failed G.b, we can retest G.b without running G.a
    again.

    On the other hand, if G is not a TestGroup, then it is an AutomatedSequence,
    which means that the subtests depend on each other.  Retesting G.b must
    retest G.a too.
    """
    test_list = self._BuildTestList(
        {
            'options': {
                'phase': 'PROTO',
                'skipped_tests': {'PROTO': ['J']},
            },
            'tests': [
                {'inherit': 'TestGroup', 'id': 'G', 'subtests': [
                    {'id': 'a', 'pytest_name': 'a'},
                    {'id': 'b', 'pytest_name': 'b'},
                ]},
                {'inherit': 'FactoryTest', 'id': 'H', 'subtests': [
                    {'id': 'a', 'pytest_name': 'a'},
                    {'id': 'b', 'pytest_name': 'b'},
                ]},
                {'inherit': 'FactoryTest', 'id': 'I', 'subtests': [
                    {'id': 'a', 'pytest_name': 'a'},
                    {'id': 'b', 'pytest_name': 'b'},
                ]},
                {'inherit': 'FactoryTest', 'id': 'J', 'subtests': [
                    {'id': 'a', 'pytest_name': 'a'},
                    {'id': 'b', 'pytest_name': 'b'},
                ]},
            ]
        })
    # G is a test group, H, I, J are AutomatedSequences
    test_list = self._SetStubStateInstance(test_list)
    test_list.SetSkippedAndWaivedTests()
    test_list.LookupPath('G.a').UpdateState(status=state.TestState.PASSED)
    test_list.LookupPath('G.b').UpdateState(status=state.TestState.FAILED)
    test_list.LookupPath('H.a').UpdateState(status=state.TestState.PASSED)
    test_list.LookupPath('H.b').UpdateState(status=state.TestState.FAILED)
    test_list.LookupPath('I.a').UpdateState(status=state.TestState.PASSED)
    test_list.LookupPath('I.b').UpdateState(status=state.TestState.PASSED)
    self._AssertTestSequence(
        test_list,
        ['test:G.b', 'test:H.a', 'test:H.b'],
        set_state=False,
        # since tests will be reset to UNTESTED, so untested must be included
        status_filter=[state.TestState.FAILED, state.TestState.UNTESTED])

  def testSkippedAndRerun(self):
    test_list = self._BuildTestList(
        {
            'options': {
                'phase': 'PROTO',
                'skipped_tests': {'PROTO': ['G.a']},
            },
            'tests': [
                {'inherit': 'TestGroup', 'id': 'G', 'subtests': [
                    {'id': 'a', 'pytest_name': 'a'},
                ]},
            ]
        })
    test_list = self._SetStubStateInstance(test_list)
    test_list.SetSkippedAndWaivedTests()
    self._AssertTestSequence(
        test_list,
        [],
        set_state=False,
        status_filter=PLAY_BUTTON_STATUS_FILTER)
    self.assertEqual(test_list.LookupPath('G').GetState().status,
                     state.TestState.SKIPPED)
    # Rerun tests, test groups should first be reset to untested and try to find
    # subtests to run.  When we leave the test group, we should compute overall
    # test status again.  Therefore, nothing should be run, and the test status
    # of 'G' should still be 'SKIPPED'
    self._AssertTestSequence(
        test_list,
        [],
        set_state=False,
        status_filter=PLAY_BUTTON_STATUS_FILTER)
    self.assertEqual(test_list.LookupPath('G').GetState().status,
                     state.TestState.SKIPPED)

  def testSkipInParallelGroup(self):
    test_list = self._BuildTestList(
        {
            'options': {
                'phase': 'PROTO',
                'skipped_tests': {'PROTO': ['G.a']},
            },
            'tests': [
                {'inherit': 'TestGroup', 'id': 'G', 'parallel': True,
                 'subtests': [
                     {'id': 'a', 'pytest_name': 'a'},
                     {'id': 'b', 'pytest_name': 'b'},
                 ]},
                {'id': 'c', 'pytest_name': 'c'},
            ]
        })
    test_list = self._SetStubStateInstance(test_list)
    test_list.SetSkippedAndWaivedTests()
    test_list.LookupPath('G.b').UpdateState(status=state.TestState.PASSED)
    test_list.LookupPath('c').UpdateState(status=state.TestState.FAILED)
    self._AssertTestSequence(
        test_list,
        ['test:c'],
        set_state=False,
        status_filter=PLAY_BUTTON_STATUS_FILTER)

  def testSkippedAndUnset(self):
    test_list = self._BuildTestList(
        {
            'options': {
                'phase': 'PROTO',
            },
            'tests': [
                {'inherit': 'TestGroup', 'id': 'G', 'subtests': [
                    {'id': 'a', 'pytest_name': 'a'},
                ]},
            ]
        })
    test_list = self._SetStubStateInstance(test_list)
    test_list.LookupPath('G.a').UpdateState(status=state.TestState.SKIPPED)
    test_list.LookupPath('G').UpdateState(status=state.TestState.SKIPPED)
    self._AssertTestSequence(
        test_list,
        ['test:G.a'],
        set_state=False,
        status_filter=PLAY_BUTTON_STATUS_FILTER)

  def testRunIfAndAutomatedSequence(self):
    test_list = self._BuildTestList(
        {
            'options': {
                'phase': 'PROTO',
            },
            'tests': [
                {'id': 'G', 'subtests': [
                    {'id': 'a', 'pytest_name': 'a'},
                    {'id': 'b', 'pytest_name': 'b', 'run_if': 'device.foo.a'},
                    {'id': 'c', 'pytest_name': 'c'}, ]},
            ]
        })
    test_list = self._SetStubStateInstance(test_list)
    self._AssertTestSequence(
        test_list,
        ['test:G.a', 'test:G.c'],
        set_state=False,
        device_data={
            'foo': {
                'a': False,
            },
        })
    self.assertEqual(test_list.LookupPath('G').GetState().status,
                     state.TestState.SKIPPED)
    self._AssertTestSequence(
        test_list,
        [],
        set_state=False,
        status_filter=PLAY_BUTTON_STATUS_FILTER,
        device_data={
            'foo': {
                'a': False,
            },
        })
    self._AssertTestSequence(
        test_list,
        ['test:G.a', 'test:G.b', 'test:G.c'],
        set_state=False,
        status_filter=PLAY_BUTTON_STATUS_FILTER,
        device_data={
            'foo': {
                'a': True,
            },
        })
    self.assertEqual(test_list.LookupPath('G').GetState().status,
                     state.TestState.PASSED)
    self._AssertTestSequence(
        test_list,
        [],
        set_state=False,
        status_filter=PLAY_BUTTON_STATUS_FILTER,
        device_data={
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
        {
            'tests': [
                {'id': 'G', 'run_if': 'device.foo.a', 'subtests': [
                    {'id': 'a', 'pytest_name': 'a', 'run_if': 'device.foo.a'},
                    {'id': 'G', 'run_if': 'device.foo.a', 'subtests': [
                        {'id': 'a', 'pytest_name': 'a'},
                        {'id': 'b', 'pytest_name': 'b'},
                    ]},
                    {'id': 'b', 'pytest_name': 'b'},
                ]},
            ]
        })

    def run_test_1(path, device_data):
      if path == 'test:G.G.a':
        device_data['foo']['a'] = False
      return True
    self._AssertTestSequence(
        test_list,
        ['test:G.a', 'test:G.G.a', 'test:G.G.b', 'test:G.b'],
        device_data={
            'foo': {
                'a': True,
            },
        },
        run_test=run_test_1)

    def run_test_2(path, device_data):
      if path == 'test:G.a':
        device_data['foo']['a'] = False
      return True
    self._AssertTestSequence(
        test_list,
        ['test:G.a', 'test:G.b'],
        device_data={
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
        {
            'tests': [
                {'id': 'a', 'pytest_name': 'a'},
                {'id': 'b', 'pytest_name': 'b', 'run_if': 'device.foo.a'},
            ]
        })

    # case 1: test 'a' set foo.a to True
    def run_test_1(path, device_data):
      if path == 'test:a':
        device_data['foo'] = {
            'a': True
        }
      return True
    self._AssertTestSequence(
        test_list,
        ['test:a', 'test:b'],
        run_test=run_test_1)

    # case 2: normal case
    self._AssertTestSequence(
        test_list,
        ['test:a'])

    # case 3: foo.a was True, but test 'a' set it to False
    def run_test_3(path, device_data):
      if path == 'test:a':
        device_data['foo'] = {
            'a': False
        }
      return True
    self._AssertTestSequence(
        test_list,
        ['test:a'],
        device_data={
            'foo': {
                'a': True
            },
        },
        run_test=run_test_3)


class TestListIteratorParallelTest(TestListIteratorTest):
  TEST_LIST = {
      'tests': [
          {'id': 'a', 'pytest_name': 't_a'},
          {'id': 'b', 'pytest_name': 't_b'},
          {'id': 'G', 'subtests': [
              {'id': 'a', 'pytest_name': 't_a'},
              {'id': 'b', 'pytest_name': 't_b'},
              {'id': 'G', 'parallel': True, 'subtests': [
                  {'id': 'a', 'pytest_name': 't_a'},
                  {'id': 'b', 'pytest_name': 't_b'},
              ]},
              {'id': 'H', 'subtests': [
                  {'id': 'a', 'pytest_name': 't_a'},
                  {'id': 'b', 'pytest_name': 't_b'},
              ]},
          ]},
          {'id': 'c', 'pytest_name': 't_c'},
      ]
  }
  def testParallel(self):
    """Test cases for FactoryTest.parallel option.

    https://chromium.googlesource.com/chromiumos/platform/factory/+/master/py/test/test_lists/TEST_LIST.md#Parallel-Tests
    """
    self._AssertTestSequence(
        self.test_list,
        ['test:a', 'test:b', 'test:G.a', 'test:G.b', 'test:G.G', 'test:G.H.a',
         'test:G.H.b', 'test:c'])


class TestListIteratorActionOnFailureTest(TestListIteratorTest):
  """Test behavior of action_on_failure attribute.

  https://chromium.googlesource.com/chromiumos/platform/factory/+/master/py/test/test_lists/TEST_LIST.md#Action-On-Failure
  """
  def testActionOnFailureNext(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'G', 'subtests': [
                    {'id': 'a', 'pytest_name': 'a',
                     'action_on_failure': 'NEXT'},
                    {'id': 'b', 'pytest_name': 'b',
                     'action_on_failure': 'NEXT'},
                ]},
                {'id': 'c', 'pytest_name': 'c',
                 'action_on_failure': 'NEXT'},
            ]
        })
    self._AssertTestSequence(
        test_list,
        ['test:G.a', 'test:G.b', 'test:c'],
        run_test=lambda path, unused_device_data: path not in set(['test:G.a']))

  def testActionOnFailureParentOneLayer(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'G', 'subtests': [
                    {'id': 'a', 'pytest_name': 'a',
                     'action_on_failure': 'PARENT'},
                    {'id': 'b', 'pytest_name': 'b'},
                ]},
                {'id': 'c', 'pytest_name': 'c'},
            ]
        })
    self._AssertTestSequence(
        test_list,
        ['test:G.a', 'test:c'],
        run_test=lambda path, unused_device_data: path not in set(['test:G.a']))

  def testActionOnFailureParentTwoLayer(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'G', 'subtests': [
                    {'id': 'G', 'action_on_failure': 'PARENT', 'subtests': [
                        {'id': 'a', 'pytest_name': 'a',
                         'action_on_failure': 'PARENT'},
                        {'id': 'b', 'pytest_name': 'b'},
                    ]},
                    {'id': 'c', 'pytest_name': 'c'},
                ]},
                {'id': 'd', 'pytest_name': 'd'},
            ]
        })
    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:d'],
        run_test=lambda path, unused_device_data: path not in set(
            ['test:G.G.a']))

  def testActionOnFailureStop(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'G', 'subtests': [
                    {'id': 'G', 'action_on_failure': 'STOP', 'subtests': [
                        {'id': 'a', 'pytest_name': 'a',
                         'action_on_failure': 'STOP'},
                        {'id': 'b', 'pytest_name': 'b'},
                    ]},
                    {'id': 'c', 'pytest_name': 'c'},
                ]},
                {'id': 'd', 'pytest_name': 'd'},
            ]
        })
    self._AssertTestSequence(
        test_list,
        ['test:G.G.a'],
        run_test=lambda path, unused_device_data: path not in set(
            ['test:G.G.a']))

    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:G.G.b'],
        run_test=lambda path, unused_device_data: path not in set(
            ['test:G.G.b']))


class TestListIteratorTeardownTest(TestListIteratorTest):
  """Test handling teardown processes.

  https://chromium.googlesource.com/chromiumos/platform/factory/+/master/py/test/test_lists/TEST_LIST.md#Teardown
  """
  def testTeardown(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'G', 'subtests': [
                    {'id': 'G', 'subtests': [
                        {'id': 'a', 'pytest_name': 'a'},
                        {'id': 'b', 'pytest_name': 'b'},
                        {'id': 'w', 'pytest_name': 'w', 'teardown': True},
                        {'id': 'x', 'pytest_name': 'x', 'teardown': True},
                        {'id': 'TG', 'teardown': True, 'subtests': [
                            {'id': 'y', 'pytest_name': 'y'},
                            {'id': 'z', 'pytest_name': 'z'},
                        ]}
                    ]},
                    {'id': 'c', 'pytest_name': 'c'},
                    {'id': 'T', 'pytest_name': 'T', 'teardown': True},
                ]},
                {'id': 'd', 'pytest_name': 'd'},
            ]
        })
    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:G.G.b', 'test:G.G.w', 'test:G.G.x',
         'test:G.G.TG.y', 'test:G.G.TG.z', 'test:G.c', 'test:G.T', 'test:d'],
        run_test=lambda path, unused_device_data: path not in set(
            ['test:G.G.a']))

  def testTeardownAfterStop(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'G', 'subtests': [
                    {'id': 'G', 'subtests': [
                        {'id': 'a', 'pytest_name': 'a',
                         'action_on_failure': 'STOP'},
                        {'id': 'b', 'pytest_name': 'b'},
                        {'id': 'w', 'pytest_name': 'w', 'teardown': True},
                        {'id': 'x', 'pytest_name': 'x', 'teardown': True},
                        {'id': 'TG', 'teardown': True, 'subtests': [
                            {'id': 'y', 'pytest_name': 'y'},
                            {'id': 'z', 'pytest_name': 'z'},
                        ]}
                    ]},
                    {'id': 'c', 'pytest_name': 'c'},
                    {'id': 'T', 'pytest_name': 'T', 'teardown': True},
                ]},
                {'id': 'd', 'pytest_name': 'd'},
            ]
        })

    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:G.G.w', 'test:G.G.x', 'test:G.G.TG.y',
         'test:G.G.TG.z', 'test:G.T'],
        run_test=lambda path, unused_device_data: path not in set([
            'test:G.G.a']))


class TestListIteratorIterationTest(TestListIteratorTest):
  def testIterations(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'G', 'iterations': 2, 'subtests': [
                    {'id': 'G', 'iterations': 2, 'subtests': [
                        {'id': 'a', 'pytest_name': 'a', 'iterations': 2},
                        {'id': 'b', 'pytest_name': 'b', 'iterations': 2},
                    ]},
                ]},
            ]
        })
    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:G.G.a', 'test:G.G.b', 'test:G.G.b'] * 4)
    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:G.G.a', 'test:G.G.b', 'test:G.G.b'] * 4,
        root='G')

  def testRetries(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'G', 'retries': 1, 'subtests': [
                    {'id': 'G', 'retries': 1, 'subtests': [
                        {'id': 'a', 'pytest_name': 'a', 'retries': 1},
                        {'id': 'b', 'pytest_name': 'b', 'retries': 1},
                    ]},
                ]},
            ]
        })
    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:G.G.a', 'test:G.G.b', 'test:G.G.b'] * 4,
        run_test=lambda unused_path, unused_device_data: False)
    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:G.G.a', 'test:G.G.b', 'test:G.G.b'] * 4,
        root='G',
        run_test=lambda unused_path, unused_device_data: False)

  def testRetriesWithTeardown(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'G', 'retries': 1, 'subtests': [
                    {'id': 'G', 'retries': 1, 'subtests': [
                        {'id': 'a', 'pytest_name': 'a', 'retries': 1},
                        {'id': 'b', 'pytest_name': 'b', 'retries': 1,
                         'teardown': True},
                    ]},
                ]},
            ]
        })
    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:G.G.a', 'test:G.G.b'] * 4,
        run_test=lambda path, unused_device_data: path not in set(
            ['test:G.G.a']))
    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:G.G.a', 'test:G.G.b'] * 4,
        root='G',
        run_test=lambda path, unused_device_data: path not in set(
            ['test:G.G.a']))

  def testActionOnFailureStop(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'G', 'retries': 1, 'subtests': [
                    {'id': 'G', 'retries': 1, 'action_on_failure': 'STOP',
                     'subtests': [
                         {'id': 'a', 'pytest_name': 'a',
                          'action_on_failure': 'STOP'},
                         {'id': 'b', 'pytest_name': 'b'},
                     ]},
                    {'id': 'c', 'pytest_name': 'c'},
                ]},
                {'id': 'd', 'pytest_name': 'd'},
            ]
        })
    self._AssertTestSequence(
        test_list,
        ['test:G.G.a'] * 4,
        run_test=lambda path, unused_device_data: path not in set(
            ['test:G.G.a']))

    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:G.G.b'] * 4,
        run_test=lambda path, unused_device_data: path not in set(
            ['test:G.G.b']))

  def testTeardownAfterStop(self):
    test_list = self._BuildTestList(
        {
            'tests': [
                {'id': 'G', 'retries': 1, 'subtests': [
                    {'id': 'G', 'subtests': [
                        {'id': 'a', 'pytest_name': 'a',
                         'action_on_failure': 'STOP'},
                        {'id': 'b', 'pytest_name': 'b'},
                        {'id': 'w', 'pytest_name': 'w', 'teardown': True},
                        {'id': 'x', 'pytest_name': 'x', 'teardown': True},
                        {'id': 'TG', 'teardown': True, 'subtests': [
                            {'id': 'y', 'pytest_name': 'y'},
                            {'id': 'z', 'pytest_name': 'z'},
                        ]}
                    ]},
                    {'id': 'c', 'pytest_name': 'c'},
                    {'id': 'T', 'pytest_name': 'T', 'teardown': True},
                ]},
                {'id': 'd', 'pytest_name': 'd'},
            ]
        })

    self._AssertTestSequence(
        test_list,
        ['test:G.G.a', 'test:G.G.w', 'test:G.G.x', 'test:G.G.TG.y',
         'test:G.G.TG.z', 'test:G.T'] * 2,
        run_test=lambda path, unused_device_data: path not in set(
            ['test:G.G.a']))


if __name__ == '__main__':
  unittest.main()
