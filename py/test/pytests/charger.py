# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''This is a factory test to test charger.'''

import logging
import threading
import time
import unittest

from cros.factory import system
from cros.factory.system.ec import EC
from cros.factory.system.power import Power
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg

_TEST_TITLE = test_ui.MakeLabel('Charger Test', u'充電測試')

def _DISCHARGE_TEXT(current, target, timeout):
  return test_ui.MakeLabel(
    'Discharging to %d%% (Current: %d%%).<br>Time remaining: %d sec.' %
    (target, current, timeout),
    u'放電至 %d%% (目前電量為 %d%%).<br>剩餘時間: %d 秒.' %
    (target, current, timeout))

_CHARGE_TEXT = test_ui.MakeLabel('Testing charger', u'測試充電中')

class ChargerTest(unittest.TestCase):
  ARGS = [
      Arg('max_charge_pct', int, 'Maximum allowed charge level when testing',
          default=85),
      Arg('timeout', int, 'Maximum allowed time to discharge battery',
          default=150),
      ]

  def setUp(self):
    self._ec = system.GetEC()
    self._power = Power()
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._thread = threading.Thread(target=self._ui.Run)

  def CheckPower(self):
    self.assertTrue(self._power.CheckBatteryPresent(), 'Cannot find battery.')
    self.assertTrue(self._power.CheckACPresent(), 'Cannot find AC power.')

  def Discharge(self):
    charge = self._power.GetChargePct()
    self.assertTrue(charge, 'Error getting battery state.')
    if charge <= self.args.max_charge_pct:
      return
    self._ec.SetChargeState(EC.ChargeState.DISCHARGE)

    for elapsed in xrange(self.args.timeout):
      self._template.SetState(_DISCHARGE_TEXT(charge,
                                              self.args.max_charge_pct,
                                              self.args.timeout - elapsed))
      time.sleep(1)
      charge = self._power.GetChargePct()
      if charge <= self.args.max_charge_pct:
        return

    self.fail('Cannot discharge battery to %d%% in %d seconds.' %
              (self.args.max_charge_pct, self.args.timeout))

  def TestCharge(self):
    self._template.SetState(_CHARGE_TEXT)
    self._ec.SetChargeState(EC.ChargeState.CHARGE)
    time.sleep(3)
    charger_current = self._ec.GetChargerCurrent()
    battery_current = self._ec.GetBatteryCurrent()
    logging.info('Charger current = %d, battery current = %d.',
                 charger_current, battery_current)
    self.assertFalse(charger_current > 0 and battery_current <= 0,
                     'Abnormal battery current')

  def runTest(self):
    '''Main entrance of charger test.'''
    self._thread.start()
    try:
      self.CheckPower()
      self.Discharge()
      self.TestCharge()
    except Exception, e:
      self._ui.Fail(str(e))
      raise
    else:
      self._ui.Pass()

  def tearDown(self):
    self._thread.join()
