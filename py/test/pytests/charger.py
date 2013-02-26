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
      options.max_charge_pct in the test_list. Default value is 85.
  starting_timeout_secs: Maximum allowed time to regulate battery to
      starting_charge_pct. Default value is 300 secs.
  spec_list:
      A list of tuples. Each tuple contains
      (charge_pct_change, timeout_secs, load)
      Charger needs to achieve charge_pct_change difference within
      timeout_secs seconds under load.
      Positive charge_pct_change is for charging and negative one is
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
  return test_ui.MakeLabel(
      ('Discharging' if charge > target else 'Charging') +
      'to %d%% (Current charge: %d%%, battery current: %d mA) under load %d.'
      '<br>Time remaining: %d sec.' %
      (target, charge, battery_current, load, timeout),
      (u'放電' if charge > target else u'充電') +
      u'至 %d%% (目前電量為 %d%%, 電池電流 %d mA)'
      u'負載 %d.<br>剩餘時間: %d 秒.' %
      (target, charge, battery_current, load, timeout))

def _MEET_TEXT(target):
  """Makes label to show subtest completes.
  Args:
    target: target battery charge percentage of this subtest.

  Returns:
    A html label to show in test ui.
  """
  return test_ui.MakeLabel('OK! Meet %d%%' % target, u'OK! 達到 %d%%' % target)

_CHARGE_TEXT = test_ui.MakeLabel('Testing charger', u'測試充電中')
_DISCHARGE_TEXT = test_ui.MakeLabel('Testing discharge', u'測試放電中')

Spec = namedtuple('Spec', 'charge_pct_change timeout_secs load')

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
      Arg('starting_charge_pct', int, 'starting charge level when testing',
          default=85),
      Arg('starting_timeout_secs', int, 'Maximum allowed time to regulate'
          'battery to starting_charge_pct', default=300),
      Arg('check_battery_current', bool, 'Check battery current > 0'
          'when charging and < 0 when discharging', default=True),
      Arg('spec_list', list, 'A list of tuples. Each tuple contains\n'
          '(charge_pct_change, timeout_secs, load)\n'
          'Charger needs to achieve charge_pct_change difference within\n'
          'timeout_secs seconds under load.\n'
          'Positive charge_pct_change is for charging and negative one is\n'
          'for discharging.\n'
          'One unit of load is one thread doing memory copy in stressapptest.\n'
          'The default value for load is the number of processor',
          default=[(2, 300, ), (-2, 300, )])
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

  def _CheckPower(self):
    """Checks battery and AC power adapter are present."""
    self.assertTrue(self._power.CheckBatteryPresent(), 'Cannot find battery.')
    self.assertTrue(self._power.CheckACPresent(), 'Cannot find AC power.')

  def _GetChargePct(self):
    """Gets charge percentage through power interface"""
    charge = self._power.GetChargePct()
    self.assertTrue(charge, 'Error getting battery charge state.')
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

  def _RegulateCharge(self, spec):
    """Checks if the charger can meet the spec.
    Checks if charge percentage and battery current are available.
    Decides whether to charge or discharge battery based on
    spec.charge_pct_change.
    Sets the load and tries to meet the difference within timeout.

    Args:
      spec: A Spec namedtuple.
    """
    charge = self._GetChargePct()
    battery_current = self._GetBatteryCurrent()
    target = charge + spec.charge_pct_change

    if charge > target:
      logging.info('Current charge is %d%%, discharge the battery to %d%%.',
                   charge, target)
      self._SetDischarge()
    elif charge < target:
      logging.info('Current charge is %d%%, charge the battery to %d%%.',
                   charge, target)
      self._SetCharge()

    with LoadManager(duration_secs=spec.timeout_secs,
                     num_threads=spec.load):
      for elapsed in xrange(spec.timeout_secs):
        self._template.SetState(_REGULATE_CHARGE_TEXT(
            charge, target, spec.timeout_secs - elapsed, spec.load,
            battery_current))
        time.sleep(1)
        charge = self._GetChargePct()
        battery_current = self._GetBatteryCurrent()
        if charge == target:
          logging.info('Meet difference from %d%% to %d%%'
                       'in %d secs under %d load.',
                       target - spec.charge_pct_change, target,
                       elapsed, spec.load)
          self._template.SetState(_MEET_TEXT(target))
          time.sleep(3)
          return
        else:
          if charge < target:
            self._CheckCharge()
          else:
            self._CheckDischarge()

      self.fail('Cannot regulate battery to %d%% in %d seconds.' %
                (target, spec.timeout_secs))

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
      time.sleep(3)

  def _SetDischarge(self):
    """Sets charger state to DISCHARGE"""
    self._template.SetState(_DISCHARGE_TEXT)
    try:
      self._board.SetChargeState(Board.ChargeState.DISCHARGE)
    except Exception, e:
      self.fail('Cannot set charger state to DISCHARGE on this board. %s' % e)
    else:
      time.sleep(3)

  def _GetSpec(self, charge_pct_change, timeout_secs, load=None):
    """Gets Spec with default load value set as number of cpus"""
    if load is None:
      load = multiprocessing.cpu_count()
    return Spec(charge_pct_change, timeout_secs, load)

  def runTest(self):
    '''Main entrance of charger test.'''
    self._thread.start()
    try:
      self._CheckPower()
      charge = self._GetChargePct()
      # Try to meet starting_charge_pct as soon as possible.
      # When trying to charge, use 0 load.
      # When trying to discharge, use full load.
      self._RegulateCharge(
          self._GetSpec(self.args.starting_charge_pct - charge,
                        self.args.starting_timeout_secs,
                        0 if self.args.starting_charge_pct > charge else None))
      # Start testing the specs when battery has starting_charge_pct charge.
      for spec in self.args.spec_list:
        self._RegulateCharge(self._GetSpec(*spec))
    except Exception, e:
      self._ui.Fail(str(e))
      raise
    else:
      self._ui.Pass()

  def tearDown(self):
    self._thread.join()
