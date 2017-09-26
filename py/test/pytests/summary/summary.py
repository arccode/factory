# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Displays a status summary for all tests in the current section.

Description
-----------
This is a test to display a summary of test results in same test group.
The summary includes tests up to, but not including, this test itself.

For example, if the test tree is::

 SMT
   ...
 Runin
   A
   B
   C
   report (this test)
   shutdown

Then this test will show the status summary for A, B, and C. No shutdown.

This test is often used as a "barrier" or "check point" when the argument
``disable_input_on_fail`` is set, since operators can't skip to next test item
when the overall status is not PASSED.

Moreover, if argument ``pass_without_prompt`` is ``True``, the test will pass
silently and move to next test item without user interaction. This is usually
known as "Barrier" mode. Otherwise, it'll prompt the given message and wait for
input, which is known as "Check Point" mode.

Test Procedure
--------------
1. If all previous tests in same group are passed, this test will display
   nothing and simply pass when argument ``pass_without_prompt`` is True,
   otherwise display a table of test names and results, prompt the given (or
   default) message and wait for input to pass or fail.
2. Otherwise, if any previous tests in same group failed, a table listing test
   names and results will be displayed. Depends on argument
   ``disable_input_on_fail``, operator may choose to continue or will stay in
   failure screen.

Dependency
----------
None.

Examples
--------
To list previous tests in same group, and always prompt and wait for input to
decide if we can move on::

  OperatorTest(pytest_name='summary')

To only stop when any previous tests in same group has failed ("Barrier")::

  OperatorTest(pytest_name='summary',
               disable_abort=True,
               never_fails=True,
               dargs={
                   'disable_input_on_fail': True,
                   'pass_without_prompt': True,
               })

To always prompt but only pass if all previous tests in same group passed
("Check Point")::

  OperatorTest(pytest_name='summary',
               disable_abort=True,
               never_fails=True,
               dargs={
                   'disable_input_on_fail': True,
                   'pass_without_prompt': False,
                   'prompt_message': _('Press space to shutdown.'),
               })
"""

import itertools
import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import state
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg

CSS = """
#test-status-table-container {
  overflow: auto;
}

#state.test-accessibility {
  background-color: #F77;
}

table {
  padding-bottom: 1em;
}

th, td {
  padding: 0 1em;
}

.prompt_message {
  font-size: 2em;
}
"""

_EXTERNAL_DIR = '/run/factory/external'

# The following test states are considered passed
_EXTENED_PASSED_STATE = {
    factory.TestState.PASSED,
    factory.TestState.FAILED_AND_WAIVED,
    factory.TestState.SKIPPED, }


class Report(unittest.TestCase):
  """A factory test to report test status."""
  ARGS = [
      i18n_arg_utils.I18nArg(
          'prompt_message', 'Prompt message in HTML when all tests passed',
          default=_('Click or press SPACE to continue')),
      Arg('disable_input_on_fail', bool,
          ('Disable user input to pass/fail when the overall status is not '
           'PASSED'),
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
      Arg('include_parents', bool,
          'Recursively include parent groups in summary',
          default=False),
      Arg('run_factory_external_name', str,
          'Notify DUT that external test is over, will use DUT interface to '
          'write result file under /run/factory/external/<NAME>.',
          default=None, optional=True),
  ]

  def _SetFixtureStatusLight(self, all_pass):
    try:
      fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)
      fixture.SetStatusColor(
          fixture.StatusColor.GREEN if all_pass else fixture.StatusColor.RED)
      fixture.Disconnect()
    except bft_fixture.BFTFixtureException:
      logging.exception('Unable to set status color on BFT fixture')

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    i18n_arg_utils.ParseArg(self, 'prompt_message')
    ui = test_ui.UI(css=CSS)
    template = ui_templates.OneSection(ui)

    test_list = self.test_info.ReadTestList()
    test = test_list.LookupPath(self.test_info.path)
    states = state.get_instance().get_test_states()

    previous_tests = []
    current = test
    root = test.root if self.args.include_parents else test.parent
    while current != root:
      previous_tests = list(itertools.takewhile(
          lambda t: t != current, current.parent.subtests)) + previous_tests
      current = current.parent

    # Try to render a table and collect statuses.
    table = []
    statuses = []
    for t in previous_tests:
      test_state = states.get(t.path)
      table.append('<tr class="test-status-%s"><th>%s</th><td>%s</td></tr>'
                   % (test_state.status.replace('_', '-'),
                      test_ui.MakeTestLabel(t),
                      test_ui.MakeStatusLabel(test_state.status)))
      statuses.append(test_state.status)

    overall_status = factory.overall_status(statuses)
    all_pass = overall_status in _EXTENED_PASSED_STATE

    goofy = state.get_instance()
    goofy.PostHookEvent('Summary', 'Good' if all_pass else 'Bad')

    if self.args.bft_fixture:
      self._SetFixtureStatusLight(all_pass)

    if self.args.run_factory_external_name:
      self.dut.CheckCall(['mkdir', '-p', _EXTERNAL_DIR])
      file_path = self.dut.path.join(_EXTERNAL_DIR,
                                     self.args.run_factory_external_name)
      if all_pass:
        self.dut.WriteFile(file_path, 'PASS')
      else:
        report = ''.join(
            '%s: %s\n' % (t.path, status) for t, status in
            zip(previous_tests, statuses))
        self.dut.WriteFile(file_path, report)

    if all_pass and self.args.pass_without_prompt:
      return

    html = []
    prompt_class = 'prompt_message'

    if not self.args.disable_input_on_fail or all_pass:
      html = html + [
          '<a onclick="onclick:window.test.pass()" href="#">',
          i18n_test_ui.MakeI18nLabelWithClass(
              self.args.prompt_message, prompt_class),
          '</a>'
      ]
    else:
      html = html + [
          i18n_test_ui.MakeI18nLabelWithClass(
              'Unable to proceed, since some previous tests have not passed.',
              prompt_class)
      ]

    html = html + [
        '<br>',
        i18n_test_ui.MakeI18nLabel(
            'Test Status for {test}:', test=test.parent.path),
        '<div class="test-status-%s" style="font-size: 3em">%s</div>' %
        (overall_status, test_ui.MakeStatusLabel(overall_status)),
        '<div id="test-status-table-container"><table>'
    ] + table + ['</table></div>']


    if not self.args.disable_input_on_fail:
      ui.EnablePassFailKeys()
    # If disable_input_on_fail is True, and overall status is PASSED, user
    # can only pass the test.
    elif all_pass:
      ui.BindStandardKeys(bind_fail_keys=False)

    template.SetState(''.join(html))
    if self.args.accessibility and not all_pass:
      ui.RunJS(
          'document.getElementById("%s").classList.add("test-accessibility")' %
          ui_templates.STATE_ID)
    logging.info('starting ui.Run with overall_status %r', overall_status)
    ui.Run()
