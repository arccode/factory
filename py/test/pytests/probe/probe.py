# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests if the components can be probed successfully or not.

This pytest uses probe module to probe the components, and verifies the
component count of each category. The default rule is the count should be equal
to 1. If the required count is not 1, we can set the rule in "overridden_rules"
argument. For example::

  FactoryTest(
      id='Probe',
      label=_('Probe'),
      pytest_name='probe',
      dargs={
          'config_file': 'probe_rule.json',
          'overridden_rules': [
              ('usb', '==', 2),         # There shoule be 2 USB components.
              ('lte', 'in', [1, 2])]})  # There should be 1 or 2 LTE components.

The format of the config file::

  {
    <Component category> : {
      <Component name> : {
        "eval" : <Function expression>,
        "expect" : <Rule expression>
      }
    }
  }

Please refer to `py/probe/probe_cmdline.py` for more details.
"""

import collections
import json
import operator
import os
import unittest

import factory_common  # pylint: disable=unused-import

from cros.factory.device import device_utils
from cros.factory.test.args import Arg
from cros.factory.test import factory
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import deploy_utils


# The config files should be placed in the py/test/pytests/probe/ folder.
LOCAL_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
OPERATOR_MAP = {
    '==': operator.eq,
    '!=': operator.ne,
    '<': operator.lt,
    '<=': operator.le,
    '>': operator.gt,
    '>=': operator.ge,
    'in': lambda a, b: a in b}

_CSS = """
table {
  border-collapse: collapse;
  margin-left: auto;
  margin-right: auto;
  padding-bottom: 1em;
}
th, td {
  border: 1px solid #dddddd;
  text-align: left;
  padding: 0 1em;
}
.prompt {
  font-size: 2em;
}
"""

def EvaluateRule(a, op_str, b):
  return OPERATOR_MAP[op_str](a, b)


class ProbeTest(unittest.TestCase):

  ARGS = [
      Arg('config_file', str,
          'Path to probe config file. This is interpreted as a path '
          'relative to `test/pytests/probe` folder.',
          optional=False),
      Arg('overridden_rules', list,
          'List of (category, cmp_function, value) tuple.',
          default=None, optional=True),
      Arg('show_ui', bool,
          'Always show the result and prompt if set to True. Always not show '
          'the result and prompt if set to False. Otherwise, only show the '
          'result and prompt when the test fails.',
          default=None, optional=True),
      ]

  def setUp(self):
    self._ui = test_ui.UI(css=_CSS)
    self._template = ui_templates.OneScrollableSection(self._ui)

    self._dut = device_utils.CreateDUTInterface()
    self.factory_tools = deploy_utils.CreateFactoryTools(self._dut)
    self.config_file_path = os.path.join(
        LOCAL_CONFIG_DIR, self.args.config_file)

  def runTest(self):
    # Check the config file exists.
    if not os.path.exists(self.config_file_path):
      self.fail('Config file %s does not exist.' % self.config_file_path)

    # Execute Probe.
    cmd = ['probe', '-v', 'probe', self.config_file_path]
    factory.console.info('Call the command: %s', ' '.join(cmd))
    probed_results = json.loads(self.factory_tools.CheckOutput(cmd))

    # Generate the rules of each category.
    rule_map = collections.defaultdict(lambda: ('==', 1))
    if self.args.overridden_rules is not None:
      for category, op_str, value in self.args.overridden_rules:
        rule_map[category] = (op_str, value)

    table_html = ui_templates.Table(rows=len(probed_results) + 1, cols=4)
    title = ['Category', 'Probed Components', 'Rule', 'Status']
    for idx, content in enumerate(title):
      table_html.SetContent(0, idx, '<b>%s</b>' % content)

    # Check every category meets the rule.
    all_passed = True
    for row_idx, category in enumerate(probed_results, 1):
      count = sum(len(comps) for comps in probed_results[category].values())
      op_str, value = rule_map[category]
      status = OPERATOR_MAP[op_str](count, value)
      all_passed &= status

      # Set the table.
      summary = []
      for name, result in probed_results[category].iteritems():
        if len(result) > 0:
          summary.append('%s %s found.' % (len(result), name))
      summary_str = '<br>'.join(summary) if summary else 'No component found.'
      rule_str = 'count (%s) %s %s' % (count, op_str, value)
      status_str = 'passed' if status else 'failed'
      factory.console.info('Category "%s" %s %s, %s.',
                           category, summary_str, rule_str, status_str)
      table_html.SetContent(row_idx, 0, category)
      table_html.SetContent(row_idx, 1, summary_str)
      table_html.SetContent(row_idx, 2, rule_str)
      table_html.SetContent(
          row_idx, 3, '<div class=test-status-{0}>{0}</div>'.format(status_str))

    if self.args.show_ui is False:
      if all_passed is False:
        self.fail()
    elif self.args.show_ui is True or not all_passed:
      html = [
          table_html.GenerateHTML(), '<br>',
          i18n_test_ui.MakeI18nLabelWithClass(
              'Press SPACE to continue', 'prompt')
      ]
      self._template.SetState(''.join(html))
      self._ui.BindKeyJS(
          test_ui.SPACE_KEY,
          'window.test.pass()' if all_passed else 'window.test.fail()')
      self._ui.Run()
