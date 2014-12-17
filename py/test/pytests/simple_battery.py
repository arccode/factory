# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A simple battery test.

A simple battery test that charges, discharges, and charges a battery on a
DUT.  The goal of this factory test is to do a quick basic verification of
battery function (typically less than 30 seconds).
"""

from __future__ import print_function

import logging
import time
import unittest

import factory_common   # pylint: disable=W0611
from cros.factory import system
from cros.factory.system import power
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.args import Arg
from cros.factory.utils import sync_utils
from cros.factory.utils import time_utils


_TEST_TITLE = test_ui.MakeLabel('Simple Battery Test', u'简单电池测试')
_UNPLUG_AC = test_ui.MakeLabel('Unplug AC to proceed', u'拔除 AC 电源')
_PLUG_AC = test_ui.MakeLabel('Plug AC to proceed', u'插上 AC 电源')
_TESTING_CHARGE = test_ui.MakeLabel('Testing battery charge...',
                                    u'测试电池充电中...')
_TESTING_DISCHARGE = test_ui.MakeLabel('Testing battery discharge...',
                                       u'测试电池放电中...')
_CSS = 'body { font-size: 2em; }'


class SimpleBatteryTest(unittest.TestCase):
  """A simple battery test."""
  ARGS = [
      Arg('charge_duration_secs', type=(int, float), default=5,
          help='the duration in seconds to charge the battery'),
      Arg('discharge_duration_secs', type=(int, float), default=5,
          help='the duration in seconds to discharge the battery'),
      Arg('min_charge_current_mA', type=(int, float), default=None,
          optional=True,
          help=('the minimum charge current in mA that the battery needs to '
                'reach during charge test')),
      Arg('min_discharge_current_mA', type=(int, float), default=-2000,
          help=('the minimum discharge current in mA that the battery needs to '
                'reach during discharge test')),
      Arg('current_sampling_period_secs', type=(int, float), default=0.5,
          help=('the period in seconds to sample charge/discharge current '
                'during test')),
      Arg('max_cycle_count', type=int, default=1,
          help=('the maximum cycle count beyond which the battery is considered'
                'used')),
  ]

  def setUp(self):
    self.VerifyArgs()
    self._ui = test_ui.UI(css=_CSS)
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._board = system.GetBoard()
    self._power = power.Power()

  def VerifyArgs(self):
    if self.args.min_charge_current_mA:
      if not self.args.min_charge_current_mA > 0:
        raise factory.FactoryTestFailure(
            'min_charge_current_mA must be greater than zero')
    if self.args.min_discharge_current_mA:
      if not self.args.min_discharge_current_mA < 0:
        raise factory.FactoryTestFailure(
            'min_discharge_current_mA must be less than zero')

  def SampleBatteryCurrent(self, duration_secs):
    """Samples battery current for a given duration.

    Args:
      duration_secs: The duration in seconds to sample battery current.

    Returns:
      A list of sampled battery current.
    """
    sampled_current = []
    end_time = time_utils.MonotonicTime() + duration_secs
    while time_utils.MonotonicTime() < end_time:
      sampled_current.append(self._board.GetBatteryCurrent())
      time.sleep(self.args.current_sampling_period_secs)
    logging.info('Sampled battery current: %s', str(sampled_current))
    return sampled_current

  def TestCharge(self, duration_secs):
    """Tests battery charging for a given duration.

    Args:
      duration_secs: The duration in seconds to test charging the battery.

    Raises:
      FactoryTestFailure if the sampled battery charge current does not pass
      the given threshold in dargs.
    """
    self._template.SetState(_PLUG_AC)
    sync_utils.WaitFor(self._board.CheckACPresent, timeout_secs=10)
    self._template.SetState(_TESTING_CHARGE)
    sampled_current = self.SampleBatteryCurrent(duration_secs)
    if self.args.min_charge_current_mA:
      if not any(
          [c > self.args.min_charge_current_mA for c in sampled_current]):
        raise factory.FactoryTestFailure(
            'Battery charge current did not reach defined threshold %f mA' %
            self.args.min_charge_current_mA)
    else:
      if not any([c > 0 for c in sampled_current]):
        raise factory.FactoryTestFailure(
            'Battery was not charging during charge test')

  def TestDischarge(self, duration_secs):
    """Tests battery discharging for a given duration.

    The test runs under high system load to maximize battery discharge current.

    Args:
      duration_secs: The duration in seconds to test discharging the battery.

    Raises:
      FactoryTestFailure if the sampled battery discharge current does not pass
      the given threshold in dargs.
    """
    self._template.SetState(_UNPLUG_AC)
    sync_utils.WaitFor(lambda: not self._board.CheckACPresent(),
        timeout_secs=10)
    self._template.SetState(_TESTING_DISCHARGE)
    # Discharge under high system load.
    with utils.LoadManager(duration_secs):
      sampled_current = self.SampleBatteryCurrent(duration_secs)
    if self.args.min_discharge_current_mA:
      if not any(
          [c < self.args.min_discharge_current_mA for c in sampled_current]):
        raise factory.FactoryTestFailure(
            'Battery discharge current did not reach defined threshold %f mA' %
            self.args.min_discharge_current_mA)
    else:
      if not any([c < 0 for c in sampled_current]):
        raise factory.FactoryTestFailure(
            'Battery was not discharging during charge test')

  def runTest(self):
    if not self._power.CheckBatteryPresent():
      raise factory.FactoryTestFailure(
          'Cannot locate battery sysfs path. Missing battery?')
    cycle_count = self._power.GetBatteryAttribute('cycle_count').strip()
    if (int(cycle_count) > self.args.max_cycle_count):
      raise factory.FactoryTestFailure(
          'Battery cycle count %s exceeds max %d' %
          (cycle_count, self.args.max_cycle_count))
    self.TestCharge(self.args.charge_duration_secs)
    self.TestDischarge(self.args.discharge_duration_secs)
    self.TestCharge(self.args.charge_duration_secs)
