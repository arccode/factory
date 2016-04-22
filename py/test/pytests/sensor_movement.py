# -*- coding: utf-8 -*-
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for sensors.

Usage examples::

    OperatorTest(
        id='AccelerometerMovement',
        label_en='Accelerometer Movement',
        pytest_name='sensor_movement',
        dargs={
            'sensor_type': 'accelerometer',
            'sub_tests': [
                ('X axis up', u'X轴朝上', {'x': 9.8, 'y': 0, 'z': 0}),
                ('Y axis up', u'Y轴朝上', {'x': 0, 'y': 9.8, 'z': 0}),
                ('Z axis up', u'Z轴朝上', {'x': 0, 'y': 0, 'z': 9.8}),],
            'tolerance': 1.0,
            'controller_options': {
                'spec_offset': (),
                'spec_ideal_values': (),
                'sample_rate': 60,
                'location': 'base'}
            })

Another example, the value of y and z axis are ignored in this test::

    OperatorTest(
        id='GyroscopeMovement',
        label_en='Gyroscope Movement',
        pytest_name='sensor_movement',
        dargs={
            'sensor_type': 'gyroscope',
            'sub_tests': [
                ('Rotate x axis', u'旋转X轴', {'x': 3}),],
            'tolerance': 1.5,
            })

"""

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import dut
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


_MSG_PASS = test_ui.MakeLabel('PASS', u'成功', 'test-pass')
_MSG_FAIL = test_ui.MakeLabel('FAIL', u'失败', 'test-fail')

_BR = '<br/>'

_CSS = """
  .test-info {font-size: 2em;}
  .test-pass {font-size: 2em; color:green;}
  .test-fail {font-size: 2em; color:red;}
"""


class SensorMovementTask(FactoryTask):
  """Movement test for accel/gyro/ecompass.

  Args:
    test: The main SensorMovement TestCase object.
    dut_instance: The dut instance.
    sensor_type: The type of the sensor.
        See SensorMovement.ARGS for more detail.
    instruction_label: A html string contains instruction on how to move
        the dut. See SensorMovement.ARGS for more detail.
    expected_value: The expected sensor output.
        See SensorMovement.ARGS for more detail.
    tolerance: The tolerance for the output of sensors.
    capture_count: Number of raw data to capture to calculate the average
        value.
    timeout_secs: Timeout in seconds for sensor to return expected value.
    controller_options: Arguments pass to GetController() of the sensor.
  """
  def __init__(self, test, dut_instance, sensor_type, instruction_label,
               expected_value, tolerance, capture_count, timeout_secs,
               controller_options):
    super(SensorMovementTask, self).__init__()
    self.test = test
    self.dut = dut_instance
    self.instruction_label = instruction_label
    self.expected_value = expected_value
    self.tolerance = tolerance
    self.capture_count = capture_count
    self.timeout_secs = timeout_secs
    self.template = test.template
    if sensor_type == 'accelerometer':
      self.sensor = self.dut.accelerometer.GetController(**controller_options)
    elif sensor_type == 'gyroscope':
      self.sensor = self.dut.gyroscope.GetController(**controller_options)
    elif sensor_type == 'magnetometer':
      self.sensor = self.dut.magnetometer
    else:
      raise ValueError('Invalid sensor name')

  def _CheckSensorValue(self):
    raw_data = self.sensor.GetRawDataAverage(self.capture_count)
    return all(abs(raw_data[k] - v) <= self.tolerance
               for k, v in self.expected_value.iteritems())

  def Run(self):
    self.template.SetState(self.instruction_label)
    try:
      sync_utils.WaitFor(self._CheckSensorValue, self.timeout_secs)
    except type_utils.TimeoutError as e:
      self.Fail(e.message)
      return
    self.template.SetState(' ' + _MSG_PASS + _BR, append=True)
    self.Pass()


class SensorMovement(unittest.TestCase):

  ARGS = [
      Arg('sensor_type', str,
          'Type of the sensor, valid values are "accelerometer", "gyroscope" '
          'and "magnetometer".',
          optional=False),
      Arg('sub_tests', list,
          'A list of tuples of the format'
          '(instruction_en, instruction_zh, expected_value), which tells '
          'operator to move the dut, and checks the sensor output.\n'
          '\n'
          'The fields are:\n'
          '- instruction_en: (str or unicode) instruction on how to move the '
          'dut in English.\n'
          '- instruction_zh: (str or unicode) instruction on how to move the '
          'dut in Chinese.\n'
          '- expected_value: (dict) A dict of {sensor-name: value} indicates '
          'the expect output of sensors. '
          'The keys of this dict can be a subset of '
          'sensor.GetRawDataAverage(), non-existing keys are ignored.',
          optional=False),
      Arg('tolerance', float, 'The tolerance for the output of sensors.',
          optional=False),
      Arg('capture_count', int,
          'Number of raw data to capture to calculate the average value.',
          default=1, optional=True),
      Arg('timeout_secs', int,
          'Timeout in seconds for sensor to return expected value.',
          default=30, optional=True),
      Arg('controller_options', dict,
          'Arguments pass to GetController() of the sensor.',
          default={}, optional=True)]

  def setUp(self):
    self.dut = dut.Create()
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_CSS)
    self._task_manager = None

  def runTest(self):
    task_list = [SensorMovementTask(self,
                                    self.dut,
                                    self.args.sensor_type,
                                    test_ui.MakeLabel(test[0],
                                                      test[1],
                                                      'test-info'),
                                    test[2],
                                    self.args.tolerance,
                                    self.args.capture_count,
                                    self.args.timeout_secs,
                                    self.args.controller_options)
                 for test in self.args.sub_tests]
    self._task_manager = FactoryTaskManager(self.ui, task_list)
    self._task_manager.Run()
