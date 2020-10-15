# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test USB type-C port charging function with Plankton-Raiden board.

Description
-----------
This test can be tested locally or in remote ADB connection manner.

Use Plankton-Raiden board control to verify device battery current. It supports
charge-5V, charge-12V, charge-20V, and discharge. This test also takes INA
current and voltage value on Plankton-Raiden board into account as a judgement.

Sometimes the charge current may not be stable, we have to wait for several
seconds until the current stable then sampling the current value.

Test Procedure
--------------
This is an automated test without user interaction, but the environment must
be setup first:

1. Connect the testing USB type-C port to Plankton-Raiden board.
2. Connect the Plankton-Raiden serial commanding port to Plankton-Raiden board.
3. Specify the type of the `bft_fixutre` connecting to.
4. Specify the charging/discharing voltage/current and its minimun/maximun
   threshold.
5. Start the test.

Dependency
----------
- Connections to Plankton-Raiden board must setup before starting.

Examples
--------
To test 5V charge, add this in test list::

  {
    "pytest_name": "plankton_usb_c_charge",
    "args": {
      "bft_fixture": {
        "class_name":
          "cros.factory.test.fixture.dummy_bft_fixture.DummyBFTFixture",
        "params": {}
      },
      "min_charge_5V_current_mA": 0
    }
  }

Test 20V charge without checking the input current::

  {
    "pytest_name": "plankton_usb_c_charge",
    "args": {
      "bft_fixture": {
        "class_name":
          "cros.factory.test.fixture.dummy_bft_fixture.DummyBFTFixture",
        "params": {}
      },
      "min_charge_20V_current_mA": 0,
      "check_ina_current": false
    }
  }

"""

import logging

from cros.factory.device import device_utils
from cros.factory.device.links import adb
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test.utils import stress_manager
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils
from cros.factory.utils import time_utils
from cros.factory.utils import type_utils


class PlanktonChargeBFTTest(test_case.TestCase):
  """Tests usb_c port charge functionality."""
  ARGS = [
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP),
      Arg('charge_duration_secs', (int, float),
          'The duration in seconds to charge the battery', default=5),
      Arg('discharge_duration_secs', (int, float),
          'The duration in seconds to discharge the battery', default=5),
      Arg('wait_after_engage_secs', (int, float),
          'The duration in seconds to wait after engage / disengage '
          'charge device', default=0),
      Arg('min_charge_5V_current_mA', (int, float),
          'The minimum charge current in mA that the battery '
          'needs to reach during charge-5V test, if is None, '
          'it would not check on this voltage level', default=None),
      Arg('min_charge_12V_current_mA', (int, float),
          'The minimum charge current in mA that the battery '
          'needs to reach during charge-12V test, if is None, '
          'it would not check on this voltage level', default=None),
      Arg('min_charge_20V_current_mA', (int, float),
          'The minimum charge current in mA that the battery '
          'needs to reach during charge-20V test, if is None, '
          'it would not check on this voltage level', default=None),
      Arg('min_discharge_current_mA', (int, float),
          'The minimum discharge current in mA that the battery '
          'needs to reach during discharging test, if is None, '
          'it would not check on this voltage level', default=None),
      Arg('current_sampling_period_secs', (int, float),
          'The period in seconds to sample '
          'charge/discharge current during test',
          default=0.5),
      Arg('check_battery_cycle', bool,
          'Whether to check battery cycle count is lower than threshold',
          default=False),
      Arg('battery_cycle_threshold', int,
          'The threshold for battery cycle count',
          default=0),
      Arg('check_protect_ina_current', bool,
          'If set True, it would check if Plankton 5V INA current is within '
          'protect_ina_current_range first for high-V protection',
          default=True),
      Arg('protect_ina_current_range', list,
          'A list for indicating reasonable current in mA of charge-5V from '
          'Plankton INA for high-V protection',
          default=[2000, 3400]),
      Arg('protect_ina_retry_times', int,
          'Retry times for checking 5V INA current for high-V protection, '
          'interval with 1 second',
          default=5),
      Arg('check_ina_current', bool,
          'If set True, it would check Plankton INA current during testing '
          'whether within ina_current_charge_range for charging, or '
          'ina_current_discharge_range for discharge',
          default=True),
      Arg('ina_current_charge_range', list,
          'A list for indicating reasonable current in mA during charging '
          'from Plankton INA',
          default=[2000, 3400]),
      Arg('ina_current_discharge_range', list,
          'A list for indicating reasonable current in mA during discharging '
          'from Plankton INA',
          default=[-3500, 0]),
      Arg('ina_voltage_tolerance', float,
          'Tolerance ratio for Plankton INA voltage compared to expected '
          'charging voltage',
          default=0.12),
      Arg('monitor_plankton_voltage_only', bool,
          'If set True, it would only check Plankton INA voltage whether as '
          'expected (not check DUT side)',
          default=False)
  ]

  _SUPPORT_CHARGE_VOLT = [5, 12, 20]  # supported charging voltage
  _DISCHARGE_VOLT = 5  # discharging voltage

  def setUp(self):
    self.ui.ToggleTemplateClass('font-large', True)
    self._dut = device_utils.CreateDUTInterface()
    self._power = self._dut.power
    self.VerifyArgs()
    self._bft_fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)
    self._adb_remote_test = isinstance(self._dut.link, adb.ADBLink)
    self._remote_test = not self._dut.link.IsLocal()
    if self._adb_remote_test:
      self.ui.SetState(_('Waiting for ADB device connection...'))
      self._bft_fixture.SetDeviceEngaged('ADB_HOST', engage=True)

  def tearDown(self):
    if self._adb_remote_test:
      # Set back the state of ADB-connected before leaving test. It can make
      # sequential tests smoother by reducing ADB connection wait time.
      self._bft_fixture.SetDeviceEngaged('ADB_HOST', engage=True)
    self._bft_fixture.Disconnect()

  def VerifyArgs(self):
    """Verifies arguments feasibility.

    Raises:
      TestFailure: If arguments are not reasonable.
    """
    if (self.args.check_protect_ina_current and
        (self.args.protect_ina_current_range[0] >
         self.args.protect_ina_current_range[1])):
      raise type_utils.TestFailure(
          'protect_ina_current_range range is invalid')
    if (self.args.check_ina_current and
        (self.args.ina_current_charge_range[0] >
         self.args.ina_current_charge_range[1])):
      raise type_utils.TestFailure(
          'ina_current_charge_range range is invalid')
    if (self.args.check_ina_current and
        (self.args.ina_current_discharge_range[0] >
         self.args.ina_current_discharge_range[1])):
      raise type_utils.TestFailure(
          'ina_current_discharge_range range is invalid')
    if (self.args.min_charge_5V_current_mA is not None and
        self.args.min_charge_5V_current_mA < 0):
      raise type_utils.TestFailure(
          'min_charge_5V_current_mA must not be less than zero')
    if (self.args.min_charge_12V_current_mA is not None and
        self.args.min_charge_12V_current_mA < 0):
      raise type_utils.TestFailure(
          'min_charge_12V_current_mA must not be less than zero')
    if (self.args.min_charge_20V_current_mA is not None and
        self.args.min_charge_20V_current_mA < 0):
      raise type_utils.TestFailure(
          'min_charge_20V_current_mA must not be less than zero')
    if (self.args.min_discharge_current_mA is not None and
        not self.args.min_discharge_current_mA < 0):
      raise type_utils.TestFailure(
          'min_discharge_current_mA must be less than zero')

  def SampleCurrentAndVoltage(self, duration_secs, charging):
    """Samples battery current and Plankton INA current/voltage for duration.

    Args:
      duration_secs: The duration in seconds to sample current.
      charging: True if testing charging; False if discharging.

    Returns:
      A tuple of three lists (sampled battery current, sampled INA current,
      sampled INA voltage).
    """
    sampled_battery_current = []
    sampled_ina_current = []
    sampled_ina_voltage = []
    end_time = time_utils.MonotonicTime() + duration_secs
    while time_utils.MonotonicTime() < end_time:
      # Skip sampling remote target current while discharging since we might
      # loss connection during that time.
      if not (self._remote_test and not charging):
        sampled_battery_current.append(self._power.GetBatteryCurrent())
      ina_values = self._bft_fixture.ReadINAValues()
      sampled_ina_current.append(ina_values['current'])
      sampled_ina_voltage.append(ina_values['voltage'])
      self.Sleep(self.args.current_sampling_period_secs)

    if not (self._remote_test and not charging):
      logging.info('Sampled battery current: %s', str(sampled_battery_current))
    logging.info('Sampled ina current: %s', str(sampled_ina_current))
    logging.info('Sampled ina voltage: %s', str(sampled_ina_voltage))
    return (sampled_battery_current, sampled_ina_current, sampled_ina_voltage)

  def MonitorINAVoltage(self, timeout_secs, testing_volt):
    """Polls Plankton INA voltage until it reaches the expected voltage.

    Args:
      timeout_secs: The duration of polling interval in seconds.
      testing_volt: The testing voltage in V.

    Returns:
      True if voltage meets as expected during polling cycle; otherwise False.
    """
    tolerance = testing_volt * 1000 * self.args.ina_voltage_tolerance
    def _PollINAVoltage():
      ina_voltage = self._bft_fixture.ReadINAValues()['voltage']
      logging.info('Monitored ina voltage: %d', ina_voltage)
      return abs(ina_voltage - testing_volt * 1000.0) <= tolerance

    try:
      sync_utils.WaitFor(_PollINAVoltage, timeout_secs,
                         self.args.current_sampling_period_secs)
      return True
    except type_utils.TimeoutError:
      ina_voltage = self._bft_fixture.ReadINAValues()['voltage']
      session.console.error('Expected voltage: %d mV, got: %d mV',
                            testing_volt * 1000, ina_voltage)
      return False

  def Check5VINACurrent(self):
    """Checks if Plankton INA is within range for charge-5V.

    If charge-5V current is within range, returns immediately. Otherwise, retry
    args.protect_ina_retry_times before failing the test.
    """
    if not self.args.check_protect_ina_current:
      return
    current_min, current_max = self.args.protect_ina_current_range

    self.ui.SetState(_('Checking Plankton INA current for protection...'))
    self._bft_fixture.SetDeviceEngaged('CHARGE_5V', engage=True)
    self.Sleep(self.args.wait_after_engage_secs)

    ina_current = 0
    retry = self.args.protect_ina_retry_times
    while retry > 0:
      self.Sleep(1)  # Wait for INA stable
      ina_current = self._bft_fixture.ReadINAValues()['current']
      logging.info('Current of plankton INA = %d mA', ina_current)
      if current_min <= ina_current <= current_max:
        break
      retry -= 1

    if retry <= 0:
      self.fail('Plankton INA current %d mA out of range [%d, %d] '
                'after %d retry.' %
                (ina_current, current_min, current_max,
                 self.args.protect_ina_retry_times))

  def TestCharging(self, current_min_threshold, testing_volt):
    """Tests charge scenario. It will monitor within args.charge_duration_secs.

    Args:
      current_min_threshold: Minimum threshold to check charging current. If
          None, skip the test.
      testing_volt: An integer to specify testing charge voltage.

    Raises:
      TestFailure: If the sampled battery charge current does not pass
          the given threshold in dargs.
    """
    if current_min_threshold is None:
      return

    if testing_volt not in self._SUPPORT_CHARGE_VOLT:
      raise type_utils.TestFailure(
          'Specified test voltage %d is not in supported list: %r' %
          (testing_volt, self._SUPPORT_CHARGE_VOLT))

    command_device = 'CHARGE_%dV' % testing_volt
    logging.info('Testing %s...', command_device)

    self.ui.SetState(
        _('Testing battery {voltage}V charging...', voltage=testing_volt))

    # Plankton-Raiden board setting: engage
    self._bft_fixture.SetDeviceEngaged(command_device, engage=True)
    self.Sleep(self.args.wait_after_engage_secs)

    if self.args.monitor_plankton_voltage_only:
      if not self.MonitorINAVoltage(self.args.charge_duration_secs,
                                    testing_volt):
        raise type_utils.TestFailure(
            'INA voltage did not meet the expected one.')
      return

    (sampled_battery_current, sampled_ina_current, sampled_ina_voltage) = (
        self.SampleCurrentAndVoltage(self.args.charge_duration_secs,
                                     charging=True))
    # Fail if all battery current samples are below threshold.
    if not any(c > current_min_threshold for c in sampled_battery_current):
      raise type_utils.TestFailure(
          'Battery charge current did not reach defined threshold %f mA' %
          current_min_threshold)
    # Fail if all Plankton INA voltage samples are not within specified range.
    self.CheckINASampleVoltage(sampled_ina_voltage, testing_volt, charging=True)
    # If args.check_ina_current, fail if average of Plankton INA current
    # samples is not within specified range.
    self.CheckINASampleCurrent(sampled_ina_current, charging=True)

  def TestDischarging(self):
    """Tests discharging within args.discharge_duration_secs.

    For local test scenario, the test runs under high system load to maximize
    battery discharge current.

    For adb remote test, it only measures Plankton INA voltage and current since
    we lose adb connection during device discharging.

    Raises:
      TestFailure: If the sampled battery discharge current does not pass
          the given threshold in dargs.
    """
    current_min_threshold = self.args.min_discharge_current_mA
    if current_min_threshold is None:
      return

    logging.info('Testing discharge...')
    self.ui.SetState(_('Testing battery discharging...'))
    self._bft_fixture.SetDeviceEngaged('CHARGE_5V', engage=False)
    self.Sleep(self.args.wait_after_engage_secs)

    if self.args.monitor_plankton_voltage_only:
      if not self.MonitorINAVoltage(self.args.charge_duration_secs, 5):
        raise type_utils.TestFailure(
            'INA voltage did not meet the expected one.')
      return

    if self._remote_test:
      (unused_sampled_battery_current, sampled_ina_current,
       sampled_ina_voltage) = (self.SampleCurrentAndVoltage(
           self.args.discharge_duration_secs, charging=False))
    else:
      # Discharge under high system load.
      with stress_manager.StressManager(self._dut).Run(
          self.args.discharge_duration_secs):
        (sampled_battery_current, sampled_ina_current, sampled_ina_voltage) = (
            self.SampleCurrentAndVoltage(
                self.args.discharge_duration_secs, charging=False))
      # Fail if all samples are over threshold.
      if not any(c < current_min_threshold for c in sampled_battery_current):
        raise type_utils.TestFailure(
            'Battery discharge current did not reach defined threshold %f mA' %
            current_min_threshold)

    # Fail if all Plankton INA voltage samples are not within specified range.
    self.CheckINASampleVoltage(
        sampled_ina_voltage, self._DISCHARGE_VOLT, charging=False)
    # If args.check_ina_current, fail if average of Plankton INA current
    # samples is not within specified range.
    self.CheckINASampleCurrent(sampled_ina_current, charging=False)

  def CheckINASampleVoltage(self, ina_sample, testing_volt, charging):
    """Checks if average INA voltage is within range on Plankton.

    Args:
      ina_sample: A list of sampled Plankton INA voltage.
      testing_volt: Expected testing voltage in V.
      charging: True if testing charging; False if discharging.

    Raises:
      TestFailure if samples are not within range.
    """
    tolerance = testing_volt * 1000 * self.args.ina_voltage_tolerance
    # Fail if error ratios of all voltage samples are higher than tolerance
    if not any(abs(v - testing_volt * 1000.0) <= tolerance for v in ina_sample):
      raise type_utils.TestFailure(
          'Plankton INA voltage did not meet expected %s %dV, sampled voltage '
          '= %s' % ('charge' if charging else 'discharge',
                    testing_volt, str(ina_sample)))

  def CheckINASampleCurrent(self, ina_sample, charging):
    """Checks if average INA current is within range on Plankton.

    Args:
      ina_sample: A list of sampled Plankton INA current.
      charging: True if testing charging; False if discharging.

    Raises:
      TestFailure if samples are not within range.
    """
    if not self.args.check_ina_current:
      return
    if charging:
      ina_min, ina_max = self.args.ina_current_charge_range
    else:
      ina_min, ina_max = self.args.ina_current_discharge_range
    # Fail if average is not within range.
    # Neglect first 2 samples since they may on current up-lifting stage.
    ina_sample = ina_sample if len(ina_sample) < 2 else ina_sample[2:]
    average = sum(ina_sample) / len(ina_sample)
    logging.info('Average Plankton INA current = %d mA', average)
    if not ina_min < average < ina_max:
      raise type_utils.TestFailure(
          'Plankton INA %s current average %d mA did not within %d - %d' %
          ('charge' if charging else 'discharge', average, ina_min, ina_max))

  def runTest(self):
    """Runs charge test.

    Raises:
      TestFailure: Battery attribute error.
    """
    if not self._power.CheckBatteryPresent():
      raise type_utils.TestFailure(
          'Cannot detect battery. Missing battery?')
    if (self.args.check_battery_cycle and
        self._power.GetBatteryCycleCount() > self.args.battery_cycle_threshold):
      raise type_utils.TestFailure('Battery cycle count is higher than %d' %
                                   self.args.battery_cycle_threshold)

    if self._remote_test:
      # Get remote target battery capacity and warn if almost full
      capacity = self._power.GetChargePct()
      session.console.info('Current battery capacity = %d %%', capacity)
      if capacity > 95:
        session.console.warning('Current battery capacity is almost full. '
                                'It may cause charge failure!!')
    else:
      # Set charge state to 'charge'
      self._power.SetChargeState(self._power.ChargeState.CHARGE)
      logging.info('Set charge state: CHARGE')

    self.Check5VINACurrent()
    self.TestCharging(self.args.min_charge_5V_current_mA, testing_volt=5)
    self.TestCharging(self.args.min_charge_12V_current_mA, testing_volt=12)
    self.TestCharging(self.args.min_charge_20V_current_mA, testing_volt=20)
    self.TestDischarging()
