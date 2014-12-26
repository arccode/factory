#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Verifies physical developer switch can be toggled and end in right state."""

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils

_MSG_TURN_ON = test_ui.MakeLabel(
    'Please turn <b class="on">ON</b> Developer Switch.',
    u'请<b class="on">开启</b> DEV SW 开发者开关。')

_MSG_TURN_OFF = test_ui.MakeLabel(
    'Please turn <b class="off">OFF</b> Developer Switch.',
    u'请<b class="off">关闭</b> DEV SW 开发者开关。')

_MSG_SW_ON = test_ui.MakeLabel(
    'Develop switch is currently <b class="on">ON</b>.',
    u'DEV SW 开发者开关目前为<b class="on">开启</b>状态')

_MSG_SW_OFF = test_ui.MakeLabel(
    'Develop switch is currently <b class="off">OFF</b>.',
    u'DEV SW 开发者开关目前为<b class="off">关闭</b>状态')

_TEST_PAGE_CSS = """
  .on {
    color: green;
  }
  .off {
    color: red;
  }
  """


class DeveloperSwitchTest(unittest.TestCase):
  ARGS = [
      Arg('end_state', bool,
          'The state when leaving test. True as enabled and False as disabled.',
          default=True),
      Arg('timeout_secs', int, 'Time out value in seconds.',
          default=(60 * 60))
  ]

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.TwoSections(self._ui)
    self._ui.AppendCSS(_TEST_PAGE_CSS)
    self._ui.Run(blocking=False)

  def runTest(self):

    def GetState():
      # This will be called so many times so we don't want to be logged.
      return int(process_utils.SpawnOutput(
          ['crossystem', 'devsw_cur'], log=False, check_output=True))

    def UpdateUI(state):
      if state:
        self._template.SetState(_MSG_TURN_OFF)
        self._template.SetInstruction(_MSG_SW_ON)
      else:
        self._template.SetState(_MSG_TURN_ON)
        self._template.SetInstruction(_MSG_SW_OFF)

    initial_state = GetState()
    timeout_secs = self.args.timeout_secs
    UpdateUI(initial_state)

    sync_utils.WaitFor(lambda: GetState() != initial_state, timeout_secs)
    UpdateUI(not initial_state)
    sync_utils.WaitFor(lambda: GetState() == initial_state, timeout_secs)
    UpdateUI(initial_state)
    # Flip again if state is not end_state
    sync_utils.WaitFor(lambda: GetState() != int(self.args.end_state),
                       timeout_secs)
