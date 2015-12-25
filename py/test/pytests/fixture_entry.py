#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Starts or ends a fixture-based testing.

This factory test invoke functions to setup or teardown a fixture-based
testlist.
"""

import unittest

import factory_common # pylint: disable=W0611

from cros.factory.test import dut
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.utils import sync_utils


_CSS = """
.prompt {
  font-size: 2em;
}

.warning {
  color: red;
}
"""

_TITLE_START = test_ui.MakeLabel('Start Fixture Test', u'开始治具测试')
_TITLE_END = test_ui.MakeLabel('End Fixture Test', u'结束治具测试')

_MSG_INSERT = test_ui.MakeLabel(
    'Please attach DUT.',
    u'INSERT 请插入测试装置。',
    'prompt')

_MSG_SEND_RESULT = test_ui.MakeLabel(
    'Sending test results to shopfloor...',
    u'SENDING 传送测试结果给服务器...',
    'prompt')

_MSG_REMOVE_DUT = test_ui.MakeLabel(
    'Please remove DUT.',
    u'REMOVE 请移除测试装置。',
    'prompt')

_MSG_RESTART_TESTS = test_ui.MakeLabel(
    'Restarting all tests...',
    u'RESTARTING 测试结束，正在重设测试列表...',
    'prompt')

class FixtureEntry(unittest.TestCase):
  """The factory test to start fixture test process."""
  ARGS = [
      Arg('start_fixture_tests', bool,
          'To start or stop the factory fixture tests.', default=True,
          optional=True),
  ]

  def setUp(self):
    self._dut = dut.Create()
    self._state = factory.get_state_instance()
    self._ui = test_ui.UI()
    self._ui.AppendCSS(_CSS)
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TITLE_START if self.args.start_fixture_tests else
                            _TITLE_END)

  def RestartAllTests(self):
    self._state.ScheduleRestart()

  def SendTestResult(self):
    # TODO(stimim): send test result to shopfloor
    pass

  def runTest(self):
    self._ui.Run(blocking=False)

    if self.args.start_fixture_tests:
      self._template.SetState(_MSG_INSERT)
      sync_utils.WaitFor(self._dut.link.IsReady, None)
    else:
      self._template.SetState(_MSG_SEND_RESULT)
      self.SendTestResult()

      self._template.SetState(_MSG_REMOVE_DUT)
      sync_utils.WaitFor(lambda: not self._dut.link.IsReady(), None)

      self._template.SetState(_MSG_RESTART_TESTS)
      self.RestartAllTests()
