# -*- coding: utf-8 -*-
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
      label_zh=u'Probe',
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
      ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self.factory_tools = deploy_utils.FactoryPythonArchive(self._dut)
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

    # Check every category meets the rule.
    success = True
    for category in probed_results:
      count = sum(len(comps) for comps in probed_results[category].values())
      op_str, value = rule_map[category]
      if not OPERATOR_MAP[op_str](count, value):
        factory.console.error('Category "%s" does not meet rule: %s %s %s',
                              category, count, op_str, value)
        success = False
    if not success:
      self.fail()
