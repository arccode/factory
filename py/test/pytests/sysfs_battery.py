# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A hardware test for checking battery existence.

This checks the existence and status of battery in sysfs.
"""

import threading
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import Log
from cros.factory.test.args import Arg
from cros.factory.test.test_ui import MakeLabel, UI
from cros.factory.test.ui_templates import OneScrollableSection
from cros.factory import system

_TEST_TITLE = MakeLabel('Battery Self-diagnosis', u'电池自我诊断')
_CSS = '#state {text-align:left;}'

class SysfsBatteryTest(unittest.TestCase):
  """Checks battery status."""
  ARGS = [
    Arg('maximum_cycle_count', int,
        'Maximum cycle count allowed to pass test', optional=True,
        default=None),
    Arg('percent_battery_wear_allowed', int,
        'Maximum pecent battery wear allowed to pass test', default=100),
    Arg('verify_battery_health_good', bool,
        'Boolean to verify that the battery health value is good',
        default=False),
  ]

  def setUp(self):
    self._ui = UI()
    self._template = OneScrollableSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._ui.AppendCSS(_CSS)

  def DiagnoseBattery(self):
    success = False
    wearAllowedPct = self.args.percent_battery_wear_allowed
    wearPct = None

    power = system.GetBoard().power
    battery_present = power.CheckBatteryPresent()
    if not battery_present:
      msg = 'Cannot find battery path'
    elif power.GetChargePct() is None:
      msg = 'Cannot get charge percentage'
    elif wearAllowedPct < 100:
      wearPct = power.GetWearPct()
      if wearPct is None:
        msg = 'Cannot get wear percentage'
      elif wearPct > wearAllowedPct:
        msg = 'Battery is over-worn: %d%%' % wearPct
      else:
        success = True
    else:
      success = True

    if battery_present:
      health = power.GetBatteryAttribute('health')
      if success and self.args.verify_battery_health_good:
        if health is None or health.lower() != 'good':
          msg = 'Battery health is %s, not Good' % health
          success = False

      cycleCount = power.GetBatteryAttribute('cycle_count')
      if success and self.args.maximum_cycle_count is not None:
        if int(cycleCount) > self.args.maximum_cycle_count:
          msg = 'Battery cycle count is too high: %s' % cycleCount
          success = False

      capacity = power.GetBatteryAttribute('capacity')
      manufacturer = power.GetBatteryAttribute('manufacturer')
      temp = power.GetBatteryAttribute('temp')

      Log('battery_checked', wearPct=wearPct, allowed=wearAllowedPct,
          health=health, cycleCount=cycleCount, capacity=capacity,
          manufacturer=manufacturer, temp=temp, success=success)

    if success:
      self._ui.Pass()
    else:
      self._ui.Fail('Battery self-diagnose failed: %s.' % msg)

  def runTest(self):
    threading.Thread(target=self.DiagnoseBattery).start()
    self._ui.Run()
