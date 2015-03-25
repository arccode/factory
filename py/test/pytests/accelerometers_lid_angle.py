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
               'tolerance': 5,
               'spec_offset': (128, 230),
               'spec_ideal_values': (0, 1024)})
"""

import logging
import math
import numpy as np
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.system.accelerometer import AccelerometerController
from cros.factory.system.accelerometer import AccelerometerControllerException
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.ui_templates import OneSection


_MSG_SPACE = lambda a: test_ui.MakeLabel(
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
      Arg(
          'angle', int, 'The target lid angle to test.',
          default=180, optional=True),
      Arg(
          'tolerance', int, 'The tolerance ',
          default=5, optional=True),
      Arg(
          'sample_rate_hz', int,
          'The sample rate in Hz to get raw data from '
          'acceleromters.', default=20, optional=True),
      Arg(
          'capture_count', int,
          'How many times to capture the raw data to '
          'calculate the lid angle.', default=20, optional=True),
      Arg(
          'spec_offset', tuple,
          'A tuple of two integers, ex: (128, 230) '
          'indicating the tolerance for the digital output of sensors under '
          'zero gravity and one gravity. Those values are vendor-specific '
          'and should be provided by the vendor.', optional=False),
      Arg(
          'spec_ideal_values', tuple,
          'A tuple of two integers, ex: (0, 1024) indicating the ideal value '
          'of digital output corresponding to 0G and 1G, respectively. For '
          'example, if a sensor has a 12-bit digital output and -/+ 2G '
          'detection range so the sensitivity is 1024 count/G. The value '
          'should be provided by the vendor.', optional=False),
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

    # Initializes an accelerometer utility class.
    self.accelerometer = AccelerometerController(
        self.args.spec_offset,
        self.args.spec_ideal_values,
        self.args.sample_rate_hz
    )

  def _CalculateLidAngle(self):
    try:
      cal_data = self.accelerometer.GetCalibratedDataAverage(
          self.args.capture_count)
    except AccelerometerControllerException as err:
      logging.info('Read calibrated data failed: %r.', err.args[0])
      return None
    # Calculate the angle between base and lid vectors.
    base_vec = [
        cal_data['in_accel_x_base'],
        cal_data['in_accel_y_base'],
        cal_data['in_accel_z_base']]
    lid_vec = [
        cal_data['in_accel_x_lid'],
        cal_data['in_accel_y_lid'],
        cal_data['in_accel_z_lid']]
    # +Y axis aligned with the hinge.
    hinge_vec = [0.0, float(self.args.spec_ideal_values[1]), 0.0]

    # http://en.wikipedia.org/wiki/Dot_product#Geometric_definition
    # We use dot product and inverse Cosine to get the angle between
    # base_vec and lid_vec in degrees.
    angle_between_vectors = math.degrees(math.acos(
        np.dot(base_vec, lid_vec) / np.linalg.norm(base_vec) /
        np.linalg.norm(lid_vec)))

    # http://en.wikipedia.org/wiki/Cross_product#Geometric_meaning
    # If the dot product of this cross product is normal, it means that the
    # shortest angle between |base| and |lid| was counterclockwise with
    # respect to the surface represented by |hinge| and this angle must be
    # reversed.
    lid_base_cross_vec = np.cross(base_vec, lid_vec)
    if np.dot(lid_base_cross_vec, hinge_vec) > 0.0:
      return 360.0 - angle_between_vectors
    else:
      return angle_between_vectors

  def StartTest(self, _):
    angle = self._CalculateLidAngle()
    if angle is None:
      self.ui.Fail('There is no calibration value for accelerometer in VPD.')
    else:
      logging.info('angle=%d', angle)
      if (angle > self.args.angle + self.args.tolerance or
          angle < self.args.angle - self.args.tolerance):
        self.ui.Fail('The lid angle is out of range: %d' % angle)
      else:
        self.ui.Pass()

  def runTest(self):
    self.ui.Run()
