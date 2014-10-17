# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is a lid angle test based on accelerometers.

There are two accelerometers in ChromeOS for lid angle calculation.
This test asks OP to turn lid angle into a desired angle and then
checks whether the lid angle is within some threshold.

Usage examples::

    OperatorTest(
        id='accelerometers_lid_angle',
        label_zh=u'上盖角度测试',
        pytest_name='accelerometers_lid_angle',
        dargs={'angle': 180,
               'tolerance': 5})
"""

import unittest
import logging
import os

import factory_common  # pylint: disable=W0611
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils.process_utils import SpawnOutput


_IIO_DEVICES_PATH = '/sys/bus/iio/devices/'


_MSG_SPACE = lambda a : test_ui.MakeLabel(
    'Please open the lid to %s degree. <br>'
    'Press space to start.' % a,
    u'请将上盖掀开到 %s 度.<br> 压下空白键开始测试' % a,
    css_class='accelerometers-lid-angle-test')

_HTML_ACCELEROMETERS_LID_ANGLE = """
<table style="width: 70%%; margin: auto;">
  <tr>
    <td align="center"><div id="accelerometers_lid_angle_title"></div></td>
  </tr>
</table>
"""

_CSS_ACCELEROMETERS_LID_ANGLE = """
  .accelerometers-lid-angle-test { font-size: 2em; }
"""

_JS_ACCELEROMETERS_LID_ANGLE = """
window.onkeydown = function(event) {
  if (event.keyCode == 32) { // space
    test.sendTestEvent("StartTest", '');
  }
}
"""

class AccelerometersLidAngleTest(unittest.TestCase):

  ARGS = [
    Arg('angle', int, 'The target lid angle to test.',
        default=180, optional=True),
    Arg('tolerance', int, 'The tolerance ',
        default=5, optional=True),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_CSS_ACCELEROMETERS_LID_ANGLE)
    self.template.SetState(_HTML_ACCELEROMETERS_LID_ANGLE)
    self.ui.RunJS(_JS_ACCELEROMETERS_LID_ANGLE)
    self.ui.SetHTML(
        _MSG_SPACE(self.args.angle), id='accelerometers_lid_angle_title')
    self.ui.AddEventHandler('StartTest', self.StartTest)

  def StartTest(self, _):
    angle = int(SpawnOutput(
        ['cat', os.path.join(self._ProbeIIOBus(), 'in_angl_input')], log=True))
    logging.info('angle=%d', angle)
    if (angle > self.args.angle + self.args.tolerance or
        angle < self.args.angle - self.args.tolerance):
      self.ui.Fail('The lid angle is out of range: %d' % angle)
    else:
      self.ui.Pass()

  def runTest(self):
    self.ui.Run()

  def _ProbeIIOBus(self):
    """Auto probing the iio bus of accelerometers.

    The iio bus will be '/sys/bus/iio/devices/iio:device0' if it's located
    at address 0. We'll probe 0-9 to check where the accelerometer locates.

    Returns:
      '/sys/bus/iio/devices/iio:deviceX' where X is a number.
    """
    for addr in xrange(0, 10):
      iio_bus_id = 'iio:device' + str(addr)
      accelerometer_name_path = os.path.join(
          _IIO_DEVICES_PATH, iio_bus_id, 'name')
      if 'cros-ec-accel' == SpawnOutput(
          ['cat', accelerometer_name_path], log=True).strip():
        logging.info('Found accelerometer at: %r.', iio_bus_id)
        return os.path.join(_IIO_DEVICES_PATH, iio_bus_id)
    self.ui.Fail('Cannot find accelerometer in this device.')
