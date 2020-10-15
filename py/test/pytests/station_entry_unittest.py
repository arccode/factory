#!/usr/bin/env python3
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for station_entry factory test."""

import logging
import unittest
from unittest import mock

from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test.pytests import station_entry
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.unittest_utils import mock_time_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


class FakeArgs:
  def __init__(self, dargs):
    for key, value in dargs.items():
      self.__dict__[key] = value


_MOCK_TEST_STATES = 'mock_test_states'


class FactoryEntryUnitTest(unittest.TestCase):
  def setUp(self):
    self._patchers = []

    self._timeline = mock_time_utils.TimeLine()
    self._patchers.extend(mock_time_utils.MockAll(self._timeline))

    self.test = station_entry.StationEntry()
    self.test.ui_class = lambda event_loop: mock.Mock(spec=test_ui.StandardUI)

    self.mock_state = mock.Mock(spec=state.StubFactoryState)
    self.mock_state.PostHookEvent = mock.MagicMock()
    self.mock_remote_state = mock.Mock(spec=state.StubFactoryState)
    def _MockGetInstance(address=None, port=None):
      del port  # unused
      if address:
        return self.mock_remote_state
      return self.mock_state
    self._CreatePatcher(state, 'GetInstance').side_effect = _MockGetInstance
    self.mock_state.GetTestStates.return_value = _MOCK_TEST_STATES

    self.mock_dut = mock.Mock()
    self._CreatePatcher(device_utils,
                        'CreateDUTInterface').return_value = self.mock_dut

    self.mock_clear_serial = self._CreatePatcher(device_data,
                                                 'ClearAllSerialNumbers')

    self._polling_sleep_context = sync_utils.WithPollingSleepFunction(
        self._timeline.AdvanceTime)
    self._polling_sleep_context.__enter__()

  def tearDown(self):
    self._polling_sleep_context.__exit__(None, None, None)
    for patcher in self._patchers:
      patcher.stop()

  def _CreatePatcher(self, *args, **kwargs):
    patcher = mock.patch.object(*args, **kwargs)
    self._patchers.append(patcher)
    return patcher.start()

  def testLocalEndStationBasedTest(self):
    self._testEndStationBasedTest(is_local=True)

  def testNonLocalEndStationBasedTest(self):
    self._testEndStationBasedTest(is_local=False)

  def _testEndStationBasedTest(self, is_local):
    timeout_secs = 123
    self.test.args = FakeArgs({'start_station_tests': False,
                               'prompt_start': False,
                               'timeout_secs': timeout_secs,
                               'disconnect_dut': True,
                               'invalidate_dut_info': True,
                               'clear_serial_numbers': True,
                               'wait_goofy': True})

    self.mock_dut.link.IsLocal.return_value = is_local
    self.mock_dut.link.IsReady.side_effect = (
        lambda: self._timeline.GetTime() < 10)

    self.test.setUp()
    self.test.runTest()

    self.mock_dut.info.Invalidate.assert_called_once()
    self.mock_clear_serial.assert_called_once()
    self.mock_state.PostHookEvent.assert_called_once_with(
        'TestResult', _MOCK_TEST_STATES)

    if not is_local:
      self.assertFalse(self.mock_dut.link.IsReady())
      self._timeline.AssertTimeAt(10)

  def testStartStationBasedTest(self):
    timeout_secs = 123
    self.test.args = FakeArgs({'start_station_tests': True,
                               'prompt_start': False,
                               'load_dut_storage': True,
                               'timeout_secs': timeout_secs,
                               'invalidate_dut_info': True,
                               'clear_serial_numbers': True,
                               'wait_goofy': True})

    self.mock_dut.link.IsReady.side_effect = (
        lambda: self._timeline.GetTime() >= 10)

    self.test.setUp()
    self.test.runTest()

    self.mock_dut.info.Invalidate.assert_called_once()
    self.mock_clear_serial.assert_called_once()
    self.assertEqual(self.mock_dut.info.GetSerialNumber.call_args_list,
                     [(('serial_number',),), (('mlb_serial_number',),)])
    self.mock_state.PostHookEvent.assert_not_called()
    self.mock_remote_state.DataShelfHasKey.assert_called_once()

    self.assertTrue(self.mock_dut.link.IsReady())
    self._timeline.AssertTimeAt(10)

  def testStartStationBasedTestTimeout(self):
    timeout_secs = 123
    self.test.args = FakeArgs({'start_station_tests': True,
                               'prompt_start': False,
                               'load_dut_storage': True,
                               'timeout_secs': timeout_secs,
                               'invalidate_dut_info': True,
                               'clear_serial_numbers': True, })

    self.mock_dut.link.IsReady.return_value = False

    self.test.setUp()
    self.assertRaisesRegex(type_utils.TestFailure, 'DUT is not connected',
                           self.test.runTest)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
