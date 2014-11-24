#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Displays a status summary for all tests in the current section.

The summary includes tests up to, but not including, this test).

For example, if the test tree is

SMT
  ...
Runin
  A
  B
  C
  report (this test)
  shutdown

...then this test will show the status summary for A, B, and C.

dargs:
  disable_input_on_fail: Disable user input to pass/fail when
    the overall status is not PASSED. If this argument is True and overall
    status is PASSED, user can pass the test by clicking the item or hitting
    space. If this argument is True and overall status is not PASSED,
    the test will hang there while the control menu can still work to
    stop/abort the test.
"""

import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test.fixture import bft_fixture

CSS = """
table {
  margin-left: auto;
  margin-right: auto;
  padding-bottom: 1em;
}
th, td {
  padding: 0 1em;
}
"""

class Report(unittest.TestCase):
  """A factory test to report test status."""
  ARGS = [
    Arg('disable_input_on_fail', bool,
        'Disable user input to pass/fail when the overall status is not PASSED',
        default=False),
    Arg('pass_without_prompt', bool,
        'If all tests passed, pass this test without prompting',
        default=False, optional=True),
    Arg('bft_fixture', dict,
        ('BFT fixture arguments (see bft_fixture test).  If provided, then a '
         'red/green light is lit to indicate failure/success rather than '
         'showing the summary on-screen.  The test does not fail if unable '
         'to connect to the BFT fixture.'),
        optional=True),
    Arg('accessibility', bool,
        'Display bright red background when the overall status is not PASSED',
        default=False, optional=True),
    ]

  def _SetFixtureStatusLight(self, all_pass):
    try:
      fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)
      fixture.SetStatusColor(
          fixture.StatusColor.GREEN
          if all_pass
          else fixture.StatusColor.RED)
      fixture.Disconnect()
    except bft_fixture.BFTFixtureException:
      logging.exception('Unable to set status color on BFT fixture')

  def runTest(self):
    test_list = self.test_info.ReadTestList()
    test = test_list.lookup_path(self.test_info.path)
    states = factory.get_state_instance().get_test_states()

    ui = test_ui.UI(css=CSS)

    statuses = []

    table = []
    for t in test.parent.subtests:
      if t == test:
        break

      state = states.get(t.path)

      table.append('<tr class="test-status-%s"><th>%s</th><td>%s</td></tr>'
                   % (state.status.replace('_', '-'),
                      test_ui.MakeTestLabel(t),
                      test_ui.MakeStatusLabel(state.status)))
      statuses.append(state.status)

    overall_status = factory.overall_status(statuses)
    all_pass = overall_status in (factory.TestState.PASSED,
                                  factory.TestState.FAILED_AND_WAIVED)

    if self.args.bft_fixture:
      self._SetFixtureStatusLight(all_pass)

    if (all_pass and self.args.pass_without_prompt):
      return

    html = [
        '<div class="test-vcenter-outer"><div class="test-vcenter-inner">',
        test_ui.MakeLabel('Test Status for %s:' % test.parent.path,
                          u'%s 测试结果列表：' % test.parent.path),
        '<div class="test-status-%s" style="font-size: 300%%">%s</div>' % (
            overall_status, test_ui.MakeStatusLabel(overall_status)),
        '<table>'] + table + ['</table>']
    if (not self.args.disable_input_on_fail or all_pass):
      html = html + ['<a onclick="onclick:window.test.pass()" href="#">',
                     test_ui.MakeLabel('Click or press SPACE to continue',
                                       u'点击或按空白键继续'),
                     '</a>']
    else:
      html = html + [test_ui.MakeLabel(
          'Unable to proceed, since some previous tests have not passed.',
          u'之前所有的测试必须通过才能通过此项目')]
    html = html + ['</div></div>']

    if self.args.accessibility and not all_pass:
      html = ['<div class="test-vcenter-accessibility">'] + html + ['</div>']

    if not self.args.disable_input_on_fail:
      ui.EnablePassFailKeys()
    # If disable_input_on_fail is True, and overall status is PASSED, user
    # can only pass the test.
    elif all_pass:
      ui.BindStandardKeys(bind_fail_keys=False)

    ui.SetHTML(''.join(html))
    logging.info('starting ui.Run with overall_status %r', overall_status)
    ui.Run()
