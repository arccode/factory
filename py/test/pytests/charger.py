# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Test that charger can charge/discharge battery for certain amount
of change within certain time under certain load.
"""

import logging
import os
import time

from cros.factory.device import device_utils
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test.utils import stress_manager
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils


CHARGE_TOLERANCE = 0.001


class ChargerTest(test_case.TestCase):
  """This class tests that charger can charge/discharge battery for certain
  amount of change within certain time under certain load.

  Properties:
    _power: The Power object to get AC/Battery info and charge percentage.
  """
  ARGS = [
      Arg('min_starting_charge_pct', (int, float),
          'minimum starting charge level when testing', default=20.0),
      Arg('max_starting_charge_pct', (int, float),
          'maximum starting charge level when testing', default=90.0),
      Arg('starting_timeout_secs', int, 'Maximum allowed time to regulate'
          'battery to starting_charge_pct', default=300),
      Arg('check_battery_current', bool, 'Check battery current > 0'
          'when charging and < 0 when discharging', default=True),
      Arg('battery_check_delay_sec', int, 'Delay of checking battery current. '
          'This can be used to handle slowly settled battery current.',
          default=3),
      Arg('verbose_log_period_secs', int, 'Log debug data every x seconds '
          'to verbose log file.', default=3),
      Arg('log_period_secs', int, 'Log test data every x seconds.',
          default=60),
      Arg('use_percentage', bool, 'True if using percentage as charge unit '
          'in spec list. False if using mAh.', default=True),
      Arg('charger_type', str, 'Type of charger required.', default=None),
      Arg('spec_list', list, 'A list of [charge_change, timeout_secs, load]\n'
          'Charger needs to achieve charge_change difference within\n'
          'timeout_secs seconds under load.\n'
          'Positive charge_change is for charging and negative one is\n'
          'for discharging.\n'
          'One unit of load is one thread doing memory copy in stressapptest.\n'
          'The default value for load is the number of processor',
          default=[[2, 300, 1], [-2, 300]])
  ]

  def setUp(self):
    """Sets the test ui, template and the thread that runs ui. Initializes
    _board and _power."""
    self._dut = device_utils.CreateDUTInterface()
    self._power = self._dut.power
    self._min_starting_charge = float(self.args.min_starting_charge_pct)
    self._max_starting_charge = float(self.args.max_starting_charge_pct)

    for spec in self.args.spec_list:
      self.assertTrue(2 <= len(spec) <= 3,
                      'spec_list item %r should have length 2 or 3' % spec)

    verbose_log_path = session.GetVerboseTestLogPath()
    file_utils.TryMakeDirs(os.path.dirname(verbose_log_path))
    logging.info('Raw verbose logs saved in %s', verbose_log_path)
    self._verbose_log = open(verbose_log_path, 'a')

    # Group checker for Testlog.
    self._group_checker = testlog.GroupParam(
        'charge_info', ['load', 'target', 'charge', 'elapsed', 'status'])
    testlog.UpdateParam('target', param_type=testlog.PARAM_TYPE.argument)

  def _GetLabelWithUnit(self, value):
    return '%.2f%s' % (value, '%' if self.args.use_percentage else 'mAh')

  def _GetRegulateChargeText(self, charge, target, timeout, load,
                             battery_current):
    """Makes label to show subtest information

    Args:
      charge: current battery charge percentage.
      target: target battery charge percentage.
      timeout: remaining time for this subtest.
      load: load argument for this subtest.
      battery_current: battery current.

    Returns:
      A html label to show in test ui.
    """
    action = _('Discharging') if charge > target else _('Charging')
    return [
        _('{action} to {target} '
          '(Current charge: {charge}, battery current: {battery_current} mA)'
          ' under load {load}.',
          action=action,
          target=self._GetLabelWithUnit(target),
          charge=self._GetLabelWithUnit(charge),
          battery_current=battery_current,
          load=load), '<br>',
        _('Time remaining: {timeout:.0f} sec.', timeout=timeout)
    ]

  def _NormalizeCharge(self, charge_pct):
    if self.args.use_percentage:
      return charge_pct
    return charge_pct * self._power.GetChargeFull() / 100.0

  def _CheckPower(self):
    """Checks battery and AC power adapter are present."""
    self.assertTrue(self._power.CheckBatteryPresent(), 'Cannot find battery.')
    self.assertTrue(self._power.CheckACPresent(), 'Cannot find AC power.')
    if self.args.charger_type:
      self.assertEqual(self._power.GetACType(), self.args.charger_type,
                       'Incorrect charger type: %s' % self._power.GetACType())

  def _GetCharge(self, use_percentage=True):
    """Gets charge level through power interface"""
    if use_percentage:
      charge = self._power.GetChargePct(get_float=True)
    else:
      charge = float(self._power.GetChargeMedian())
    self.assertIsNotNone(charge, 'Error getting battery charge state.')
    return charge

  def _GetBatteryCurrent(self):
    """Gets battery current through board"""
    try:
      return self._power.GetBatteryCurrent()
    except Exception as e:
      self.fail('Cannot get battery current on this board. %s' % e)

  def _GetChargerCurrent(self):
    """Gets current that charger wants to drive through board"""
    try:
      return self._power.GetChargerCurrent()
    except NotImplementedError:
      return None

  def _GetPowerInfo(self):
    """Gets power info on this board"""
    try:
      return self._power.GetPowerInfo()
    except NotImplementedError:
      return None

  def _Meet(self, charge, target, moving_up):
    """Checks if charge has meet the target.

    Args:
      charge: The current charge value.
      target: The target charge value.
      moving_up: The direction of charging. Should be True or False.

    Returns:
      True if charge is close to target enough, or charge > target when
        moving up, or charge < target when moving down.
      False otherwise.
    """
    if abs(charge - target) < CHARGE_TOLERANCE:
      return True
    if moving_up:
      return charge > target
    return charge < target

  def _RegulateCharge(self, charge_change, timeout_secs, load=None):
    """Checks if the charger can meet the spec.

    Checks if charge percentage and battery current are available.
    Decides whether to charge or discharge battery based on
    charge_change.
    Sets the load and tries to meet the difference within timeout.

    Args:
      charge_change: The difference of charge percentage that should be
          achieved.
      timeout_secs: Timeout in seconds.
      load: One unit of load is one thread doing memory copy in stressapptest.
          Default to number of cpu core.
    """
    if load is None:
      load = self._dut.info.cpu_count

    charge = self._GetCharge(self.args.use_percentage)
    battery_current = self._GetBatteryCurrent()
    target = charge + charge_change
    moving_up = None
    if abs(target - charge) < CHARGE_TOLERANCE:
      logging.warning('Current charge is %s, target is %s.'
                      ' They are too close so there is no need to'
                      'charge/discharge.', self._GetLabelWithUnit(charge),
                      self._GetLabelWithUnit(target))
      event_log.Log('target_too_close', charge=charge, target=target)
      with self._group_checker:
        testlog.LogParam('status', 'target_too_close')
        testlog.LogParam('target', target)
        testlog.LogParam('charge', charge)
        testlog.LogParam('load', load)
        testlog.LogParam('elapsed', 0)
      return

    if charge > target:
      logging.info('Current charge is %s, discharge the battery to %s.',
                   self._GetLabelWithUnit(charge),
                   self._GetLabelWithUnit(target))
      self.ui.SetState(_('Testing discharge'))
      self._SetDischarge()
      moving_up = False
    elif charge < target:
      logging.info('Current charge is %s, charge the battery to %s.',
                   self._GetLabelWithUnit(charge),
                   self._GetLabelWithUnit(target))
      self.ui.SetState(_('Testing charger'))
      self._SetCharge()
      moving_up = True

    assert moving_up is not None

    if load > 0:
      stress_manager_instance = stress_manager.StressManager(self._dut)
    else:
      stress_manager_instance = stress_manager.DummyStressManager()

    with stress_manager_instance.Run(num_threads=load):
      start_time = time.time()
      last_verbose_log_time = None
      last_log_time = None
      spec_end_time = start_time + timeout_secs
      while time.time() < spec_end_time:
        elapsed = time.time() - start_time
        self.ui.SetState(
            self._GetRegulateChargeText(charge, target, timeout_secs - elapsed,
                                        load, battery_current))
        self._CheckPower()
        charge = self._GetCharge(self.args.use_percentage)
        battery_current = self._GetBatteryCurrent()

        with self._group_checker:
          testlog.LogParam('target', target)
          testlog.LogParam('charge', charge)
          testlog.LogParam('load', load)
          testlog.LogParam('elapsed', elapsed)
          testlog.LogParam('status', 'running')

        if self._Meet(charge, target, moving_up):
          logging.info('Meet difference from %s to %s'
                       ' in %d secs under %d load.',
                       self._GetLabelWithUnit(target - charge_change),
                       self._GetLabelWithUnit(target), elapsed, load)
          event_log.Log('meet', elapsed=elapsed, load=load, target=target,
                        charge=charge)
          with self._group_checker:
            testlog.LogParam('target', target)
            testlog.LogParam('charge', charge)
            testlog.LogParam('load', load)
            testlog.LogParam('elapsed', elapsed)
            testlog.LogParam('status', 'meet')
          self.ui.SetState(
              _('OK! Meet {target}', target=self._GetLabelWithUnit(target)))
          self.Sleep(1)
          return

        if elapsed >= self.args.battery_check_delay_sec:
          charger_current = self._GetChargerCurrent()

          if (not last_verbose_log_time or
              elapsed - last_verbose_log_time >
              self.args.verbose_log_period_secs):
            self._VerboseLog(charge, charger_current, battery_current)
            last_verbose_log_time = elapsed

          if (not last_log_time or
              elapsed - last_log_time > self.args.log_period_secs):
            self._Log(charge, charger_current, battery_current)
            last_log_time = elapsed

          if charge < target:
            self._CheckCharge(charger_current, battery_current)
          else:
            self._CheckDischarge(battery_current)

        self.Sleep(1)

      event_log.Log('not_meet', load=load, target=target, charge=charge)
      with self._group_checker:
        elapsed = time.time() - start_time
        testlog.LogParam('target', target)
        testlog.LogParam('charge', charge)
        testlog.LogParam('load', load)
        testlog.LogParam('elapsed', elapsed)
        testlog.LogParam('status', 'not_meet')
      self.fail('Cannot regulate battery to %s in %d seconds.' %
                (self._GetLabelWithUnit(target), timeout_secs))

  def _VerboseLog(self, charge, charger_current, battery_current):
    """Log data to verbose log"""
    self._verbose_log.write(time.strftime('%Y-%m-%d %H:%M:%S\n', time.gmtime()))
    self._verbose_log.write('Charge = %s\n' % self._GetLabelWithUnit(charge))
    if charger_current is not None:
      self._verbose_log.write('Charger current = %d\n' % charger_current)
    self._verbose_log.write('Battery current = %d\n' % battery_current)
    self._verbose_log.write('Power info =\n%s\n' % self._GetPowerInfo())
    self._verbose_log.flush()

  def _Log(self, charge, charger_current, battery_current):
    """Log data"""
    logging.info('Charge = %s', self._GetLabelWithUnit(charge))
    if charger_current is not None:
      logging.info('Charger current = %d', charger_current)
    logging.info('Battery current = %d', battery_current)

  def _CheckCharge(self, charger_current, battery_current):
    """Checks current in charging state"""
    if charger_current:
      self.assertGreater(charger_current, 0, 'Abnormal charger current')
    if self.args.check_battery_current:
      self.assertGreater(battery_current, 0, 'Abnormal battery current')

  def _CheckDischarge(self, battery_current):
    """Checks current in discharging state"""
    if self.args.check_battery_current:
      self.assertLess(battery_current, 0, 'Abnormal battery current')

  def _SetCharge(self):
    """Sets charger state to CHARGE"""
    try:
      self._power.SetChargeState(self._power.ChargeState.CHARGE)
    except Exception as e:
      self.fail('Cannot set charger state to CHARGE on this board. %s' % e)
    else:
      self.Sleep(1)

  def _SetDischarge(self):
    """Sets charger state to DISCHARGE"""
    try:
      self._power.SetChargeState(self._power.ChargeState.DISCHARGE)
    except Exception as e:
      self.fail('Cannot set charger state to DISCHARGE on this board. %s' % e)
    else:
      self.Sleep(1)

  def runTest(self):
    """Main entrance of charger test."""
    self._CheckPower()
    charge = self._GetCharge(self.args.use_percentage)

    min_charge = self._NormalizeCharge(self._min_starting_charge)
    max_charge = self._NormalizeCharge(self._max_starting_charge)

    if charge < min_charge:
      start_charge_diff = min_charge - charge
    elif charge > max_charge:
      start_charge_diff = max_charge - charge
    else:
      start_charge_diff = None

    # Try to meet start_charge_diff as soon as possible.
    # When trying to charge, use 0 load.
    # When trying to discharge, use full load.
    if start_charge_diff:
      self._RegulateCharge(start_charge_diff, self.args.starting_timeout_secs,
                           (0 if start_charge_diff > 0 else None))
    # Start testing the specs when battery charge is between
    # min_starting_charge_pct and max_starting_charge_pct.
    for spec in self.args.spec_list:
      self._RegulateCharge(*spec)

  def tearDown(self):
    # Must enable charger to charge or we will drain the battery!
    self._SetCharge()
