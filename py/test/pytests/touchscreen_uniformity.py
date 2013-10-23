# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for checking touchscreen uniformity.

This test is intended to be run during run-in without a fixture or operator.
The test recalibrates the touchscreen then reads raw reference (baseline) data.
Each value must fall within a specified max and min range. Delta values (the
baseline - current reading) are also checked.

Sample test_list entry:

TOUCHSCREEN_UNIFORMITY = OperatorTest(
  id='TouchscreenUniformity',
  label_zh=u'触屏均一性测试',
  run_if='device_data.component.has_touchscreen',
  pytest_name='touchscreen_uniformity',
  dargs={'deltas_max_val': 40,
         'deltas_min_val': -30,
         'refs_max_val': 25100,
         'refs_min_val': 23400,
         'i2c_bus_id': '10-004a'})

The args thresholds in need to be experimentally determined by checking
a set of machines. The test logs the actual max and min values found.
"""

import logging
import os
import time
import unittest
import numpy

from cros.factory.event_log import Log
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager

_CALIBRATION_DELAY_SECS = 0.1
_DEFAULT_REFS_MAX = 24600
_DEFAULT_REFS_MIN = 23400
_DEFAULT_DELTAS_MAX = 30
_DEFAULT_DELTAS_MIN = -20
_DEFAULT_I2C_BUS_ID = '10-004a'

_I2C_DEVICES_PATH = '/sys/bus/i2c/devices'
_KERNEL_DRIVER_PATH = '/sys/kernel/debug/atmel_mxt_ts'

_LABEL_CALIBRATING_TOUCHSCREEN = test_ui.MakeLabel('Calibrating Touchscreen',
    u'触屏校正中', 'test-info')
_LABEL_NOT_FOUND = test_ui.MakeLabel('ERROR: Touchscreen Not Found',
    u'没有找到触屏', 'test-fail')
_LABEL_TESTING_REFERENCES = test_ui.MakeLabel('Testing References',
    u'参考值测试中', 'test-info')
_LABEL_TESTING_DELTAS = test_ui.MakeLabel('Testing Deltas',
    u'差量测试中', 'test-info')
_LABEL_PASS = test_ui.MakeLabel('PASS', u'成功', 'test-pass')
_LABEL_FAIL = test_ui.MakeLabel('FAIL', u'失败', 'test-fail')
_MESSAGE_DELAY_SECS = 1

_BR = '<br/>'

_CSS = """
  .test-info {font-size: 2em;}
  .test-pass {font-size: 2em; color:green;}
  .test-fail {font-size: 2em; color:red;}
"""

class AtmelTouchController(object):
  """Utility class for the Atmel 1664s touch controller.

  Args:
    i2c_bus_id: String. I2C device identifier. Ex: '10-004a'
  """

  def __init__(self, i2c_bus_id):
    i2c_device_path = os.path.join(_I2C_DEVICES_PATH, i2c_bus_id)
    self.object_path = os.path.join(i2c_device_path, 'object')
    self.kernel_device_path = os.path.join(_KERNEL_DRIVER_PATH, i2c_bus_id)
    self.rows = None
    self.cols = None
    if self.IsPresent():
      matrix_path = os.path.join(i2c_device_path, 'matrix_size')
      with open(matrix_path, 'r') as f:
        self.rows, self.cols = [
            int(val) for val in f.readline().strip().split()]

  def IsPresent(self):
    """Checks that the touch controller is present.

    Returns:
      True if the controller is present.
    """
    return os.path.exists(self.object_path)

  def _ReadRaw(self, filename):
    """Reads rows * cols touchscreen sensor raw data.

    Args:
      filename: Name of the raw data file to open from within the
                kernel debug directory.
    Retruns:
      Raw data as a [row][col] array of ints.
    """
    file_path = os.path.join(self.kernel_device_path, filename)
    raw_data = []
    with open(file_path) as f:
      for dummy_row in range(self.rows):
        row_data = []
        line = f.read(self.cols * 2)
        for col_pos in range(0, self.cols * 2, 2):
          # Correct endianness
          s = line[col_pos + 1] + line[col_pos]
          val = int(s.encode('hex'), 16)
          # Correct signed values
          if val > 32768:
            val = val - 65535

          row_data.append(val)

        raw_data.append(row_data)

    return raw_data

  def ReadDeltas(self):
    """Read raw delta information from the controller

    Return:
      A [row][col] list of raw data values.
    """
    logging.info('Reading deltas')
    return self._ReadRaw('deltas')

  def ReadRefs(self):
    """Reads raw reference (baseline) information from the controller.

    Return:
      A [row][col] list of raw data values.
    """
    logging.info('Reading refs')
    return self._ReadRaw('refs')

  def Calibrate(self):
    """Forces calibration of the touchscreen.

    Returns:
      True if calibration was successful.
    """
    logging.info('Calibrating touchscreen')
    # Force calibration with T6 instance 0, byte 2 (calibrate), non-zero value.
    self.WriteObject('06000201')
    # Empirical value to give the controller some time to finish calibration.
    time.sleep(_CALIBRATION_DELAY_SECS)
    return True #TODO(dparker): Figure out how to detect calibration errors.

  def WriteObject(self, value):
    """Writes an object control value to the controller.

    Args:
      value: A string of the object control value to write.
    """
    with open(self.object_path, 'w') as f:
      f.write(value)

    time.sleep(0.1)


class CalibrateTouchscreenTask(FactoryTask):
  """Recalibrates the touch controller."""

  def __init__(self, test):
    super(CalibrateTouchscreenTask, self).__init__()
    self.template = test.template
    self.touch_controller = test.touch_controller

  def Run(self):
    self.template.SetState(_LABEL_CALIBRATING_TOUCHSCREEN)
    if self.touch_controller.Calibrate():
      self.template.SetState(' ' + _LABEL_PASS + _BR, append=True)
      self.Pass()
    else:
      self.template.SetState(' ' + _LABEL_FAIL + _BR, append=True)
      self.Fail('Touchscreen calibration failed.')


class CheckRawDataTask(FactoryTask):
  """Checks raw controler data is in an expected range.

  Args:
    test: The factory test calling this task.
    data_name: String. A short name of the data type being checked. The name
               must match the sysfs entries under the I2C device path.
    ui_label: String. Formatted HTML to append to the test UI.
    FetchData: The function to call to retrieve the test data to check.
    min_val: Int. The lower bound to check the raw data against.
    max_val: Int. The upper bound to check the raw data against.
  """

  def __init__(self, test, data_name, ui_label, FetchData, min_val, max_val):
    super(CheckRawDataTask, self).__init__()
    self.template = test.template
    self.data_name = data_name
    self.ui_label = ui_label
    self.FetchData = FetchData
    self.min_val = min_val
    self.max_val = max_val

  def checkRawData(self):
    """Checks that data from self.FetchData is within bounds.

    Returns:
      True if the data is in bounds.
    """
    logging.info('Checking %s values are between %d and %d',
                 self.data_name, self.min_val, self.max_val)
    check_passed = True
    data = self.FetchData()
    for row_index in range(len(data)):
      for col_index in range(len(data[row_index])):
        val = data[row_index][col_index]
        if (val < self.min_val or val > self.max_val):
          logging.info(
              'Raw data out of range: row=%d, col=%s, val=%d',
              row_index, col_index, val)
          check_passed = False

    merged_data = sum(data, [])
    actual_min_val = min(merged_data)
    actual_max_val = max(merged_data)
    standard_deviation = float(numpy.std(merged_data))
    logging.info('Lowest value: %d', actual_min_val)
    logging.info('Highest value: %d', actual_max_val)
    logging.info('Standard deviation %f', standard_deviation)
    Log('touchscreen_%s_stats' % self.data_name,
        **{
           'allowed_min_val': self.min_val,
           'allowed_max_val': self.max_val,
           'acutal_min_val': actual_min_val,
           'acutal_max_val': actual_max_val,
           'standard_deviation': standard_deviation,
           'test_passed': check_passed,
          }
    )

    return check_passed

  def Run(self):
    self.template.SetState(self.ui_label, append=True)
    if self.checkRawData():
      self.template.SetState(' ' + _LABEL_PASS + _BR, append=True)
      self.Pass()
    else:
      self.template.SetState(' ' + _LABEL_FAIL + _BR, append=True)
      self.Fail('Uniformity check on %s failed.' % self.data_name, later=True)


class CheckReferencesTask(CheckRawDataTask):
  """Checks refernece data is in an expected range."""

  def __init__(self, test):
    super(CheckReferencesTask, self).__init__(test, 'refs',
        _LABEL_TESTING_REFERENCES, test.touch_controller.ReadRefs,
        test.args.refs_min_val, test.args.refs_max_val)


class CheckDeltasTask(CheckRawDataTask):
  """Checks delta data is in an expected range."""

  def __init__(self, test):
    super(CheckDeltasTask, self).__init__(test, 'deltas',
        _LABEL_TESTING_DELTAS, test.touch_controller.ReadDeltas,
        test.args.deltas_min_val, test.args.deltas_max_val)


class CheckTouchController(FactoryTask):
  """Verifies that the touch controler interface exists."""

  def __init__(self, test):
    super(CheckTouchController, self).__init__()
    self.template = test.template
    self.touch_controller = test.touch_controller

  def Run(self):
    if self.touch_controller.IsPresent():
      self.Pass()
    else:
      self.template.SetState(_LABEL_NOT_FOUND)
      time.sleep(_MESSAGE_DELAY_SECS)
      self.Fail('Touch controller not found.')


class WaitTask(FactoryTask):
  """Waits for a specified number of seconds.

  Args:
    delay: Number of seconds to wait.
  """

  def __init__(self, delay):
    super(WaitTask, self).__init__()
    self.delay = delay

  def Run(self):
    time.sleep(self.delay)
    self.Pass()


class TouchscreenUniformity(unittest.TestCase):

  ARGS = [
    Arg('refs_max_val', int, 'Maximum value for reference data.',
      default=_DEFAULT_REFS_MAX, optional=True),
    Arg('refs_min_val', int, 'Minimum value for reference data.',
      default=_DEFAULT_REFS_MIN, optional=True),
    Arg('deltas_max_val', int, 'Maximum value for delta data.',
      default=_DEFAULT_DELTAS_MAX, optional=True),
    Arg('deltas_min_val', int, 'Minimum value for delta data.',
      default=_DEFAULT_DELTAS_MIN, optional=True),
    Arg('i2c_bus_id', str, 'i2c bus address of controller',
      default=_DEFAULT_I2C_BUS_ID, optional=True),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.touch_controller = AtmelTouchController(self.args.i2c_bus_id)
    self.ui.AppendCSS(_CSS)
    self._task_manager = None

  def runTest(self):

    task_list = [
        CheckTouchController(self),
        CalibrateTouchscreenTask(self),
        CheckReferencesTask(self),
        CheckDeltasTask(self),
        WaitTask(_MESSAGE_DELAY_SECS)
    ]
    self._task_manager = FactoryTaskManager(self.ui, task_list)
    self._task_manager.Run()
