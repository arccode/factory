# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for gyroscopes.

Usage examples::

    OperatorTest(
        id='Gyroscope',
        pytest_name='gyroscope',
        dargs={
            'rotation_threshold': 1.0,
            'stop_threshold': 0.1
        })
"""

import collections
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import event
from cros.factory.test import factory_task
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


_MSG_SPACE = i18n_test_ui.MakeI18nLabelWithClass(
    'Please put device on a horizontal plane then press space to '
    'start calibration.', 'test-info')
_MSG_IN_PROGRESS = i18n_test_ui.MakeI18nLabelWithClass(
    'Please do not move the device.', 'test-info')
_MSG_START_MOVING = i18n_test_ui.MakeI18nLabelWithClass(
    'Please rotate the device.', 'test-info')
_MSG_SUBTESTS = '<div class="{state}">{key}={value}</div>'

def GetPreparingMessage(secs):
  return i18n_test_ui.MakeI18nLabelWithClass(
      'Calibration will be started within {secs} seconds.'
      'Please do not move device.',
      'test-info',
      secs=secs)


_MSG_PASS = i18n_test_ui.MakeI18nLabelWithClass('PASS', 'test-pass')
_MSG_FAIL = i18n_test_ui.MakeI18nLabelWithClass('FAIL', 'test-fail')

_BR = '<br>'

_CSS = """
  .test-info {font-size: 2em;}
  .test-pass {font-size: 2em; color:green;}
  .test-fail {font-size: 2em; color:red;}
"""


class ReadGyroscopeTask(factory_task.FactoryTask):
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

  def _UpdateState(self, max_values):
    state_msg = ''.join(
        _MSG_SUBTESTS.format(state=('test-pass' if v > self.rotation_threshold
                                    else 'test-fail'),
                             key=k, value=v)
        for k, v in max_values.items())

    self.template.SetState(state_msg)

  def _WaitForDeviceStop(self):
    """Wait until absolute value of all sensors less than stop_threshold."""

    def CheckSensorState():
      data = self.gyroscope.GetData()
      return all(abs(v) < self.stop_threshold for v in data.values())

    sync_utils.WaitFor(CheckSensorState, self.timeout_secs)

  def _WaitForDeviceRotate(self):
    """Wait until all sensors has absolute value > rotation_threshold."""

    max_values = collections.defaultdict(float)
    def CheckSensorMaxValues():
      data = self.gyroscope.GetData()
      for sensor_name in data:
        max_values[sensor_name] = max(max_values[sensor_name],
                                      abs(data[sensor_name]))
      self._UpdateState(max_values)
      return all(abs(v) > self.rotation_threshold for v in max_values.values())

    sync_utils.WaitFor(CheckSensorMaxValues, self.timeout_secs)

  def StartTask(self):
    """Waits a period of time and then starts testing."""
    for i in xrange(self.setup_time_secs):
      self.template.SetState(GetPreparingMessage(self.setup_time_secs - i))
      time.sleep(1)

    try:
      self.template.SetInstruction(_MSG_IN_PROGRESS)
      self._WaitForDeviceStop()

      self.template.SetInstruction(_MSG_START_MOVING)
      self._WaitForDeviceRotate()
    except type_utils.TimeoutError as e:
      self.Fail(e.message)
      return

    self.template.SetState(' ' + _MSG_PASS + _BR, append=True)
    self.Pass()

  def Run(self):
    """Prompts a message to ask operator to press space."""
    if self.test.args.autostart:
      self.test.ui.AddEventHandler('StartTask', lambda _: self.StartTask())
      self.test.ui.PostEvent(event.Event(event.Event.Type.TEST_UI_EVENT,
                                         subtype='StartTask'))
    else:
      self.template.SetState(_MSG_SPACE)
      self.test.ui.BindKey(test_ui.SPACE_KEY, lambda _: self.StartTask())


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
          default=2, optional=True),
      Arg('autostart', bool, 'Auto start this test.',
          default=False, optional=True)]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.gyroscope = self.dut.gyroscope.GetController()
    self.ui = test_ui.UI()
    self.template = ui_templates.TwoSections(self.ui)
    self.ui.AppendCSS(_CSS)
    self._task_manager = None

  def runTest(self):
    task_list = [ReadGyroscopeTask(self, self.gyroscope,
                                   self.args.rotation_threshold,
                                   self.args.stop_threshold,
                                   self.args.timeout_secs,
                                   self.args.setup_time_secs)]
    self._task_manager = factory_task.FactoryTaskManager(self.ui, task_list)
    self._task_manager.Run()
