# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''
This is a factory test that only pass when battery is charged to specific
level.
'''

import logging
import threading
import time
import unittest

from cros.factory import system
from cros.factory.event_log import Log
from cros.factory.system.board import Board
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg

_TEST_TITLE = test_ui.MakeLabel('Charging', u'充电')

def FormatTime(seconds):
  return "%d:%02d:%02d" % (seconds / 3600, (seconds / 60) % 60, seconds % 60)

def MakeChargeTextLabel(start, current, target, elapsed, remaining):
  _LABEL_EN = ('Charging to %d%% (Start: %d%%. Current: %d%%.)<br>' +
               'Time elapsed: %s' + '&nbsp;' * 8 + 'Time remaining: %s')
  _LABEL_ZH = (u'充电至 %d%% (起始电量: %d%%. 当前电量: %d%%.)<br>' +
               u'经过时间: %s' + u'&nbsp;' * 8 + u'剩余时间: %s')
  values = (target, start, current, FormatTime(elapsed), FormatTime(remaining))
  return test_ui.MakeLabel(_LABEL_EN % values, _LABEL_ZH % values)

def MakeSpriteHTMLTag(src, height, width):
  return (('<div id="batteryIcon" style="background-image: url(%s);' +
          'width: %dpx; height: %dpx; margin:auto;"></div>') %
          (src, width, height))

class ChargerTest(unittest.TestCase):
  ARGS = [
      Arg('target_charge_pct', int, 'Target charge level',
          default=78),
      Arg('timeout_secs', int, 'Maximum allowed time to charge battery',
          default=3600),
      ]

  def setUp(self):
    self._board = system.GetBoard()
    self._power = self._board.power
    self._ui = test_ui.UI()
    self._template = ui_templates.TwoSections(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._thread = threading.Thread(target=self._ui.Run)

  def CheckPower(self):
    self.assertTrue(self._power.CheckBatteryPresent(), 'Cannot find battery.')
    self.assertTrue(self._power.CheckACPresent(), 'Cannot find AC power.')

  def Charge(self):
    start_charge = self._power.GetChargePct()
    self.assertTrue(start_charge, 'Error getting battery state.')
    if start_charge >= self.args.target_charge_pct:
      return
    self._board.SetChargeState(Board.ChargeState.CHARGE)
    self._template.SetState(MakeSpriteHTMLTag('charging_sprite.png', 256, 256))
    logging.info('Charging starting at %d%%', start_charge)

    for elapsed in xrange(self.args.timeout_secs):
      charge = self._power.GetChargePct()
      if charge >= self.args.target_charge_pct:
        Log('charged', charge=charge, target=self.args.target_charge_pct,
            elapsed=elapsed)
        return
      self._ui.RunJS('$("batteryIcon").style.backgroundPosition = "-%dpx 0px"' %
                     ((elapsed % 4) * 256))
      self._template.SetInstruction(MakeChargeTextLabel(
                                      start_charge,
                                      charge,
                                      self.args.target_charge_pct,
                                      elapsed,
                                      self.args.timeout_secs - elapsed))
      if elapsed % 300 == 0:
        logging.info('Battery level is %d%% after %d minutes',
                     charge,
                     elapsed / 60)
      time.sleep(1)

    Log('failed_to_charge', charge=charge, target=self.args.target_charge_pct,
        timeout_sec=self.args.timeout_secs)
    self.fail('Cannot charge battery to %d%% in %d seconds.' %
              (self.args.target_charge_pct, self.args.timeout_secs))

  def runTest(self):
    self._thread.start()
    try:
      self.CheckPower()
      self.Charge()
    except Exception, e:
      self._ui.Fail(str(e))
      raise
    else:
      self._ui.Pass()

  def tearDown(self):
    self._thread.join()
