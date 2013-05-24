# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
A test to instruct the operator to plug/unplug AC power.
"""

from collections import namedtuple
import glob
import logging
import os
import threading
import time
import unittest

from cros.factory.test.args import Arg
from cros.factory.test import test_ui
from cros.factory.test import ui_templates

_TEST_TITLE_PLUG = test_ui.MakeLabel('Connect AC', u'连接充电器')
_TEST_TITLE_UNPLUG = test_ui.MakeLabel('Remove AC', u'移除充电器')

_PLUG_AC = test_ui.MakeLabel('Plug in the charger.', u'请连接充电器')
_UNPLUG_AC = test_ui.MakeLabel('Unplug the charger.', u'请移除充电器')

_POLLING_PERIOD_SECS = 1

POWER_SUPPLY_PATH = '/sys/class/power_supply/*'

State = namedtuple('State', 'power_type online')

class ACPowerTest(unittest.TestCase):
  """A test to instruct the operator to plug/unplug AC power.

  Args:
    power_path: The path to power supply in sysfs. None to search for
      specified power_type.
    power_type: The type of the power. None to skip power type check.
    online: True if expecting AC power. Otherwise, False.
  """

  ARGS = [
    Arg('power_path', str, 'Sysfs path for power source', optional=True),
    Arg('power_type', str, 'Type of the power source', optional=True),
    Arg('online', bool, 'True if expecting AC power',
        default=True, optional=True),
  ]

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetTitle(_TEST_TITLE_PLUG if self.args.online
                            else _TEST_TITLE_UNPLUG)
    self._template.SetState(_PLUG_AC if self.args.online else _UNPLUG_AC)
    self._power_state = dict()
    self._done = threading.Event()

  def GetPowerType(self, path):
    type_path = os.path.join(path, 'type')
    if not os.path.exists(type_path):
      return None
    with open(type_path, 'r') as f:
      return f.read().strip()

  def PowerIsOnline(self, path):
    """Check if the specified power source is online.

    Returns:
      True if online=1 and False if online=0. If there's no 'online' property,
        returns None.
    """
    online_path = os.path.join(path, 'online')
    if not os.path.exists(online_path):
      return None
    with open(online_path, 'r') as f:
      return f.read().strip() == '1'

  def UpdatePowerStateMap(self, path):
    if path:
      path = [path]
    else:
      path = glob.glob(POWER_SUPPLY_PATH)
    new_state = dict([(p, State(power_type=self.GetPowerType(p),
                                online=self.PowerIsOnline(p)))
                      for p in path])

    removed = list(set(self._power_state.keys()) - set(new_state.keys()))
    if removed:
      logging.info('Power source(s) %s removed', removed)

    for p in new_state.iterkeys():
      if p not in self._power_state or self._power_state[p] != new_state[p]:
        logging.info('%s: %s', p, new_state[p])

    self._power_state = new_state

  def Done(self):
    self._done.set()

  def runTest(self):
    self._ui.Run(blocking=False, on_finish=self.Done)
    while not self._done.is_set():
      self.UpdatePowerStateMap(self.args.power_path)
      if any((x.power_type == self.args.power_type
              if self.args.power_type else True) and
             x.online == self.args.online
             for x in self._power_state.values()):
        return
      time.sleep(_POLLING_PERIOD_SECS)
