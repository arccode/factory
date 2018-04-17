# -*- mode: python; coding: utf-8 -*-
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Checks voltages."""

import logging
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import ui_templates
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg


_CSS = """.warn {
  color:white;
  background-color:red;
}"""


def _StateId(key):
  return '%s_state' % key


def _ValueId(key):
  return '%s_value' % key


class WhaleCheckVoltageTest(test_case.TestCase):
  """Checks voltages."""
  ARGS = [
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP),
      Arg('criteria', dict,
          'Criteria of measured voltage. A dict '
          '{ina_name: (schematic_name, expected_voltage, relative_tolerance)} '
          'where the unit of voltage is mV'),
      Arg('timeout_secs', (int, float),
          'Total #seconds to perform voltage checking', default=10),
      Arg('poll_interval_secs', (int, float), 'Pause between voltage check',
          default=0.3),
  ]

  def CheckVoltage(self, index):
    all_pass = True
    power_rail = self._bft.CheckPowerRail()
    self._power_rail_str = ', '.join(
        '%s: %d' % kv for kv in sorted(power_rail.items()))
    logging.debug('Measured power rail (mV): ' + self._power_rail_str)

    # log the value by testlog
    for key, unused_criteria in self._sorted_criteria:
      measured = power_rail.get(key, 0)
      self._testlog_voltage_series[key].LogValue(key=index, value=measured)

    self._errors = []
    for key, (display_name, expected, tolerance) in self._sorted_criteria:
      measured = power_rail.get(key, 0)

      if expected is None:
        state = 'ignored'
      elif abs(measured - expected) * 100 > tolerance * expected:
        all_pass = False
        self._errors.append(
            '%s: %d (expect %d +- %d%%)' % (display_name,
                                            measured,
                                            expected,
                                            tolerance))
        logging.info(
            'Unexpected voltage on %s: expected %d mV, actual %d mV',
            display_name, expected, measured)
        state = 'failed'
      else:
        state = 'passed'

      self.ui.SetHTML(
          '<div class=test-status-{0}>{1}</div>'.format(state, measured),
          id=_ValueId(key))
      self.ui.SetHTML(
          '<div class=test-status-{0}>{0}</div>'.format(state),
          id=_StateId(key))

    return all_pass

  def setUp(self):
    self._bft = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)
    self._sorted_criteria = sorted(self.args.criteria.items())

    self._power_rail_str = None
    self._errors = []

    self._testlog_voltage_series = {}
    for key, unused_criteria in self._sorted_criteria:
      self._testlog_voltage_series[key] = testlog.CreateSeries(
          name=key,
          description='Voltage value for %s over time' % key,
          key_unit='trial',
          value_unit='millivolt')

  def InitDashboard(self):
    table = ui_templates.Table(element_id='dashboard', cols=4,
                               rows=len(self._sorted_criteria) + 1)
    for c, title in enumerate(
        [_('Power rail'), _('voltage (mV)'), _('expected'), _('status')]):
      table.SetContent(0, c, title)

    for r, (key, (display_name, expected, tolerance)) in enumerate(
        self._sorted_criteria, 1):
      table.SetContent(r, 0, display_name)
      table.SetContent(r, 1, '<div id="%s"></div>' % _ValueId(key))
      if expected is None:
        table.SetContent(r, 2, 'N/A')
      else:
        table.SetContent(r, 2, '%d &plusmn; %d%%' % (expected, tolerance))
      table.SetContent(r, 3, '<div id="%s"></div>' % _StateId(key))
    self.ui.SetState([table.GenerateHTML()])

  def runTest(self):
    self.InitDashboard()

    now = time.time()
    end_time = now + self.args.timeout_secs
    index = 0
    while now < end_time:
      test_pass = self.CheckVoltage(index)
      index += 1
      if test_pass:
        break
      time.sleep(self.args.poll_interval_secs)
      now = time.time()

    if not test_pass:
      self.fail()
