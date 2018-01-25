#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.test.pytests import factory_state
from cros.factory.test import state
from cros.factory.test.test_lists import manager
from cros.factory.utils import type_utils


class FactoryStateUnittest(unittest.TestCase):
  def setUp(self):
    self.device_state = state.StubFactoryState()
    self.station_state = state.StubFactoryState()

    self.test = factory_state.ManipulateFactoryStateLayer()

  def testCopyFromDUT(self):
    station_test_list = manager.BuildTestListForUnittest(
        {'tests': [
            {'id': 'a', 'subtests': [
                {'id': 'a', 'pytest_name': 'a'},
                {'id': 'b', 'pytest_name': 'b'},
                {'id': 'c', 'pytest_name': 'c'}, ]}, ]})

    self.device_state.data_shelf['k'] = 'v'
    self.device_state.update_test_state('', status='PASSED')
    self.device_state.update_test_state('a', status='PASSED')
    self.device_state.update_test_state('a.a', status='PASSED')
    self.device_state.update_test_state('a.b', status='PASSED')
    self.device_state.update_test_state('a.c', status='PASSED')
    self.device_state.update_test_state('b', status='PASSED')
    self.device_state.update_test_state('b.a', status='PASSED')
    self.device_state.update_test_state('b.b', status='PASSED')
    self.device_state.update_test_state('b.c', status='PASSED')

    self.station_state.data_shelf['k'] = 'u'
    self.station_state.update_test_state('', status='ACTIVE')
    self.station_state.update_test_state('a', status='ACTIVE')
    self.station_state.update_test_state('a.a', status='PASSED')
    self.station_state.update_test_state('a.b', status='ACTIVE')
    self.station_state.update_test_state('a.c', status='UNTESTED')

    self.test.args = type_utils.AttrDict(exclude_current_test_list=True,
                                         include_tests=True)
    self.test.path = 'a.b'
    self.test.test_info = mock.MagicMock()
    self.test.test_info.ReadTestList.return_value = station_test_list

    self.test.DoCopy(self.device_state, self.station_state)

    self.assertEqual(self.station_state.data_shelf['k'].Get(), 'v')

    self.assertItemsEqual(self.device_state.get_test_paths(),
                          ['', 'a', 'a.a', 'a.b', 'a.c',
                           'b', 'b.a', 'b.b', 'b.c'])
    # Test states for 'b', 'b.*' are copied from DUT.
    self.assertItemsEqual(self.station_state.get_test_paths(),
                          ['', 'a', 'a.a', 'a.b', 'a.c',
                           'b', 'b.a', 'b.b', 'b.c'])
    self.assertEqual('PASSED', self.station_state.get_test_state('b').status)
    self.assertEqual('PASSED', self.station_state.get_test_state('b.a').status)
    self.assertEqual('PASSED', self.station_state.get_test_state('b.b').status)
    self.assertEqual('PASSED', self.station_state.get_test_state('b.c').status)

    self.assertEqual('ACTIVE', self.station_state.get_test_state('').status)
    self.assertEqual('ACTIVE', self.station_state.get_test_state('a').status)
    self.assertEqual('PASSED', self.station_state.get_test_state('a.a').status)
    self.assertEqual('ACTIVE', self.station_state.get_test_state('a.b').status)
    self.assertEqual(
        'UNTESTED', self.station_state.get_test_state('a.c').status)

  def testCopyFromDUTRetestOnlyStation(self):
    station_test_list = manager.BuildTestListForUnittest(
        {'tests': [
            {'id': 'a', 'subtests': [
                {'id': 'a', 'pytest_name': 'a'},
                {'id': 'b', 'pytest_name': 'b'},
                {'id': 'c', 'pytest_name': 'c'}, ]}, ]})

    self.device_state.data_shelf['k'] = 'v'
    self.device_state.update_test_state('', status='PASSED')
    self.device_state.update_test_state('a', status='PASSED')
    self.device_state.update_test_state('a.a', status='PASSED')
    self.device_state.update_test_state('a.b', status='PASSED')
    self.device_state.update_test_state('a.c', status='PASSED')

    self.station_state.data_shelf['k'] = 'u'
    self.station_state.update_test_state('', status='ACTIVE')
    self.station_state.update_test_state('a', status='ACTIVE')
    self.station_state.update_test_state('a.a', status='PASSED')
    self.station_state.update_test_state('a.b', status='ACTIVE')
    self.station_state.update_test_state('a.c', status='UNTESTED')

    self.test.args = type_utils.AttrDict(exclude_current_test_list=True,
                                         include_tests=True)
    self.test.path = 'a.b'
    self.test.test_info = mock.MagicMock()
    self.test.test_info.ReadTestList.return_value = station_test_list

    self.test.DoCopy(self.device_state, self.station_state)

    self.assertEqual(self.station_state.data_shelf['k'].Get(), 'v')

    self.assertItemsEqual(self.device_state.get_test_paths(),
                          ['', 'a', 'a.a', 'a.b', 'a.c'])
    self.assertItemsEqual(self.station_state.get_test_paths(),
                          ['', 'a', 'a.a', 'a.b', 'a.c'])
    self.assertEqual('ACTIVE', self.station_state.get_test_state('').status)
    self.assertEqual('ACTIVE', self.station_state.get_test_state('a').status)
    self.assertEqual('PASSED', self.station_state.get_test_state('a.a').status)
    self.assertEqual('ACTIVE', self.station_state.get_test_state('a.b').status)
    self.assertEqual(
        'UNTESTED', self.station_state.get_test_state('a.c').status)

  def testCopyToDUT(self):
    station_test_list = manager.BuildTestListForUnittest(
        {'tests': [
            {'id': 'a', 'subtests': [
                {'id': 'a', 'pytest_name': 'a'},
                {'id': 'b', 'pytest_name': 'b'},
                {'id': 'c', 'pytest_name': 'c'}, ]}, ]})

    self.device_state.data_shelf['k'] = 'v'
    self.device_state.update_test_state('', status='UNTESTED')
    self.device_state.update_test_state('a', status='UNTESTED')
    self.device_state.update_test_state('a.a', status='UNTESTED')
    self.device_state.update_test_state('a.b', status='UNTESTED')
    self.device_state.update_test_state('a.c', status='UNTESTED')
    self.device_state.update_test_state('b', status='PASSED')
    self.device_state.update_test_state('b.a', status='PASSED')
    self.device_state.update_test_state('b.b', status='PASSED')
    self.device_state.update_test_state('b.c', status='PASSED')

    self.station_state.data_shelf['k'] = 'u'
    self.station_state.update_test_state('', status='ACTIVE')
    self.station_state.update_test_state('a', status='ACTIVE')
    self.station_state.update_test_state('a.a', status='PASSED')
    self.station_state.update_test_state('a.b', status='ACTIVE')
    self.station_state.update_test_state('a.c', status='UNTESTED')

    self.test.args = type_utils.AttrDict(exclude_current_test_list=False,
                                         include_tests=True)
    self.test.path = 'a.b'
    self.test.test_info = mock.MagicMock()
    self.test.test_info.ReadTestList.return_value = station_test_list

    self.test.DoCopy(self.station_state, self.device_state)

    self.assertEqual(self.device_state.data_shelf['k'].Get(), 'u')

    self.assertItemsEqual(self.device_state.get_test_paths(),
                          ['', 'a', 'a.a', 'a.b', 'a.c',
                           'b', 'b.a', 'b.b', 'b.c'])
    self.assertItemsEqual(self.station_state.get_test_paths(),
                          ['', 'a', 'a.a', 'a.b', 'a.c'])
    self.assertEqual('PASSED', self.device_state.get_test_state('b').status)
    self.assertEqual('PASSED', self.device_state.get_test_state('b.a').status)
    self.assertEqual('PASSED', self.device_state.get_test_state('b.b').status)
    self.assertEqual('PASSED', self.device_state.get_test_state('b.c').status)

    self.assertEqual('ACTIVE', self.device_state.get_test_state('a').status)
    self.assertEqual('PASSED', self.device_state.get_test_state('a.a').status)
    self.assertEqual('ACTIVE', self.device_state.get_test_state('a.b').status)
    self.assertEqual(
        'UNTESTED', self.device_state.get_test_state('a.c').status)

  def testCopyExcludeTest(self):
    station_test_list = manager.BuildTestListForUnittest(
        {'tests': [
            {'id': 'a', 'subtests': [
                {'id': 'a', 'pytest_name': 'a'},
                {'id': 'b', 'pytest_name': 'b'},
                {'id': 'c', 'pytest_name': 'c'}, ]}, ]})

    self.device_state.data_shelf['k'] = 'v'
    self.device_state.update_test_state('', status='UNTESTED')
    self.device_state.update_test_state('a', status='FAILED')
    self.device_state.update_test_state('a.a', status='FAILED')
    self.device_state.update_test_state('a.b', status='FAILED')
    self.device_state.update_test_state('a.c', status='FAILED')
    self.device_state.update_test_state('b', status='PASSED')
    self.device_state.update_test_state('b.a', status='PASSED')
    self.device_state.update_test_state('b.b', status='PASSED')
    self.device_state.update_test_state('b.c', status='PASSED')

    self.station_state.data_shelf['k'] = 'u'
    self.station_state.update_test_state('', status='ACTIVE')
    self.station_state.update_test_state('a', status='ACTIVE')
    self.station_state.update_test_state('a.a', status='PASSED')
    self.station_state.update_test_state('a.b', status='ACTIVE')
    self.station_state.update_test_state('a.c', status='UNTESTED')

    self.test.args = type_utils.AttrDict(exclude_current_test_list=True,
                                         include_tests=False)
    self.test.path = 'a.b'
    self.test.test_info = mock.MagicMock()
    self.test.test_info.ReadTestList.return_value = station_test_list

    self.test.DoCopy(self.station_state, self.device_state)

    self.assertEqual(self.device_state.data_shelf['k'].Get(), 'u')

    # Test states Should not change.
    self.assertItemsEqual(self.device_state.get_test_paths(),
                          ['', 'a', 'a.a', 'a.b', 'a.c',
                           'b', 'b.a', 'b.b', 'b.c'])
    self.assertItemsEqual(self.station_state.get_test_paths(),
                          ['', 'a', 'a.a', 'a.b', 'a.c'])
    self.assertEqual('PASSED', self.device_state.get_test_state('b').status)
    self.assertEqual('PASSED', self.device_state.get_test_state('b.a').status)
    self.assertEqual('PASSED', self.device_state.get_test_state('b.b').status)
    self.assertEqual('PASSED', self.device_state.get_test_state('b.c').status)
    self.assertEqual('FAILED', self.device_state.get_test_state('a').status)
    self.assertEqual('FAILED', self.device_state.get_test_state('a.a').status)
    self.assertEqual('FAILED', self.device_state.get_test_state('a.b').status)
    self.assertEqual('FAILED', self.device_state.get_test_state('a.c').status)


if __name__ == '__main__':
  unittest.main()
