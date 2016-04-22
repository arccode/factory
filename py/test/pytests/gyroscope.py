# -*- coding: utf-8 -*-
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for gyroscopes.

Usage examples::

    OperatorTest(
        id='Gyroscope',
        label_zh=u'陀螺仪',
        pytest_name='gyroscope',
        dargs={
            'rotation_threshold': 1,
            'stop_threshold': 0.1
            })

"""

import collections
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import dut
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


_MSG_SPACE = test_ui.MakeLabel(
    'Please put device on a horizontal plane then press space to '
    'start calibration.',
    u'按空白键开始測试。', 'test-info')
_MSG_IN_PROGRESS = test_ui.MakeLabel(
    'Please do not move the device.',
    u'请勿移动待测物。', 'test-info')
_MSG_START_MOVING = test_ui.MakeLabel(
    'Please rotate the device.',
    u'请转动待测物。', 'test-info')

def GetPreparingMessage(secs):
  return test_ui.MakeLabel(
      'Calibration will be started within %d seconds.'
      'Please do not move device.' % secs,
      u'测试程序即将于 %d 秒后开始，请勿移动待测物。' % secs, 'test-info')

_MSG_PASS = test_ui.MakeLabel('PASS', u'成功', 'test-pass')
_MSG_FAIL = test_ui.MakeLabel('FAIL', u'失败', 'test-fail')

_BR = '<br/>'

_CSS = """
  .test-info {font-size: 2em;}
  .test-pass {font-size: 2em; color:green;}
  .test-fail {font-size: 2em; color:red;}
"""


class ReadGyroscopeTask(FactoryTask):
  """Horizontal calibration for accelerometers.

  Attributes:
    test: The main Gyroscope TestCase object.
    gyroscope: The gyroscope object.
    rotation_threshold: The expected value to read when dut start rotating.
    stop_threshold: The expected value to read when dut stop moving.
    timeout_secs: Maximum retry time for gyro to return expected value.
    setup_time_secs: How many seconds to wait after pressing space to
      start calibration.
  """

  def __init__(self, test, gyroscope, rotation_threshold, stop_threshold,
               timeout_secs, setup_time_secs):
    super(ReadGyroscopeTask, self).__init__()
    self.test = test
    self.gyroscope = gyroscope
    self.rotation_threshold = rotation_threshold
    self.stop_threshold = stop_threshold
    self.timeout_secs = timeout_secs
    self.setup_time_secs = setup_time_secs
    self.template = test.template

  def _WaitForDeviceStop(self):
    """Wait until absolute value of all sensors less than stop_threshold."""

    def CheckSensorState():
      raw_data = self.gyroscope.GetRawDataAverage()
      return all(abs(v) < self.stop_threshold for v in raw_data.values())

    sync_utils.WaitFor(CheckSensorState, self.timeout_secs)

  def _WaitForDeviceRotate(self):
    """Wait until all sensors has absolute value > rotation_threshold."""

    max_values = collections.defaultdict(float)
    def CheckSensorMaxValues():
      raw_data = self.gyroscope.GetRawDataAverage()
      for sensor_name in raw_data:
        max_values[sensor_name] = max(max_values[sensor_name],
                                      abs(raw_data[sensor_name]))
      return all(abs(v) > self.rotation_threshold for v in max_values.values())

    sync_utils.WaitFor(CheckSensorMaxValues, self.timeout_secs)

  def StartTask(self):
    """Waits a period of time and then starts testing."""
    for i in xrange(self.setup_time_secs):
      self.template.SetState(GetPreparingMessage(self.setup_time_secs - i))
      time.sleep(1)

    try:
      self.template.SetState(_MSG_IN_PROGRESS)
      self._WaitForDeviceStop()

      self.template.SetState(_MSG_START_MOVING)
      self._WaitForDeviceRotate()
    except type_utils.TimeoutError as e:
      self.Fail(e.message)
      return

    self.template.SetState(' ' + _MSG_PASS + _BR, append=True)
    self.Pass()

  def Run(self):
    """Prompts a message to ask operator to press space."""
    self.template.SetState(_MSG_SPACE)
    self.test.ui.BindKey(' ', lambda _: self.StartTask())


class Gyroscope(unittest.TestCase):

  ARGS = [
      Arg('rotation_threshold', float,
          'The expected value (rad/s) to read when dut start rotating.',
          optional=False),
      Arg('stop_threshold', float,
          'The expected value to read when dut stop moving.',
          optional=False),
      Arg('timeout_secs', int,
          'Timeout in seconds for gyro to return expected value.',
          default=30, optional=True),
      Arg('setup_time_secs', int,
          'Seconds to wait before starting the test.',
          default=2, optional=True)]

  def setUp(self):
    self.dut = dut.Create()
    self.gyroscope = self.dut.gyroscope.GetController()
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_CSS)
    self._task_manager = None

  def runTest(self):
    task_list = [ReadGyroscopeTask(self, self.gyroscope,
                                   self.args.rotation_threshold,
                                   self.args.stop_threshold,
                                   self.args.timeout_secs,
                                   self.args.setup_time_secs)]
    self._task_manager = FactoryTaskManager(self.ui, task_list)
    self._task_manager.Run()
