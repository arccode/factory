# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for accelerometers calibration.

This is a calibration test for two tri-axis (x, y, and z) accelerometers
in a ChromeOS device. From one accelerometer, we can obtain digital output
proportional to the linear acceleration in each axis. For example, the
ideal value of a sensor having 12-bit analog-to-digital resolution and
+/- 2G detection range will be 1024 count/g. If we put it on a flat table
we can get (x, y, z) = (0, 0, 1024) at an ideal case. For upside down
we'll have (x, y, z) = (0, 0, -1024).

Since accelerometer is very sensitive, the digital output will be different
for each query. For example, (34, -29, 998), (-31, 24, 979), (4, 9, 1003), etc.
In addition, temperature or the assembly quality may impact the accuracy
of the accelerometer during manufacturing (ex, position is tilt). To
mitigate this kind of errors, we'll sample several records of raw data
and compute its average value under an ideal environment.
Then store the offset as a calibrated value for future calculation.

For each signal, there is an equation in the driver:

- _input = (_raw * _calibscale / 1024) + _calibbias.

In a horizontal calibration, we'll put accelerometers on a flat
position then sample 100 records of raw data.
In this position, two axes are under 0G and one axis is under 1G.
Then we'll store the difference between the ideal value (0 and -/+1024)
and the average value of 100 samples as '_calibbias'. For '_calibscale',
we'll set it as default value: 1024.

Below is an example of test list. There are some mandatory arguments:

- orientation: A dict of { signal_name: orientation in gravity }
  indicates which signal is under 0G and which signal is under -/+1G
  during calibration.

- spec_offset: A tuple of two numbers, ex: (0.5, 0.5) indicating the
  tolerance in m/s^2 for the digital output of sensors under 0G and -/+1G.

Usage examples::

    OperatorTest(
        id='AccelerometersCalibration',
        label_zh=u'加速度计校准',
        pytest_name='accelerometers_calibration',
        dargs={'orientation': {
                   'in_accel_x': 0,
                   'in_accel_y': 0,
                   'in_accel_z': 1},
               'spec_offset': (0.5, 0.5),
               'location': 'base'})

"""

import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import accelerometer
from cros.factory.device import device_utils
from cros.factory.test import factory_task
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


_MSG_NOT_SUPPORTED = i18n_test_ui.MakeI18nLabelWithClass(
    'ERROR: The function is not supported.', 'test-fail')
_MSG_SPACE = i18n_test_ui.MakeI18nLabelWithClass(
    'Please put device on a horizontal plane then press space to '
    'start calibration.', 'test-info')
_MSG_PREPARING_CALIBRATION = lambda time: i18n_test_ui.MakeI18nLabelWithClass(
    'Calibration will be started within {time} seconds.'
    'Please do not move device.',
    'test-info',
    time=time)
_MSG_CALIBRATION_IN_PROGRESS = i18n_test_ui.MakeI18nLabelWithClass(
    'Calibration is in progress, please do not move device.', 'test-info')
_MSG_PASS = i18n_test_ui.MakeI18nLabelWithClass('PASS', 'test-pass')
_MSG_FAIL = i18n_test_ui.MakeI18nLabelWithClass('FAIL', 'test-fail')
_MESSAGE_DELAY_SECS = 1

_BR = '<br>'

_CSS = """
  .test-info {font-size: 2em;}
  .test-pass {font-size: 2em; color:green;}
  .test-fail {font-size: 2em; color:red;}
"""


class HorizontalCalibrationTask(factory_task.FactoryTask):
  """Horizontal calibration for accelerometers.

  Attributes:
    test: The main AccelerometersCalibration TestCase object.
    orientation: orientation in gravity (0, -1G or +1G)
      of two sensors during calibration.
    Ex, {'in_accel_x_base': 0,
         'in_accel_y_base': 0,
         'in_accel_z_base': 1,
         'in_accel_x_lid': 0,
         'in_accel_y_lid': 0,
         'in_accel_z_lid': -1}
    capture_count: How many iterations to capture the raw data to calculate
      the average.
    setup_time_secs: How many seconds to wait after pressing space to
      start calibration.
  """

  def __init__(self, test, orientation, capture_count, setup_time_secs,
               spec_offset, sample_rate):
    super(HorizontalCalibrationTask, self).__init__()
    self.test = test
    self.orientation = orientation
    self.capture_count = capture_count
    self.setup_time_secs = setup_time_secs
    self.spec_offset = spec_offset
    self.sample_rate = sample_rate
    self.accelerometer = test.accelerometer_controller
    self.template = test.template

  def StartCalibration(self):
    """Waits a period of time and then starts calibration."""
    # Waits for a few seconds to let machine become stable.
    for i in xrange(self.setup_time_secs):
      self.template.SetState(
          _MSG_PREPARING_CALIBRATION(self.setup_time_secs - i))
      time.sleep(_MESSAGE_DELAY_SECS)

    # Cleanup offsets before calibration
    self.accelerometer.CleanUpCalibrationValues()

    # Starts calibration.
    self.template.SetState(_MSG_CALIBRATION_IN_PROGRESS)
    try:
      raw_data = self.accelerometer.GetData(self.capture_count)
    except accelerometer.AccelerometerException:
      self.Fail('Read raw data failed.')
      return
    # Checks accelerometer is normal or not before calibration.
    if not self.accelerometer.IsWithinOffsetRange(raw_data, self.orientation,
                                                  self.spec_offset):
      self.template.SetState(' ' + _MSG_FAIL + _BR, append=True)
      self.Fail('Raw data out of range, the accelerometers may be damaged.')
      return
    calib_bias = self.accelerometer.CalculateCalibrationBias(
        raw_data, self.orientation)
    self.accelerometer.UpdateCalibrationBias(calib_bias)
    self.template.SetState(' ' + _MSG_PASS + _BR, append=True)
    self.Pass()

  def Run(self):
    """Prompts a message to ask operator to press space."""
    self.template.SetState(_MSG_SPACE)
    self.test.ui.BindKey(test_ui.SPACE_KEY, lambda _: self.StartCalibration())


class SixSidedCalibrationTask(factory_task.FactoryTask):
  """Six-sided calibration for accelerometers."""

  def __init__(self, test):
    super(SixSidedCalibrationTask, self).__init__()
    self.template = test.template

  def Run(self):
    # TODO(bowgotsai): add six-sided calibration.
    self.template.SetState(_MSG_NOT_SUPPORTED)
    time.sleep(_MESSAGE_DELAY_SECS)
    self.Fail('Six sided calibration is not supported.')


class AccelerometersCalibration(unittest.TestCase):

  ARGS = [
      Arg(
          'calibration_method', str,
          'There are two calibration methods: horizontal calibration and '
          'six-sided calibration. The value can be either "horizontal" or '
          '"sixsided".', default='horizontal', optional=True),
      Arg(
          'orientation', dict,
          'Keys: the name of the accelerometer signal. For example, '
          '"in_accel_x_base" or "in_accel_x_lid". The possible keys are '
          '"in_accel_(x|y|z)_(base|lid)".'
          'Values: an int or a tuple of (orientation-1, orientation-2, ...).'
          'Each orientation is 0, 1 or -1 representing the ideal '
          'value for gravity under such orientation. For example, 1 or '
          '(0, 0, 1, 0, 0, -1).'
          'An example of orientation for horizontal calibration: {'
          '    "in_accel_x_base": 0,'
          '    "in_accel_y_base": 0,'
          '    "in_accel_z_base": 1,'
          '    "in_accel_x_lid": 0,'
          '    "in_accel_y_lid": 0,'
          '    "in_accel_z_lid": -1}.'
          'Another example of orientation_gravity for six-sided calibration: {'
          '    "in_accel_x_base": (0, 0, 1, -1, 0, 0),'
          '    "in_accel_y_base": (0, 0, 0, 0, 1, -1),'
          '    "in_accel_z_base": (1, -1, 0, 0, 0, 0),'
          '    "in_accel_x_lid": (0, 0, 1, -1, 0, 0),'
          '    "in_accel_y_lid": (0, 0, 0, 0, 1, -1),'
          '    "in_accel_z_lid": (1, -1, 0, 0, 0, 0)}.', optional=False),
      Arg(
          'sample_rate_hz', int,
          'The sample rate in Hz to get raw data from '
          'accelerometers.', default=20, optional=True),
      Arg(
          'capture_count', int,
          'How many times to capture the raw data to '
          'calculate the average value.', default=100, optional=True),
      Arg(
          'setup_time_secs', int,
          'How many seconds to wait before starting '
          'to calibration.', default=2, optional=True),
      Arg(
          'spec_offset', tuple,
          'A tuple of two numbers, ex: (0.5, 0.5) '
          'indicating the tolerance in m/s^2 for the digital output of '
          'sensors under 0 and 1G.', optional=False),
      Arg(
          'location', str,
          'The location for the accelerometer', default='base',
          optional=True)]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    # Checks arguments.
    self.assertIn(self.args.calibration_method, ['horizontal', 'sixsided'])
    self.assertEquals(2, len(self.args.spec_offset))
    # Initializes a accelerometer utility class.
    self.accelerometer_controller = (
        self.dut.accelerometer.GetController(self.args.location))
    self.ui.AppendCSS(_CSS)
    self._task_manager = None

  def runTest(self):
    if self.args.calibration_method == 'horizontal':
      task_list = [HorizontalCalibrationTask(
          self,
          self.args.orientation,
          self.args.capture_count,
          self.args.setup_time_secs,
          self.args.spec_offset,
          self.args.sample_rate_hz)]
    else:
      task_list = [SixSidedCalibrationTask(self.args.orientation)]
    self._task_manager = factory_task.FactoryTaskManager(self.ui, task_list)
    self._task_manager.Run()
