# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
A test to instruct the operator to plug/unplug AC power.
"""

import threading
import time
import unittest

from cros.factory import system
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg

_TEST_TITLE_PLUG = test_ui.MakeLabel('Connect AC', u'连接充电器')
_TEST_TITLE_UNPLUG = test_ui.MakeLabel('Remove AC', u'移除充电器')

_PLUG_AC = lambda x: test_ui.MakeLabel(
    'Plug in the charger' + (' (%s)' % x if x else ''),
    u'请连接充电器' + (' (%s)' % x if x else ''))
_UNPLUG_AC = test_ui.MakeLabel('Unplug the charger.', u'请移除充电器')

_POLLING_PERIOD_SECS = 1

class ACPowerTest(unittest.TestCase):
  """A test to instruct the operator to plug/unplug AC power.

  Args:
    power_type: The type of the power. None to skip power type check.
    online: True if expecting AC power. Otherwise, False.
  """

  ARGS = [
    Arg('power_type', str, 'Type of the power source', optional=True),
    Arg('online', bool, 'True if expecting AC power',
        default=True, optional=True),
  ]

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE_PLUG if self.args.online
                            else _TEST_TITLE_UNPLUG)
    self._template.SetState(_PLUG_AC(self.args.power_type)
                            if self.args.online else _UNPLUG_AC)
    self._power_state = dict()
    self._done = threading.Event()
    self._power = system.GetBoard().power
    self._last_type = None

  def Done(self):
    self._done.set()

  def CheckCondition(self):
    if self._power.CheckACPresent() != self.args.online:
      return False
    current_type = self._power.GetACType()
    if self.args.power_type and self.args.power_type != current_type:
      if self._last_type != current_type:
        factory.console.warning('Expecting %s but see %s',
                                self.args.power_type,
                                current_type)
        self._last_type = current_type
      return False
    return True

  def runTest(self):
    self._ui.Run(blocking=False, on_finish=self.Done)
    while not self._done.is_set():
      if self.CheckCondition():
        return
      time.sleep(_POLLING_PERIOD_SECS)
