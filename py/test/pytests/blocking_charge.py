# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""This is a factory test that only pass when battery is charged to specific
level.
"""

import logging
import threading
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import event_log
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg

_TEST_TITLE = i18n_test_ui.MakeI18nLabel('Charging')


def FormatTime(seconds):
  return '%d:%02d:%02d' % (seconds / 3600, (seconds / 60) % 60, seconds % 60)


def MakeChargeTextLabel(start, current, target, elapsed, remaining):
  return i18n_test_ui.MakeI18nLabel(
      'Charging to {target}% (Start: {start}%. Current: {current}%.)<br>'
      'Time elapsed: {elapsed}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
      'Time remaining: {remaining}',
      target=target, start=start, current=current,
      elapsed=FormatTime(elapsed), remaining=FormatTime(remaining))


def MakeSpriteHTMLTag(src, height, width):
  return (('<div id="batteryIcon" style="background-image: url(%s);' +
           'width: %dpx; height: %dpx; margin:auto;"></div>') %
          (src, width, height))


class ChargerTest(unittest.TestCase):
  ARGS = [
      Arg('target_charge_pct', int, 'Target charge level',
          default=78),
      Arg('target_charge_pct_is_delta', bool,
          'Specify target_charge_pct is a delta of current charge',
          default=False),
      Arg('timeout_secs', int, 'Maximum allowed time to charge battery',
          default=3600),
  ]

  def setUp(self):
    self._power = device_utils.CreateDUTInterface().power
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
    target_charge = self.args.target_charge_pct
    if self.args.target_charge_pct_is_delta is True:
      target_charge = min(target_charge + start_charge, 100)
    if start_charge >= target_charge:
      return
    self._power.SetChargeState(self._power.ChargeState.CHARGE)
    self._template.SetState(MakeSpriteHTMLTag('charging_sprite.png', 256, 256))
    logging.info('Charging starting at %d%%', start_charge)

    for elapsed in xrange(self.args.timeout_secs):
      charge = self._power.GetChargePct()

      if charge >= target_charge:
        event_log.Log('charged', charge=charge, target=target_charge,
                      elapsed=elapsed)
        return
      self._ui.RunJS('$("batteryIcon").style.backgroundPosition = "-%dpx 0px"' %
                     ((elapsed % 4) * 256))
      self._template.SetInstruction(MakeChargeTextLabel(
          start_charge,
          charge,
          target_charge,
          elapsed,
          self.args.timeout_secs - elapsed))
      if elapsed % 300 == 0:
        logging.info('Battery level is %d%% after %d minutes',
                     charge,
                     elapsed / 60)
      time.sleep(1)

    event_log.Log('failed_to_charge', charge=charge, target=target_charge,
                  timeout_sec=self.args.timeout_secs)
    self.fail('Cannot charge battery to %d%% in %d seconds.' %
              (target_charge, self.args.timeout_secs))

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
