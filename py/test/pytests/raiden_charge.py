# -*- coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test Raiden USB type-C port charging function.

A simple battery test that with Plankton-Raiden control, we verify charge-5V,
charge-12V, charge-20V, and discharge. This test also takes INA current value on
Plankton Raiden board as a judgement.
"""

import logging
import time
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory import system
from cros.factory.system.board import Board
from cros.factory.system import power
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.args import Arg
from cros.factory.test.fixture import bft_fixture
from cros.factory.utils import time_utils

_TEST_TITLE = test_ui.MakeLabel('Raiden Charging Test', u'Raiden 充电测试')
_TESTING_CHARGE = lambda v: test_ui.MakeLabel(
    'Testing battery %dV charging...' % v,
    u'测试电池 %dV 充电中...' % v)
_TESTING_DISCHARGE = test_ui.MakeLabel('Testing battery discharging...',
                                       u'测试电池放电中...')
_CSS = 'body { font-size: 2em; }'


class RaidenChargeBFTTest(unittest.TestCase):
  """Tests raiden port charge functionality."""
  ARGS = [
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP),
      Arg('raiden_index', int, 'Index of DUT raiden port'),
      Arg('charge_duration_secs', (int, float),
          'The duration in seconds to charge the battery', default=5),
      Arg('discharge_duration_secs', (int, float),
          'The duration in seconds to discharge the battery', default=5),
      Arg('min_charge_5V_current_mA', (int, float),
          'The minimum charge current in mA that the battery '
          'needs to reach during charge-5V test, if is None, '
          'it would not check on this voltage level', optional=True),
      Arg('min_charge_12V_current_mA', (int, float),
          'The minimum charge current in mA that the battery '
          'needs to reach during charge-12V test, if is None, '
          'it would not check on this voltage level', optional=True),
      Arg('min_charge_20V_current_mA', (int, float),
          'The minimum charge current in mA that the battery '
          'needs to reach during charge-20V test, if is None, '
          'it would not check on this voltage level', optional=True),
      Arg('min_discharge_current_mA', (int, float),
          'The minimum discharge current in mA that the battery '
          'needs to reach during discharging test, if is None, '
          'it would not check on this voltage level', optional=True),
      Arg('current_sampling_period_secs', (int, float),
          'The period in seconds to sample '
          'charge/discharge current during test',
          default=0.5),
      Arg('check_battery_cycle', bool,
          'Whether to check battery cycle count equals to zero',
          default=False),
      Arg('check_protect_ina_current', bool,
          'If set True, it would check if Plankton 5V INA current is within '
          'protect_ina_current_range first for high-V protection',
          default=True),
      Arg('protect_ina_current_range', tuple,
          'A tuple for indicating reasonable current in mA of charge-5V from '
          'Plankton INA for high-V protection',
          default=(2000, 3400)),
      Arg('protect_ina_retry_times', int,
          'Retry times for checking 5V INA current for high-V protection, '
          'interval with 1 second',
          default=5),
      Arg('check_ina_current', bool,
          'If set True, it would check Plankton INA current during testing '
          'whether within ina_current_charge_range for charging, or '
          'ina_current_discharge_range for discharge',
          default=True),
      Arg('ina_current_charge_range', tuple,
          'A tuple for indicating reasonable current in mA during charging '
          'from Plankton INA',
          default=(2000, 3400)),
      Arg('ina_current_discharge_range', tuple,
          'A tuple for indicating reasonable current in mA during discharging '
          'from Plankton INA',
          default=(-3500, 0)),
      Arg('ina_voltage_tolerance', float,
          'Tolerance ratio for Plankton INA voltage compared to expected '
          'charging voltage',
          default=0.12)
  ]

  # Supported charging voltage
  _SUPPORT_CHARGE_VOLT = [5, 12, 20]

  def setUp(self):
    self.VerifyArgs()
    self._ui = test_ui.UI(css=_CSS)
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._board = system.GetBoard()
    self._power = power.Power()
    self._bft_fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)

  def tearDown(self):
    self._bft_fixture.Disconnect()

  def VerifyArgs(self):
    """Verifies arguments feasibility.

    Raises:
      FactoryTestFailure: If arguments are not reasonable.
    """
    if (self.args.check_protect_ina_current and
        (self.args.protect_ina_current_range[0] >
         self.args.protect_ina_current_range[1])):
      raise factory.FactoryTestFailure(
          'protect_ina_current_range range is invalid')
    if (self.args.check_ina_current and
        (self.args.ina_current_charge_range[0] >
         self.args.ina_current_charge_range[1])):
      raise factory.FactoryTestFailure(
          'ina_current_charge_range range is invalid')
    if (self.args.check_ina_current and
        (self.args.ina_current_discharge_range[0] >
         self.args.ina_current_discharge_range[1])):
      raise factory.FactoryTestFailure(
          'ina_current_discharge_range range is invalid')
    if (self.args.min_charge_5V_current_mA is not None and
        self.args.min_charge_5V_current_mA < 0):
      raise factory.FactoryTestFailure(
          'min_charge_5V_current_mA must not be less than zero')
    if (self.args.min_charge_12V_current_mA is not None and
        self.args.min_charge_12V_current_mA < 0):
      raise factory.FactoryTestFailure(
          'min_charge_12V_current_mA must not be less than zero')
    if (self.args.min_charge_20V_current_mA is not None and
        self.args.min_charge_20V_current_mA < 0):
      raise factory.FactoryTestFailure(
          'min_charge_20V_current_mA must not be less than zero')
    if (self.args.min_discharge_current_mA is not None and
        not self.args.min_discharge_current_mA < 0):
      raise factory.FactoryTestFailure(
          'min_discharge_current_mA must be less than zero')

  def SampleCurrentAndVoltage(self, duration_secs):
    """Samples battery current and Plankton INA current/voltage for duration.

    Args:
      duration_secs: The duration in seconds to sample current.

    Returns:
      A tuple of three lists (sampled battery current, sampled INA current,
      sampled INA voltage).
    """
    sampled_battery_current = []
    sampled_ina_current = []
    sampled_ina_voltage = []
    end_time = time_utils.MonotonicTime() + duration_secs
    while time_utils.MonotonicTime() < end_time:
      sampled_battery_current.append(self._board.GetBatteryCurrent())
      ina_values = self._bft_fixture.ReadINAValues()
      sampled_ina_current.append(ina_values['current'])
      sampled_ina_voltage.append(ina_values['voltage'])
      time.sleep(self.args.current_sampling_period_secs)

    logging.info('Sampled battery current: %s', str(sampled_battery_current))
    logging.info('Sampled ina current: %s', str(sampled_ina_current))
    logging.info('Sampled ina voltage: %s', str(sampled_ina_voltage))
    return (sampled_battery_current, sampled_ina_current, sampled_ina_voltage)

  def Check5VINACurrent(self):
    """Checks if Plankton INA is within range for charge-5V.

    If charge-5V current is within range, returns immediately. Otherwise, retry
    args.protect_ina_retry_times before failing the test.
    """
    if not self.args.check_protect_ina_current:
      return
    current_min = self.args.protect_ina_current_range[0]
    current_max = self.args.protect_ina_current_range[1]

    self._bft_fixture.SetDeviceEngaged('CHARGE_5V', engage=True)

    ina_current = 0
    retry = self.args.protect_ina_retry_times
    while retry > 0:
      time.sleep(1)  # Wait for INA stable
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

  def TestCharging(self, current_min_threshold, voltage_tolerance,
                   testing_volt):
    """Tests charge scenario. It will monitor within args.charge_duration_secs.

    Args:
      current_min_threshold: Minimum threshold to check charging current. If
          None, skip the test.
      voltage_tolerance: Error ratio threshold to check charging voltage.
      testing_volt: An integer to specify testing charge voltage.

    Raises:
      FactoryTestFailure: If the sampled battery charge current does not pass
          the given threshold in dargs.
    """

    if current_min_threshold is None:
      return

    if testing_volt not in self._SUPPORT_CHARGE_VOLT:
      raise factory.FactoryTestFailure(
          'Specified test voltage %d is not in supported list: %r' %
          (testing_volt, self._SUPPORT_CHARGE_VOLT))

    command_device = 'CHARGE_%dV' % testing_volt
    logging.info('Testing %s...', command_device)

    self._template.SetState(_TESTING_CHARGE(testing_volt))
    # Plankton-Raiden board setting: engage
    self._bft_fixture.SetDeviceEngaged(command_device, engage=True)

    (sampled_battery_current, sampled_ina_current, sampled_ina_voltage) = (
        self.SampleCurrentAndVoltage(self.args.charge_duration_secs))
    # Fail if all battery current samples are below threshold
    if not any(
        c > current_min_threshold for c in sampled_battery_current):
      raise factory.FactoryTestFailure(
          'Battery charge current did not reach defined threshold %f mA' %
          current_min_threshold)
    # Fail if all Plankton INA voltage samples are not within specified range
    tolerance = testing_volt * 1000 * voltage_tolerance
    if not any(abs(
        v - testing_volt * 1000.0) <= tolerance for v in sampled_ina_voltage):
      raise factory.FactoryTestFailure(
          'Plankton INA voltage did not meet expected charge voltage')
    # If args.check_ina_current, fail if average of Plankton INA current
    # samples is not within specified range.
    self.CheckINASampleCurrent(sampled_ina_current, charging=True)

  def TestDischarging(self):
    """Tests discharging within args.discharge_duration_secs.

    The test runs under high system load to maximize battery discharge current.

    Raises:
      FactoryTestFailure: If the sampled battery discharge current does not pass
          the given threshold in dargs.
    """

    current_min_threshold = self.args.min_discharge_current_mA
    if current_min_threshold is None:
      return

    logging.info('Testing discharge...')
    self._template.SetState(_TESTING_DISCHARGE)
    self._bft_fixture.SetDeviceEngaged('CHARGE_5V', engage=False)

    # Discharge under high system load.
    with utils.LoadManager(self.args.discharge_duration_secs):
      (sampled_battery_current, sampled_ina_current, _) = (
          self.SampleCurrentAndVoltage(self.args.discharge_duration_secs))
    # Fail if all samples are over threshold.
    if not any(
        c < current_min_threshold for c in sampled_battery_current):
      raise factory.FactoryTestFailure(
          'Battery discharge current did not reach defined threshold %f mA' %
          current_min_threshold)
    # If args.check_ina_current, fail if average of Plankton INA current
    # samples is not within specified range.
    self.CheckINASampleCurrent(sampled_ina_current, charging=False)

  def CheckINASampleCurrent(self, ina_sample, charging):
    """Checks if average INA current is within range on Plankton.

    Args:
      ina_sample: A list of sampled Plankton INA current.
      charging: True if testing charging; False if discharging.

    Raises:
      FactoryTestFailure if samples are not within range.
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
      raise factory.FactoryTestFailure(
          'Plankton INA %s current average %d mA did not within %d - %d' %
          ('charge' if charging else 'discharge', average, ina_min, ina_max))

  def runTest(self):
    """Runs charge test.

    Raises:
      FactoryTestFailure: Battery attribute error.
    """
    if not self._power.CheckBatteryPresent():
      raise factory.FactoryTestFailure(
          'Cannot locate battery sysfs path. Missing battery?')
    if (self.args.check_battery_cycle and
        int(self._power.GetBatteryAttribute('cycle_count').strip()) != 0):
      raise factory.FactoryTestFailure('Battery cycle count is not zero')

    # Set charge state to 'charge'
    self._board.SetChargeState(Board.ChargeState.CHARGE)
    logging.info('Set charge state: CHARGE')

    self.Check5VINACurrent()
    self.TestCharging(self.args.min_charge_5V_current_mA,
                      self.args.ina_voltage_tolernace, testing_volt=5)
    self.TestCharging(self.args.min_charge_12V_current_mA,
                      self.args.ina_voltage_tolernace, testing_volt=12)
    self.TestCharging(self.args.min_charge_20V_current_mA,
                      self.args.ina_voltage_tolernace, testing_volt=20)
    self.TestDischarging()
