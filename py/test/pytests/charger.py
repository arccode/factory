# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''This is a factory test to test charger.
Test that charger can charge/discharge battery for certain
amount of change within certain time under certain load.

dargs:
  starting_charge_pct: Starting charge level when testing.
      This value should be close to options.min_charge_pct and
      options.max_charge_pct in the test_list. Default value is 85.0.
  starting_timeout_secs: Maximum allowed time to regulate battery to
      starting_charge_pct. Default value is 300 secs.
  use_percentage: True if using percentage as charge unit in spec list.
      False if using mAh. Default value is True.
  check_battery_current: Check battery current > 0 when charging and < 0
      when discharging.
  battery_check_delay_sec: Delay of checking battery current. This can be
      used to handle slowly settled battery current. Default value is 3 secs.
  spec_list:
      A list of tuples. Each tuple contains
      (charge_change, timeout_secs, load)
      Charger needs to achieve charge_change difference within
      timeout_secs seconds under load.
      Positive charge_change is for charging and negative one is
      for discharging.
      One unit of load is one thread doing memory copy in stressapptest.
      The default value for load is the number of processor,
      Default spec_list=[(2, 300, ), (-2, 300, )])
'''

import logging
import multiprocessing
import threading
import time
import unittest
from collections import namedtuple

from cros.factory import system
from cros.factory.system.board import Board
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.utils import LoadManager

_TEST_TITLE = test_ui.MakeLabel('Charger Test', u'充電放電測試')

def _REGULATE_CHARGE_TEXT(charge, target, timeout, load,
                          battery_current, use_percentage):
  """Makes label to show subtest information
  Args:
    charge: current battery charge percentage.
    target: target battery charge percentage.
    timeout: remaining time for this subtest.
    load: load argument for this subtest.
    battery_current: battery current.
    use_percentage: Whether to use percentage or mAh.

  Returns:
    A html label to show in test ui.
  """
  unit = '%' if use_percentage else 'mAh'
  return test_ui.MakeLabel(
      ('Discharging' if charge > target else 'Charging') +
      ' to %.2f%s (Current charge: %.2f%s, battery current: %d mA) under load '
      '%d.<br>Time remaining: %d sec.' %
      (target, unit, charge, unit, battery_current, load, timeout),
      (u'放電' if charge > target else u'充電') +
      u'至 %.2f%s (目前電量為 %.2f%s, 電池電流 %d mA)'
      u'負載 %d.<br>剩餘時間: %d 秒.' %
      (target, unit, charge, unit, battery_current, load, timeout))

def _MEET_TEXT(target, use_percentage):
  """Makes label to show subtest completes.
  Args:
    target: target battery charge percentage of this subtest.
    use_percentage: Whether to use percentage or mAh.

  Returns:
    A html label to show in test ui.
  """
  unit = '%' if use_percentage else 'mAh'
  return test_ui.MakeLabel('OK! Meet %.2f%s' % (target, unit),
                           u'OK! 達到 %.2f%s' % (target, unit))

_CHARGE_TEXT = test_ui.MakeLabel('Testing charger', u'測試充電中')
_DISCHARGE_TEXT = test_ui.MakeLabel('Testing discharge', u'測試放電中')

Spec = namedtuple('Spec', 'charge_change timeout_secs load')

CHARGE_TOLERANCE = 0.001

class ChargerTest(unittest.TestCase):
  """This class tests that charger can charge/discharge battery for certain
  amount of change within certain time under certain load.

  Properties:
    _board: The Board object to provide interface to battery and charger.
    _power: The Power object to get AC/Battery info and charge percentage.
    _ui: Test UI.
    _template: Test template.
    _thread: The thread to run ui.
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
      Arg('use_percentage', bool, 'True if using percentage as charge unit '
          'in spec list. False if using mAh.', default=True),
      Arg('spec_list', list, 'A list of tuples. Each tuple contains\n'
          '(charge_change, timeout_secs, load)\n'
          'Charger needs to achieve charge_change difference within\n'
          'timeout_secs seconds under load.\n'
          'Positive charge_change is for charging and negative one is\n'
          'for discharging.\n'
          'One unit of load is one thread doing memory copy in stressapptest.\n'
          'The default value for load is the number of processor',
          default=[(2, 300, 1), (-2, 300, )])
      ]

  def setUp(self):
    """Sets the test ui, template and the thread that runs ui. Initializes
    _board and _power."""
    self._board = system.GetBoard()
    self._power = self._board.power
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._thread = threading.Thread(target=self._ui.Run)
    self._min_starting_charge = float(self.args.min_starting_charge_pct)
    self._max_starting_charge = float(self.args.max_starting_charge_pct)
    self._unit = '%' if self.args.use_percentage else 'mAh'

  def _NormalizeCharge(self, charge_pct):
    if self.args.use_percentage:
      return charge_pct
    else:
      return charge_pct * self._power.GetChargeFull() / 100.0

  def _CheckPower(self):
    """Checks battery and AC power adapter are present."""
    self.assertTrue(self._power.CheckBatteryPresent(), 'Cannot find battery.')
    self.assertTrue(self._power.CheckACPresent(), 'Cannot find AC power.')

  def _GetCharge(self, use_percentage=True):
    """Gets charge level through power interface"""
    if use_percentage:
      charge = self._power.GetChargePct(get_float=True)
    else:
      charge = float(self._power.GetCharge())
    self.assertTrue(charge is not None, 'Error getting battery charge state.')
    return charge

  def _GetBatteryCurrent(self):
    """Gets battery current through board"""
    try:
      battery_current = self._board.GetBatteryCurrent()
    except Exception, e:
      self.fail('Cannot get battery current on this board. %s' % e)
    else:
      return battery_current

  def _GetChargerCurrent(self):
    """Gets current that charger wants to drive through board"""
    try:
      charger_current = self._board.GetChargerCurrent()
    except NotImplementedError:
      logging.exception('Charger current is not available on this board')
      return None
    else:
      return charger_current

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
    self.assertTrue(moving_up is not None)
    if abs(charge - target) < CHARGE_TOLERANCE:
      return True
    if moving_up:
      return charge > target
    else:
      return charge < target

  def _RegulateCharge(self, spec):
    """Checks if the charger can meet the spec.
    Checks if charge percentage and battery current are available.
    Decides whether to charge or discharge battery based on
    spec.charge_change.
    Sets the load and tries to meet the difference within timeout.

    Args:
      spec: A Spec namedtuple.
    """
    charge = self._GetCharge(self.args.use_percentage)
    battery_current = self._GetBatteryCurrent()
    target = charge + spec.charge_change
    moving_up = None
    if abs(target - charge) < CHARGE_TOLERANCE:
      logging.warning('Current charge is %.2f%s, target is %.2f%s.'
                      ' They are too close so there is no need to'
                      'charge/discharge.', charge, self._unit,
                      target, self._unit)
      return

    elif charge > target:
      logging.info('Current charge is %.2f%s, discharge the battery to %.2f%s.',
                   charge, self._unit, target, self._unit)
      self._SetDischarge()
      moving_up = False
    elif charge < target:
      logging.info('Current charge is %.2f%s, charge the battery to %.2f%s.',
                   charge, self._unit, target, self._unit)
      self._SetCharge()
      moving_up = True

    # charge should move up or down.
    self.assertTrue(moving_up is not None)

    with LoadManager(duration_secs=spec.timeout_secs,
                     num_threads=spec.load):
      for elapsed in xrange(spec.timeout_secs):
        self._template.SetState(_REGULATE_CHARGE_TEXT(
            charge, target, spec.timeout_secs - elapsed, spec.load,
            battery_current, self.args.use_percentage))
        time.sleep(1)
        charge = self._GetCharge(self.args.use_percentage)
        logging.info('Current charge is %.2f%s, target is %.2f%s.',
                     charge, self._unit, target, self._unit)
        battery_current = self._GetBatteryCurrent()
        if self._Meet(charge, target, moving_up):
          logging.info('Meet difference from %.2f%s to %.2f%s'
                       ' in %d secs under %d load.',
                       target - spec.charge_change, self._unit,
                       target, self._unit,
                       elapsed, spec.load)
          self._template.SetState(_MEET_TEXT(target, self.args.use_percentage))
          time.sleep(1)
          return
        elif elapsed >= self.args.battery_check_delay_sec:
          if charge < target:
            self._CheckCharge()
          else:
            self._CheckDischarge()

      self.fail('Cannot regulate battery to %.2f%s in %d seconds.' %
                (target, self._unit, spec.timeout_secs))

  def _CheckCharge(self):
    """Checks current in charging state """
    charger_current = self._GetChargerCurrent()
    if charger_current:
      logging.info('Charger current = %d', charger_current)
      self.assertTrue(charger_current > 0, 'Abnormal charger current')
    battery_current = self._GetBatteryCurrent()
    logging.info('Battery current = %d.', battery_current)
    factory.console.info('battery current %d' % battery_current)
    if self.args.check_battery_current:
      self.assertTrue(battery_current > 0, 'Abnormal battery current')

  def _CheckDischarge(self):
    """Checks current in discharging state """
    charger_current = self._GetChargerCurrent()
    if charger_current:
      logging.info('Charger current = %d', charger_current)
    battery_current = self._GetBatteryCurrent()
    logging.info('Battery current = %d.', battery_current)
    factory.console.info('battery current %d' % battery_current)
    if self.args.check_battery_current:
      self.assertTrue(battery_current < 0, 'Abnormal battery current')

  def _SetCharge(self):
    """Sets charger state to CHARGE"""
    self._template.SetState(_CHARGE_TEXT)
    try:
      self._board.SetChargeState(Board.ChargeState.CHARGE)
    except Exception, e:
      self.fail('Cannot set charger state to CHARGE on this board. %s' % e)
    else:
      time.sleep(1)

  def _SetDischarge(self):
    """Sets charger state to DISCHARGE"""
    self._template.SetState(_DISCHARGE_TEXT)
    try:
      self._board.SetChargeState(Board.ChargeState.DISCHARGE)
    except Exception, e:
      self.fail('Cannot set charger state to DISCHARGE on this board. %s' % e)
    else:
      time.sleep(1)

  def _GetSpec(self, charge_change, timeout_secs, load=None):
    """Gets Spec with default load value set as number of cpus"""
    if load is None:
      load = multiprocessing.cpu_count()
    return Spec(charge_change, timeout_secs, load)

  def runTest(self):
    '''Main entrance of charger test.'''
    self._thread.start()
    try:
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
        self._RegulateCharge(
            self._GetSpec(start_charge_diff,
                          self.args.starting_timeout_secs,
                          0 if start_charge_diff > 0 else None))
      # Start testing the specs when battery charge is between
      # min_starting_charge_pct and max_starting_charge_pct.
      for spec in self.args.spec_list:
        self._RegulateCharge(self._GetSpec(*spec))
    except Exception, e:
      self._ui.Fail(str(e))
      raise
    else:
      self._ui.Pass()

  def tearDown(self):
    self._thread.join()
