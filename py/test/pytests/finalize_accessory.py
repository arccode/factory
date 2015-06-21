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
      Arg('final_test_result_key', str,
          'the final test result key',
          default=''),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self._template = ui_templates.OneSection(self.ui)
    self._state = factory.get_state_instance()
    self.test_states_path = os.path.join(factory.get_log_root(), 'test_states')

  def _GetFinalTestResult(self):
    def _IsWaived(path):
      for re_path in waive_tests:
        if re_path.match(path):
          return True
      return False

    # The root (test list, path='') and this test itself should be skipped.
    skip_path = ['', self.test_info.path]
    waive_tests = map(re.compile, self.args.waive_tests)
    passed_states = set([factory.TestState.PASSED,
                         factory.TestState.FAILED_AND_WAIVED,
                         factory.TestState.ACTIVE])
    test_states = self._state.get_test_states()
    factory.console.debug('states: %s', test_states)
    failed_results = [(path, s.status) for path, s in test_states.iteritems()
                      if (s.status not in passed_states and
                          path not in skip_path and
                          not _IsWaived(path))]
    if failed_results:
      factory.console.info('failed_results:')
      for path, status in failed_results:
        factory.console.info('  %s: %s', path, status)
    else:
      factory.console.info('All tests passed!')
    Log('failed_results', failed_results=failed_results)

    # The 'FAIL' and 'PASS' are defined explicitly for partner's shopfloor,
    # different from TestState.
    final_test_result = 'FAIL' if failed_results else 'PASS'
    factory.set_shared_data(self.args.final_test_result_key, final_test_result)
    self.ui.Pass()

  def runTest(self):
    self._template.SetState(_MSG_GET_TEST_RESULT)
    if self.args.get_final_result:
      self._GetFinalTestResult()
    self.ui.Run()
