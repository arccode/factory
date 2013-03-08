# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A hardware test for checking battery existence.

This checks the existence of battery in sysfs.
"""

import threading
import unittest

from cros.factory.test.args import Arg
from cros.factory.test.test_ui import MakeLabel, UI
from cros.factory.test.ui_templates import OneScrollableSection
from cros.factory.system.power import Power

_TEST_TITLE = MakeLabel('Battery Self-diagnosis', u'电池自我诊断')
_CSS = '#state {text-align:left;}'

class SysfsBatteryTest(unittest.TestCase):
  ARGS = [
    Arg('percent_battery_wear_allowed', int,
        'Maximum pecent battery wear allowed to pass test', default=100)
  ]

  def setUp(self):
    self._ui = UI()
    self._template = OneScrollableSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._ui.AppendCSS(_CSS)

  def DiagnoseBattery(self):
    success = False
    wearAllowedPct = self.args.percent_battery_wear_allowed

    power = Power()
    if not power.CheckBatteryPresent():
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

    if success:
      self._ui.Pass()
    else:
      self._ui.Fail('Battery self-diagnose failed: %s.' % msg)

  def runTest(self):
    threading.Thread(target=self.DiagnoseBattery).start()
    self._ui.Run()
