# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is a lid angle test based on accelerometers.

Description
-----------
There are two accelerometers in ChromeOS for lid angle calculation.
This test asks OP to turn lid angle into a desired angle and then
checks whether the lid angle is within some threshold.
Please notice this test requires the hinge to be in a horizontal plane.

Test Procedure
--------------
1. Bend the device (base/lid) into a desired angle then press space.
2. Wait for completion.

Dependency
----------
- Device API (``cros.factory.device.accelerometer``).

Examples
--------
Usage examples::

    {
      "pytest_name": "accelerometers_lid_angle",
      "args": {
        "angle": 180,
        "tolerance": 5,
        "spec_offset": [0.5, 0.5]
      }
    }
"""

import logging
import math

import numpy as np

from cros.factory.device import accelerometer
from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.utils.arg_utils import Arg


class AccelerometersLidAngleTest(test_case.TestCase):
  ARGS = [
      Arg('angle', int, 'The target lid angle in degree to test.', default=180),
      Arg('tolerance', int, 'The tolerance in degree.', default=5),
      Arg(
          'capture_count', int, 'How many times to capture the raw data to '
          'calculate the lid angle.', default=20),
      Arg(
          'spec_offset', list,
          'Two numbers, ex: [0.5, 0.5] indicating the tolerance in m/s^2 for '
          'the digital output of sensors under 0 and 1G.'),
      Arg('autostart', bool, 'Starts the test automatically without prompting.',
          default=False),
      Arg('sample_rate_hz', int, 'The sample rate in Hz to get raw data from '
          'accelerometers.', default=20),
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui.ToggleTemplateClass('font-large', True)

    # Initializes an accelerometer utility class.
    self.accelerometers = {}
    for location in ['base', 'lid']:
      self.accelerometers[location] = (
          self.dut.accelerometer.GetController(location))

  def _CalculateLidAngle(self):
    """ Calculate the lid angle based on the two accelerometers (base/lid).

    When the lid angle is 180 degrees and the keyboard is on a horizontal
    plane in front of an user, the standard orientation of both
    accelerometers is:
      +X axis is aligned with the hinge and pointing to the right.
      +Y axis is in the same plane as the keyboard pointing towards the
         top of the screen.
      +Z axis is perpendicular to the keyboard, pointing out of the keyboard.

    This orientation is used in kernel 3.18 and later, previous kernel
    might use different orientation. It's also used in Android and is defined
    in the w3 spec: http://www.w3.org/TR/orientation-event/#description.
    """
    cal_data = {}
    for location, accelerometer_controller in self.accelerometers.items():
      try:
        cal_data[location] = accelerometer_controller.GetData(
            self.args.capture_count, self.args.sample_rate_hz)
      except accelerometer.AccelerometerException as err:
        logging.info(
            'Read %s calibrated data failed: %r.', location, err.args[0])
        return None

    # +X axis is aligned with the hinge.
    hinge_vec = [9.8, 0.0, 0.0]
    # The calulation requires hinge in a horizontal position.
    min_value = -self.args.spec_offset[0]
    max_value = self.args.spec_offset[0]
    for data in cal_data.values():
      if not min_value <= data['in_accel_x'] <= max_value:
        self.FailTask('The hinge is not in a horizontal plane.')

    base_vec_flattened = [
        0.0,
        cal_data['base']['in_accel_y'],
        cal_data['base']['in_accel_z']]
    lid_vec_flattened = [
        0.0,
        cal_data['lid']['in_accel_y'],
        cal_data['lid']['in_accel_z']]

    # http://en.wikipedia.org/wiki/Dot_product#Geometric_definition
    # We use dot product and inverse Cosine to get the angle between
    # base_vec_flattened and lid_vec_flattened in degrees.
    angle_between_vectors = math.degrees(math.acos(
        np.dot(base_vec_flattened, lid_vec_flattened) /
        np.linalg.norm(base_vec_flattened) /
        np.linalg.norm(lid_vec_flattened)))

    # Based on the standard orientation described above, the sum of the
    # lid angle (between keyboard and screen) and angle_between_vectors
    # is 180 degrees. For example, when turning the lid angle to 180 degrees,
    # the orientation of two accelerometers is the same, hence
    # angle_between_vectors is 0 degrees.
    lid_angle = 180.0 - angle_between_vectors

    # http://en.wikipedia.org/wiki/Cross_product#Geometric_meaning
    # If the dot product of this cross product is normal, it means that the
    # shortest angle between |base| and |lid| was counterclockwise with
    # respect to the surface represented by |hinge| and this angle must be
    # reversed. That means the current lid angle is >= 180 degrees and the
    # value should be (360.0 - lid_angle), where lid_angle is always the
    # smaller angle between the keyboard and the screen.
    lid_base_cross_vec = np.cross(base_vec_flattened, lid_vec_flattened)
    if np.dot(lid_base_cross_vec, hinge_vec) > 0.0:
      return 360.0 - lid_angle
    return lid_angle

  def runTest(self):
    if not self.args.autostart:
      self.ui.SetState(
          _('Please open the lid to {angle} degrees and press SPACE.',
            angle=self.args.angle))
      self.ui.WaitKeysOnce(test_ui.SPACE_KEY)
    else:
      self.ui.SetState(
          _('Please open the lid to {angle} degrees.', angle=self.args.angle))
      self.Sleep(1)

    self.ui.SetState(_('Checking angle...'))
    angle = self._CalculateLidAngle()
    if angle is None:
      self.FailTask('There is no calibration value for accelerometer in VPD.')

    logging.info('angle = %f', angle)
    if not (self.args.angle - self.args.tolerance <= angle <=
            self.args.angle + self.args.tolerance):
      self.FailTask('The lid angle is out of range: %f' % angle)
