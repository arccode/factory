# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''This is a factory test to test battery charging/discharging current.

dargs:
  min_charging_current: The minimum allowed charging current. In mA.
  min_discharging_current: The minimum allowed discharging current. In mA.
  timeout_secs: The timeout of detecting required charging/discharging current.
'''

import logging
import unittest

from cros.factory import system
from cros.factory.system.board import Board
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.utils.net_utils import PollForCondition

_TEST_TITLE = test_ui.MakeLabel('Battery Current Test', u'充電放電电流測試')

def _PROMPT_TEXT(charge, current, target):
  return test_ui.MakeLabel(
      'Waiting for %s current to meet %d mA. (Currently %s at %d mA)' %
          ('charging' if charge else 'discharging',
           target,
           'charging' if current >= 0 else 'discharging',
           abs(current)),
      u'等待%s电流大于 %d mA. (目前%s中:%d mA)' %
          (u'充电' if charge else u'放电',
           target,
           u'充电' if current >= 0 else u'放电',
           abs(current)))

_CHARGE_TEXT = lambda c, t: _PROMPT_TEXT(True, c, t)
_DISCHARGE_TEXT = lambda c, t: _PROMPT_TEXT(False, c, t)

class BatteryCurrentTest(unittest.TestCase):
  """
  A factory test to test battery charging/discharging current.
  """
  ARGS = [
      Arg('min_charging_current', int,
          'minimum allowed charging current', optional=True),
      Arg('min_discharging_current', int,
          'minimum allowed discharging current', optional=True),
      Arg('timeout_secs', int,
          'Test timeout value', default=10, optional=True),
      Arg('max_battery_level', int,
          'maximum allowed starting battery level', optional=True),
      ]

  def setUp(self):
    """Sets the test ui, template and the thread that runs ui. Initializes
    _board and _power."""
    self._board = system.GetBoard()
    self._power = self._board.power
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)

  def _LogCurrent(self, current):
    if current >= 0:
      logging.info('Charging current = %d mA', current)
    else:
      logging.info('Discharging current = %d mA', -current)

  def _CheckCharge(self):
    current = self._board.GetBatteryCurrent()
    target = self.args.min_charging_current
    self._LogCurrent(current)
    self._template.SetState(_CHARGE_TEXT(current, target))
    return current >= target

  def _CheckDischarge(self):
    current = self._board.GetBatteryCurrent()
    target = self.args.min_discharging_current
    self._LogCurrent(current)
    self._template.SetState(_DISCHARGE_TEXT(current, target))
    return -current >= target

  def runTest(self):
    """Main entrance of charger test."""
    if self.args.max_battery_level:
      self.assertLessEqual(self._power.GetChargePct(),
                           self.args.max_battery_level,
                           'Starting battery level too high')
    self._ui.Run(blocking=False)
    if self.args.min_charging_current:
      self._board.SetChargeState(Board.ChargeState.CHARGE)
      PollForCondition(self._CheckCharge, poll_interval_secs=0.5,
                       condition_name='ChargeCurrent',
                       timeout=self.args.timeout_secs)
    if self.args.min_discharging_current:
      self._board.SetChargeState(Board.ChargeState.DISCHARGE)
      PollForCondition(self._CheckDischarge, poll_interval_secs=0.5,
                       condition_name='DischargeCurrent',
                       timeout=self.args.timeout_secs)

  def tearDown(self):
    # Must enable charger to charge or we will drain the battery!
    self._board.SetChargeState(Board.ChargeState.CHARGE)
