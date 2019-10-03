# -*- mode: python; coding: utf-8 -*-
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Checks voltages."""

import logging
import time

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

  def CheckVoltage(self, elapsed):
    all_pass = True
    power_rail = self._bft.CheckPowerRail()
    self._power_rail_str = ', '.join(
        '%s: %d' % kv for kv in sorted(power_rail.items()))
    logging.debug('Measured power rail (mV): %s', self._power_rail_str)

    self._errors = []
    for key, (display_name, expected, tolerance) in self._sorted_criteria:
      measured = power_rail.get(key, 0)
      # log the value by testlog
      with self._group_checker:
        testlog.LogParam('ina_name', key)
        testlog.LogParam('elapsed', elapsed)
        if expected is None:
          testlog.LogParam('voltage', measured)
          state = 'ignored'
        else:
          if testlog.CheckNumericParam(
              'voltage', measured,
              min=expected - tolerance / 100. * expected,
              max=expected + tolerance / 100. * expected):
            state = 'passed'
          else:
            state = 'failed'
            all_pass = False
            self._errors.append(
                '%s: %d (expect %d +- %d%%)' % (
                    display_name, measured, expected, tolerance))
            logging.info(
                'Unexpected voltage on %s: expected %d mV, actual %d mV',
                display_name, expected, measured)

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

    self._group_checker = testlog.GroupParam(
        'voltage',
        ['ina_name', 'voltage', 'elapsed'])
    testlog.UpdateParam('ina_name', param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam(
        'voltage',
        description='Voltage value over time',
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

    start_time = time.time()
    elapsed = time.time() - start_time
    while elapsed < self.args.timeout_secs:
      test_pass = self.CheckVoltage(elapsed)
      if test_pass:
        break
      time.sleep(self.args.poll_interval_secs)
      elapsed = time.time() - start_time

    if not test_pass:
      self.fail()
