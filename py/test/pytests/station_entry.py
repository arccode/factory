# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Starts or ends a station-based test.

Description
-----------
This pytest initializes (or terminates) the DUT connection in a
station-based test, and validates (or invalidates) related device
info. This pytest is mainly used as the first and last pytest to
wrap around a sequence of station-based tests.

In more detail, if the argument `start_station_tests` is set to True,
this pytest performs following initialization steps:
1. Clear DUT info.
2. Clear serial numbers from device data.
3. Wait for DUT being connected.

On the other hand, if the argument `start_station_tests` is set to
False, this pytest performs following cleanup steps:
1. Wait for DUT being disconnected.
2. Clear DUT info.
3. Clear serial numbers from device data.

Test Procedure
--------------
If argument `start_station_tests` is set to True, it waits until the
DUT is connected.

Otherwise, if argument `start_station_tests` is set to False, it waits
until the DUT is disconnected.

Dependency
----------
Depend on Device API (``cros.factory.device.device_utils``) to create
a DUT interface, and monitor if DUT is connected.

Examples
--------
To start a sequence of station-based tests, this pytest can be used as
the first pytest, add this in test list::

  {
    "pytest_name": "station_entry"
  }

If the following pytests should be started until spacebar is hit::

  {
    "pytest_name": "station_entry",
    "args": {
      "prompt_start": true
    }
  }

To gracefully terminate a sequence of station-based tests::

  {
    "pytest_name": "station_entry",
    "args": {
      "start_station_tests": false
    }
  }

Please refer to station_based.test_list.json and STATION_BASED.md about how to
do station based testing.
"""

from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test import session
from cros.factory.test.i18n import _
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


class StationEntry(test_case.TestCase):
  """The factory test to start station test process."""
  ARGS = [
      Arg('start_station_tests', bool,
          'To start or stop the factory station tests.',
          default=True),
      Arg('prompt_start', bool,
          'Prompt for spacebar before starting test.',
          default=False),
      Arg('timeout_secs', int,
          'Timeout for waiting the device. Set to None for waiting forever.',
          default=None),
      Arg('disconnect_dut', bool,
          'Ask operator to disconnect DUT or not',
          default=True),
      # TODO(hungte) When device_data and dut_storage has been synced, we should
      # change this to "clear_dut_storage" since testlog will still try to
      # reload device data from storage before invocation of next test.
      Arg('load_dut_storage', bool,
          'To load DUT storage into station session (DeviceData).',
          default=True),
      Arg('invalidate_dut_info', bool,
          'To invoke dut.info.Invalidate() or not',
          default=True),
      Arg('clear_serial_numbers', bool,
          'To invoke device_data.ClearAllSerialNumbers() or not',
          default=True),
      Arg('wait_goofy', bool, 'wait until we can connect to goofy',
          default=True),
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self._state = state.GetInstance()
    self.ui.ToggleTemplateClass('font-large', True)
    self.ui.SetTitle(
        _('Start Station Test')
        if self.args.start_station_tests else _('End Station Test'))

  def SendTestResult(self):
    self._state.PostHookEvent('TestResult', self._state.GetTestStates())

  def runTest(self):
    if self.args.start_station_tests:
      # Clear dut.info data.
      if self.args.invalidate_dut_info:
        session.console.info('Clearing dut.info data...')
        self._dut.info.Invalidate()
      if self.args.clear_serial_numbers:
        session.console.info('Clearing serial numbers')
        device_data.ClearAllSerialNumbers()
      self.Start()
      if self.args.load_dut_storage:
        self._dut.info.GetSerialNumber('serial_number')
        self._dut.info.GetSerialNumber('mlb_serial_number')
    else:
      self.End()
      # Clear dut.info data.
      if self.args.invalidate_dut_info:
        session.console.info('Clearing dut.info data...')
        self._dut.info.Invalidate()
      if self.args.clear_serial_numbers:
        session.console.info('Clearing serial numbers')
        device_data.ClearAllSerialNumbers()

  def Start(self):
    self.ui.SetState(_('Please attach DUT.'))

    def _IsReady():
      if not self._dut.link.IsReady():
        return False
      try:
        self._dut.CheckCall(['true'])
        return True
      except Exception:
        return False

    try:
      sync_utils.WaitFor(_IsReady, self.args.timeout_secs, poll_interval=1)
    except type_utils.TimeoutError:
      self.FailTask(
          'DUT is not connected in %d seconds' % self.args.timeout_secs)

    if self.args.wait_goofy:
      def _TryCreateStateProxy():
        try:
          state_proxy = state.GetInstance(self._dut.link.host)
          state_proxy.DataShelfHasKey('test_list_options')
          return True
        except Exception:
          session.console.exception('Cannot create state proxy')
          return False

      try:
        sync_utils.WaitFor(_TryCreateStateProxy,
                           self.args.timeout_secs,
                           poll_interval=1)
      except type_utils.TimeoutError:
        self.FailTask(
            'DUT Goofy is not connected in %d seconds' % self.args.timeout_secs)

    if self.args.prompt_start:
      self.ui.SetState(_('Press SPACE to start the test.'))
      self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

  def End(self):
    self.ui.SetState(_('Sending test results to shopfloor...'))

    self.SendTestResult()

    self.ui.SetState(_('Please remove DUT.'))
    if not self._dut.link.IsLocal():
      if self.args.disconnect_dut:
        sync_utils.WaitFor(lambda: not self._dut.link.IsReady(),
                           self.args.timeout_secs,
                           poll_interval=1)
      else:
        self.ui.SetState(_('Press SPACE to end the test.'))
        self.ui.WaitKeysOnce(test_ui.SPACE_KEY)
