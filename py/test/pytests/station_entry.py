#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Starts or ends a station-based test.

This factory test invokes functions to setup or teardown a station-based
test list.
"""

import threading
import unittest

import factory_common # pylint: disable=W0611

from cros.factory.test import countdown_timer
from cros.factory.test import dut
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils import sync_utils
from cros.factory.utils.arg_utils import Arg


_CSS = """
.prompt {
  font-size: 2em;
}

.warning {
  color: red;
}
"""

_TITLE_START = test_ui.MakeLabel('Start Station Test', u'开始测试')
_TITLE_END = test_ui.MakeLabel('End Station Test', u'结束测试')

_ID_MSG_DIV = 'msg'
_ID_COUNTDOWN_DIV = 'countdown'

_STATE_HTML = """
<div id='%s'></div>
<div id='%s'></div>
""" % (_ID_MSG_DIV, _ID_COUNTDOWN_DIV)

_MSG_INSERT = test_ui.MakeLabel(
    'Please attach DUT.',
    u'INSERT 请插入测试装置。',
    'prompt')

_MSG_PRESS_SPACE = test_ui.MakeLabel(
    'Press SPACE to start the test.',
    u'请按空白键开始测试。',
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


class StationEntry(unittest.TestCase):
  """The factory test to start station test process."""
  ARGS = [
      Arg('start_station_tests', bool,
          'To start or stop the factory station tests.',
          default=True, optional=True),
      Arg('prompt_start', bool,
          'Prompt for spacebar before starting test.',
          default=False, optional=True),
      Arg('clear_device_data', bool,
          'Clear device data (serial numbers).',
          default=True, optional=True),
      Arg('timeout_secs', int,
          'Timeout for waiting the device. Set to None for waiting forever.',
          default=None, optional=True),
      Arg('disconnect_dut', bool,
          'Ask operator to disconnect DUT or not',
          default=True, optional=True),
  ]

  def setUp(self):
    self._dut = dut.Create()
    self._state = factory.get_state_instance()
    self._ui = test_ui.UI()
    self._ui.AppendCSS(_CSS)
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TITLE_START if self.args.start_station_tests else
                            _TITLE_END)
    self._space_event = threading.Event()

  def RestartAllTests(self):
    self._state.ScheduleRestart()

  def SendTestResult(self):
    self._dut.hooks.SendTestResult(self._state.get_test_states())

  def _ClearDeviceData(self):
    """Clear serial numbers from DeviceData if requested."""
    if self.args.clear_device_data:
      shopfloor.DeleteDeviceData(
          ['serial_number', 'mlb_serial_number'], optional=True)

  def runTest(self):
    self._template.SetState(_STATE_HTML)
    self._ui.Run(blocking=False)
    self._ui.BindKey(' ', lambda _: self._space_event.set())

    if self.args.start_station_tests:
      self._ClearDeviceData()
      self.Start()
    else:
      self.End()
      self._ClearDeviceData()

  def Start(self):
    self._ui.SetHTML(_MSG_INSERT, id=_ID_MSG_DIV)
    disable_event = threading.Event()

    if self.args.timeout_secs:
      countdown_timer.StartCountdownTimer(
          self.args.timeout_secs,
          lambda: (self._ui.Fail('DUT is not connected in %d seconds' %
                                 self.args.timeout_secs)),
          self._ui,
          _ID_COUNTDOWN_DIV,
          disable_event=disable_event)

    def _IsReady():
      try:
        self._dut.CheckCall(['true'])
        return True
      except:  # pylint: disable=bare-except
        return False

    sync_utils.WaitFor(_IsReady, self.args.timeout_secs, poll_interval=1)
    disable_event.set()

    if self.args.prompt_start:
      self._ui.SetHTML(_MSG_PRESS_SPACE, id=_ID_MSG_DIV)
      sync_utils.WaitFor(self._space_event.isSet, None)
      self._space_event.clear()

  def End(self):
    self._ui.SetHTML(_MSG_SEND_RESULT, id=_ID_MSG_DIV)
    self.SendTestResult()

    self._ui.SetHTML(_MSG_REMOVE_DUT, id=_ID_MSG_DIV)
    if not self._dut.link.IsLocal():
      if self.args.disconnect_dut:
        sync_utils.WaitFor(lambda: not self._dut.link.IsReady(),
                           self.args.timeout_secs,
                           poll_interval=1)
      else:
        sync_utils.WaitFor(self._space_event.isSet, None)
        self._space_event.clear()

    self._ui.SetHTML(_MSG_RESTART_TESTS, id=_ID_MSG_DIV)
    self.RestartAllTests()
