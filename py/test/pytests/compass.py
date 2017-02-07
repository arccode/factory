# -*- coding: utf-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Compass test which requires operator place the DUT heading north and south.
"""


import math
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils import sync_utils
from cros.factory.utils.arg_utils import Arg

_COMPASS_CSS = '''
.compass {
  width: 300px;
  height: 300px;
  border: 2px solid black;
  border-radius: 50%;
  font-size: 200%;
  margin: auto;
  position: relative
}

.success {
  background: #afa;
  font-size: 4em;
}
'''

_STATE_TEMPLATE = '''
<div>
  <div style='position: absolute; text-align: left'>
    in_magn_x: {in_magn_x}<br>
    in_magn_y: {in_magn_y}<br>
    in_magn_z: {in_magn_z}<br>
    degree: {degree:.1f}<br>
  </div>
  <div class=compass style='transform: rotate({degree}deg)'>
    <div style='color: red'>N</div>
    <div style='position: absolute; bottom: 0; width: 300px'>S</div>
  </div>
<div>
'''

_MSG_STATUS_SUCCESS = test_ui.MakeLabel(
    'Success!', u'成功！')
_HTML_STATUS_SUCCESS = '<div class="success">%s</div>' % _MSG_STATUS_SUCCESS

_NORTH = (0, 1)
_SOUTH = (0, -1)

_FLASH_STATUS_TIME = 1


class CompassTest(unittest.TestCase):
  ARGS = [
      Arg('tolerance', int, 'The tolerance in degree.',
          default=5, optional=True)
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.controller = self.dut.magnetometer.GetController()
    self.ui = test_ui.UI()
    self.ui.AppendCSS(_COMPASS_CSS)
    self._template = ui_templates.TwoSections(self.ui)

  def runTest(self):
    self._SetInstruction('north', u'北')
    sync_utils.PollForCondition(
        poll_method=lambda: self._CheckDirection(_NORTH),
        timeout_secs=1000,
        poll_interval_secs=0.1)
    self._template.SetState(_HTML_STATUS_SUCCESS)
    time.sleep(_FLASH_STATUS_TIME)

    self._SetInstruction('south', u'南')
    sync_utils.PollForCondition(
        poll_method=lambda: self._CheckDirection(_SOUTH),
        timeout_secs=1000,
        poll_interval_secs=0.1)
    self._template.SetState(_HTML_STATUS_SUCCESS)
    time.sleep(_FLASH_STATUS_TIME)

  def _SetInstruction(self, direction_en, direction_zh):
    label = test_ui.MakeLabel('Put the DUT towards %s' % direction_en,
                              u'将机器朝向%s方' % direction_zh)
    self._template.SetTitle(label)

  def _CalculateDirection(self, x, y):
    """Calculate the absolute direction of the compass in degree.

    Args:
      x: X-axis component of the direction. X-axis points towards east.
      y: Y-axis component of the direction. Y-axis points towards north.

    Returns:
      Directed angle relative to north (0, 1), in degree, clockwise.
      For example:
          North = 0
          East = 90
          South = 180 = -180
          West = -90
    """
    rad = math.atan2(x, y)
    return rad / math.pi * 180

  def _CalculateAngle(self, x1, y1, x2, y2):
    """Calculate the angle between two vectors (x1, y1) and (x2, y2)."""
    rad = math.acos(
        (x1 * x2 + y1 * y2) / math.hypot(x1, y1) / math.hypot(x2, y2))
    return rad / math.pi * 180

  def _CheckDirection(self, expected_direction):
    values = self.controller.GetData(capture_count=1)
    x, y = values['in_magn_x'], values['in_magn_y']
    if x == 0 and y == 0:
      # atan2(0, 0) returns 0, we need to avoid this case.
      raise factory.FactoryTestFailure(
          'Sensor outputs (0, 0), possibly not working.')
    degree = self._CalculateDirection(x, y)
    self._template.SetState(_STATE_TEMPLATE.format(degree=degree, **values))
    return (
        self._CalculateAngle(x, y, *expected_direction) < self.args.tolerance)
