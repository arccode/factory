#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# We need to inject mock objects to protected members of FactoryEntry:
# pylint: disable=protected-access

"""Unit tests for station_entry factory test."""

import logging
import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.device import types
from cros.factory.goofy.goofy_rpc import GoofyRPC
from cros.factory.test import device_data
from cros.factory.test.pytests import station_entry
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.utils import sync_utils


class FakeArgs(object):
  def __init__(self, dargs):
    for (key, value) in dargs.iteritems():
      self.__dict__[key] = value


_MOX_HTML_TYPE = mox.Or(mox.IsA(list), mox.IsA(basestring), mox.IsA(dict))


class FactoryEntryUnitTest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()
    self.test = station_entry.StationEntry()

    self.mock_ui = self.mox.CreateMock(test_ui.StandardUI)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testSetUpForStartTesting(self):
    mock_state = self.mox.CreateMock(GoofyRPC)

    self.mox.StubOutWithMock(state, 'get_instance')

    # for start testing
    state.get_instance().AndReturn(mock_state)
    self.mock_ui.AppendCSS(mox.IsA(str))
    self.mock_ui.SetTitle(_MOX_HTML_TYPE)

    self.mox.ReplayAll()

    self.test.args = FakeArgs({'start_station_tests': True,
                               'prompt_start': False,
                               'timeout_secs': None,
                               'invalidate_dut_info': True,
                               'clear_serial_numbers': True, })
    self.test.ui = self.mock_ui
    self.test.setUp()
    self.assertEqual(self.test._state, mock_state)

    self.mox.VerifyAll()

  def testLocalEndStationBasedTest(self):
    self._testEndStationBasedTest(is_local=True)

  def testNonLocalEndStationBasedTest(self):
    self._testEndStationBasedTest(is_local=False)

  def _testEndStationBasedTest(self, is_local):
    mock_dut_link = self.mox.CreateMock(types.DeviceLink)
    self.test._dut = device_utils.CreateDUTInterface()
    self.test._dut.link = mock_dut_link
    mock_state = self.mox.CreateMock(GoofyRPC)
    self.test._state = mock_state
    timeout_secs = 123
    self.test.args = FakeArgs({'start_station_tests': False,
                               'prompt_start': False,
                               'timeout_secs': timeout_secs,
                               'disconnect_dut': True,
                               'invalidate_dut_info': True,
                               'clear_serial_numbers': True, })
    self.test.ui = self.mock_ui

    self.mox.StubOutWithMock(device_data, 'ClearAllSerialNumbers')
    self.mox.StubOutWithMock(sync_utils, 'WaitFor')
    self.mox.StubOutWithMock(self.test, 'SendTestResult')

    device_data.ClearAllSerialNumbers()
    self.mock_ui.SetState(_MOX_HTML_TYPE).MultipleTimes()

    mock_dut_link.IsLocal().AndReturn(is_local)
    if not is_local:
      sync_utils.WaitFor(mox.IsA(type(lambda: None)), timeout_secs,
                         poll_interval=1)

    self.test.SendTestResult()

    self.mox.ReplayAll()

    self.test.runTest()

    self.mox.VerifyAll()

  def testStartStationBasedTest(self):
    mock_dut_link = self.mox.CreateMock(types.DeviceLink)
    self.test._dut = device_utils.CreateDUTInterface()
    self.test._dut.link = mock_dut_link
    self.test.ui = self.mock_ui
    timeout_secs = 123
    self.test.args = FakeArgs({'start_station_tests': True,
                               'prompt_start': False,
                               'load_dut_storage': True,
                               'timeout_secs': timeout_secs,
                               'invalidate_dut_info': True,
                               'clear_serial_numbers': True, })

    self.mox.StubOutWithMock(device_data, 'ClearAllSerialNumbers')
    self.mox.StubOutWithMock(self.test._dut.info, 'GetSerialNumber')
    self.mox.StubOutWithMock(sync_utils, 'WaitFor')

    device_data.ClearAllSerialNumbers()
    self.test._dut.info.GetSerialNumber('serial_number')
    self.test._dut.info.GetSerialNumber('mlb_serial_number')
    self.mock_ui.SetState(_MOX_HTML_TYPE).MultipleTimes()
    sync_utils.WaitFor(mox.IsA(type(lambda: None)), timeout_secs,
                       poll_interval=1)

    self.mox.ReplayAll()

    self.test.runTest()

    self.mox.VerifyAll()


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
