# -*- coding: utf-8 -*-
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The finalize test is used to collect the test results for accessories."""


import os
import re
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.event_log import Log
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.env import paths
from cros.factory.test.test_ui import MakeLabel


_MSG_GET_TEST_RESULT = MakeLabel('Get the final test result...',
                                 '检查系统最终测试结果...')


class FinalizeAccessory(unittest.TestCase):
  """The main class for finalize accessory pytest."""
  ARGS = [
      Arg('get_final_result', bool,
          'Get the final test result"',
          default=False),
      Arg('waive_tests', list,
          'the waved tests',
          default=[]),
      Arg('specified_group', str,
          'If specified, only test results in this group are collected.',
          optional=True),
      Arg('final_test_result_key', str,
          'the final test result key',
          default=''),
      Arg('failed_reasons_key', str,
          'the failed-reasons key',
          default=''),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self._template = ui_templates.OneSection(self.ui)
    self._state = factory.get_state_instance()
    self.test_states_path = os.path.join(paths.get_log_root(), 'test_states')

  def _GetFinalTestResult(self):
    def _IsWaived(path):
      # Skips the root and this test itself.
      if path in skip_paths:
        return True
      # Skips tests which match skip_patterns.
      for re_path in skip_patterns:
        if re_path.match(path):
          return True
      # For specified group, skips the root of group and tests not belonged to
      # the group.
      if (self.args.specified_group and
          (path == self.args.specified_group or
           not path.startswith(self.args.specified_group))):
        return True
      return False

    # The root (test list, path='') and this test itself should be skipped.
    skip_paths = ['', self.test_info.path]
    skip_patterns = map(re.compile, self.args.waive_tests)
    passed_states = set([factory.TestState.PASSED,
                         factory.TestState.FAILED_AND_WAIVED,
                         factory.TestState.ACTIVE])
    test_states = self._state.get_test_states()
    factory.console.debug('states: %s', test_states)
    failed_results = dict([(path, (s.status, s.error_msg))
                           for path, s in test_states.iteritems()
                           if (s.status not in passed_states and
                               not _IsWaived(path))])

    if failed_results:
      # The 'FAIL' is defined explicitly for partner's shopfloor.
      final_test_result = 'FAIL'
      factory.console.info('failed_results:')
      for path, (status, error_msg) in failed_results.iteritems():
        factory.console.info('%s: %s (error_msg: %s)', path, status, error_msg)
    else:
      # The 'PASS' is defined explicitly for partner's shopfloor.
      final_test_result = 'PASS'
      factory.console.info('All tests passed!')
    Log('failed_results', failed_results=failed_results)

    factory.set_shared_data(self.args.final_test_result_key, final_test_result)
    failed_msgs_dict = dict([(path, error_msg) for path, (status, error_msg) in
                             failed_results.iteritems()])
    factory.set_shared_data(self.args.failed_reasons_key, failed_msgs_dict)
    self.ui.Pass()

  def runTest(self):
    self._template.SetState(_MSG_GET_TEST_RESULT)
    if self.args.get_final_result:
      self._GetFinalTestResult()
    self.ui.Run()
