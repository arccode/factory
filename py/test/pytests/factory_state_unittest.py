#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import tempfile
import threading
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.goofy import goofy_server
from cros.factory.test.pytests import factory_state
from cros.factory.test import state
from cros.factory.test.test_lists import manager
from cros.factory.utils import net_utils
from cros.factory.utils import type_utils


class FactoryStateUnittest(unittest.TestCase):
  def setUp(self):
    self.device_state = state.StubFactoryState()
    self.station_state = state.StubFactoryState()

    self.test = factory_state.ManipulateFactoryStateLayer()

  def tearDown(self):
    if self.device_state.GetLayerCount() > 1:
      self.test.DoMerge(self.device_state, self.station_state)
    if self.station_state.GetLayerCount() > 1:
      self.test.DoMerge(self.station_state, self.device_state)

  def _SetDataShelf(self):
    self.device_state.data_shelf_set_value(u'k', u'device')
    self.device_state.data_shelf_set_value(state.KEY_DEVICE_DATA,
                                           {u'foo': u'device'})
    self.station_state.data_shelf_set_value(u'k', u'station')
    self.station_state.data_shelf_set_value(state.KEY_DEVICE_DATA,
                                            {u'foo': u'station'})

  def testCopyFromDUT(self):
    station_test_list = manager.BuildTestListForUnittest(
        {'tests': [
            {'id': 'a', 'subtests': [
                {'id': 'a', 'pytest_name': 'a'},
                {'id': 'b', 'pytest_name': 'b'},
                {'id': 'c', 'pytest_name': 'c'}, ]}, ]})

    self._SetDataShelf()

    self.device_state.update_test_state(path='', status='PASSED')
    self.device_state.update_test_state(path='a', status='PASSED')
    self.device_state.update_test_state(path='a.a', status='PASSED')
    self.device_state.update_test_state(path='a.b', status='PASSED')
    self.device_state.update_test_state(path='a.c', status='PASSED')
    self.device_state.update_test_state(path='b', status='PASSED')
    self.device_state.update_test_state(path='b.a', status='PASSED')
    self.device_state.update_test_state(path='b.b', status='PASSED')
    self.device_state.update_test_state(path='b.c', status='PASSED')

    self.station_state.update_test_state(path='', status='ACTIVE')
    self.station_state.update_test_state(path='a', status='ACTIVE')
    self.station_state.update_test_state(path='a.a', status='PASSED')
    self.station_state.update_test_state(path='a.b', status='ACTIVE')
    self.station_state.update_test_state(path='a.c', status='UNTESTED')

    self.test.args = type_utils.AttrDict(exclude_current_test_list=True,
                                         include_tests=True)
    self.test.path = 'a.b'
    self.test.test_info = mock.MagicMock()
    self.test.test_info.ReadTestList.return_value = station_test_list

    self.test.DoCopy(self.device_state, self.station_state)

    self.assertEqual(self.device_state.data_shelf['k'].Get(), 'device')
    self.assertEqual(self.station_state.data_shelf['k'].Get(), 'station')
    self.assertEqual(
        self.station_state.data_shelf[state.KEY_DEVICE_DATA]['foo'].Get(),
        'device')
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

    self._SetDataShelf()
    self.device_state.update_test_state(path='', status='PASSED')
    self.device_state.update_test_state(path='a', status='PASSED')
    self.device_state.update_test_state(path='a.a', status='PASSED')
    self.device_state.update_test_state(path='a.b', status='PASSED')
    self.device_state.update_test_state(path='a.c', status='PASSED')

    self.station_state.update_test_state(path='', status='ACTIVE')
    self.station_state.update_test_state(path='a', status='ACTIVE')
    self.station_state.update_test_state(path='a.a', status='PASSED')
    self.station_state.update_test_state(path='a.b', status='ACTIVE')
    self.station_state.update_test_state(path='a.c', status='UNTESTED')

    self.test.args = type_utils.AttrDict(exclude_current_test_list=True,
                                         include_tests=True)
    self.test.path = 'a.b'
    self.test.test_info = mock.MagicMock()
    self.test.test_info.ReadTestList.return_value = station_test_list

    self.test.DoCopy(self.device_state, self.station_state)

    self.assertEqual(self.device_state.data_shelf['k'].Get(), 'device')
    self.assertEqual(self.station_state.data_shelf['k'].Get(), 'station')
    self.assertEqual(
        self.station_state.data_shelf[state.KEY_DEVICE_DATA]['foo'].Get(),
        'device')
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

    self._SetDataShelf()
    self.device_state.update_test_state(path='', status='UNTESTED')
    self.device_state.update_test_state(path='a', status='UNTESTED')
    self.device_state.update_test_state(path='a.a', status='UNTESTED')
    self.device_state.update_test_state(path='a.b', status='UNTESTED')
    self.device_state.update_test_state(path='a.c', status='UNTESTED')
    self.device_state.update_test_state(path='b', status='PASSED')
    self.device_state.update_test_state(path='b.a', status='PASSED')
    self.device_state.update_test_state(path='b.b', status='PASSED')
    self.device_state.update_test_state(path='b.c', status='PASSED')

    self.station_state.update_test_state(path='', status='ACTIVE')
    self.station_state.update_test_state(path='a', status='ACTIVE')
    self.station_state.update_test_state(path='a.a', status='PASSED')
    self.station_state.update_test_state(path='a.b', status='ACTIVE')
    self.station_state.update_test_state(path='a.c', status='UNTESTED')

    self.test.args = type_utils.AttrDict(exclude_current_test_list=False,
                                         include_tests=True)
    self.test.path = 'a.b'
    self.test.test_info = mock.MagicMock()
    self.test.test_info.ReadTestList.return_value = station_test_list

    self.test.DoCopy(self.station_state, self.device_state)

    self.assertEqual(self.device_state.data_shelf['k'].Get(), 'device')
    self.assertEqual(self.station_state.data_shelf['k'].Get(), 'station')
    self.assertEqual(
        self.device_state.data_shelf[state.KEY_DEVICE_DATA]['foo'].Get(),
        'station')
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

    self._SetDataShelf()
    self.device_state.update_test_state(path='', status='UNTESTED')
    self.device_state.update_test_state(path='a', status='FAILED')
    self.device_state.update_test_state(path='a.a', status='FAILED')
    self.device_state.update_test_state(path='a.b', status='FAILED')
    self.device_state.update_test_state(path='a.c', status='FAILED')
    self.device_state.update_test_state(path='b', status='PASSED')
    self.device_state.update_test_state(path='b.a', status='PASSED')
    self.device_state.update_test_state(path='b.b', status='PASSED')
    self.device_state.update_test_state(path='b.c', status='PASSED')

    self.station_state.update_test_state(path='', status='ACTIVE')
    self.station_state.update_test_state(path='a', status='ACTIVE')
    self.station_state.update_test_state(path='a.a', status='PASSED')
    self.station_state.update_test_state(path='a.b', status='ACTIVE')
    self.station_state.update_test_state(path='a.c', status='UNTESTED')

    self.test.args = type_utils.AttrDict(exclude_current_test_list=True,
                                         include_tests=False)
    self.test.path = 'a.b'
    self.test.test_info = mock.MagicMock()
    self.test.test_info.ReadTestList.return_value = station_test_list

    self.test.DoCopy(self.station_state, self.device_state)

    self.assertEqual(self.device_state.data_shelf['k'].Get(), 'device')
    self.assertEqual(self.station_state.data_shelf['k'].Get(), 'station')
    self.assertEqual(
        self.device_state.data_shelf[state.KEY_DEVICE_DATA]['foo'].Get(),
        'station')
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

  def testEmptyDeviceData(self):
    station_test_list = manager.BuildTestListForUnittest(
        {'tests': [
            {'id': 'a', 'subtests': [
                {'id': 'a', 'pytest_name': 'a'},
                {'id': 'b', 'pytest_name': 'b'},
                {'id': 'c', 'pytest_name': 'c'}, ]}, ]})
    self.test.args = type_utils.AttrDict(exclude_current_test_list=True,
                                         include_tests=False)
    self.test.path = 'a.b'
    self.test.test_info = mock.MagicMock()
    self.test.test_info.ReadTestList.return_value = station_test_list

    # Both source and destination doesn't have device data
    self.test.DoCopy(self.device_state, self.station_state)
    self.assertFalse(
        self.station_state.data_shelf_has_key(state.KEY_DEVICE_DATA))

    # recover
    self.station_state.PopLayer()

    # Source doesn't have device data, destination does.
    self.station_state.data_shelf_set_value(state.KEY_DEVICE_DATA, {'foo': 1})
    self.test.DoCopy(self.device_state, self.station_state)
    self.assertEqual(
        self.station_state.data_shelf[state.KEY_DEVICE_DATA]['foo'].Get(), 1)

    # recover
    self.station_state.PopLayer()

    # Source has device data, destination doesn't
    self.test.DoCopy(self.station_state, self.device_state)
    self.assertEqual(
        self.device_state.data_shelf[state.KEY_DEVICE_DATA]['foo'].Get(), 1)


class FactoryStateEnd2EndTest(FactoryStateUnittest):
  """Make sure copy & merge works with RPC server & DBM shelve."""

  def setUp(self):
    self.goofy_server = []
    self.goofy_server_thread = []
    self.state_instance = []
    self.root_dir = tempfile.mkdtemp()

    for i in xrange(2):
      server = goofy_server.GoofyServer(('127.0.0.1', 5000 + i))
      self.goofy_server.append(server)

      thread = threading.Thread(target=server.serve_forever,
                                name=('GoofyServer_%d' % i))
      thread.start()
      self.goofy_server_thread.append(thread)

      state_instance = state.FactoryState(
          state_file_dir=os.path.join(self.root_dir, str(i)))
      server.AddRPCInstance('/goofy', state_instance)
      self.state_instance.append(state_instance)

    self.device_state = state.get_instance('127.0.0.1', 5000)
    self.station_state = state.get_instance('127.0.0.1', 5001)
    self.test = factory_state.ManipulateFactoryStateLayer()

  def tearDown(self):
    try:
      if self.device_state.GetLayerCount() > 1:
        self.test.DoMerge(self.device_state, self.station_state)
      if self.station_state.GetLayerCount() > 1:
        self.test.DoMerge(self.station_state, self.device_state)
    finally:
      for i in xrange(2):
        net_utils.ShutdownTCPServer(self.goofy_server[i])
        self.goofy_server_thread[i].join()
        self.goofy_server[i].server_close()

      shutil.rmtree(self.root_dir)


if __name__ == '__main__':
  unittest.main()
