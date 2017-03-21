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

Sample test_list entry::

  OperatorTest(
    id='TouchscreenUniformity',
    label_zh=u'触屏均一性测试',
    run_if='device_data.component.has_touchscreen',
    pytest_name='touchscreen_uniformity',
    dargs={'deltas_max_val': 40,
           'deltas_min_val': -30,
           'refs_max_val': 25100,
           'refs_min_val': 23400})

The args thresholds in need to be experimentally determined by checking
a set of machines. The test logs the actual max and min values found.
"""

import logging
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.external import numpy
from cros.factory.test import event_log
from cros.factory.test import factory_task
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


_LABEL_CALIBRATING_TOUCHSCREEN = i18n_test_ui.MakeI18nLabelWithClass(
    'Calibrating Touchscreen', 'test-info')
_LABEL_NOT_FOUND = i18n_test_ui.MakeI18nLabelWithClass(
    'ERROR: Touchscreen Not Found', 'test-fail')
_LABEL_TESTING_REFERENCES = i18n_test_ui.MakeI18nLabelWithClass(
    'Testing References', 'test-info')
_LABEL_TESTING_DELTAS = i18n_test_ui.MakeI18nLabelWithClass(
    'Testing Deltas', 'test-info')
_LABEL_PASS = i18n_test_ui.MakeI18nLabelWithClass('PASS', 'test-pass')
_LABEL_FAIL = i18n_test_ui.MakeI18nLabelWithClass('FAIL', 'test-fail')
_MESSAGE_DELAY_SECS = 1

_BR = '<br>'

_CSS = """
  .test-info {font-size: 2em;}
  .test-pass {font-size: 2em; color:green;}
  .test-fail {font-size: 2em; color:red;}
"""


class CalibrateTouchscreenTask(factory_task.FactoryTask):
  """Recalibrates the touch controller."""

  def __init__(self, test):
    super(CalibrateTouchscreenTask, self).__init__()
    self.template = test.template
    self.touchscreen = test.touchscreen

  def Run(self):
    self.template.SetState(_LABEL_CALIBRATING_TOUCHSCREEN)
    if self.touchscreen.CalibrateController():
      self.template.SetState(' ' + _LABEL_PASS + _BR, append=True)
      self.Pass()
    else:
      self.template.SetState(' ' + _LABEL_FAIL + _BR, append=True)
      self.Fail('Touchscreen calibration failed.')


class CheckRawDataTask(factory_task.FactoryTask):
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
    for row_index in xrange(len(data)):
      for col_index in xrange(len(data[row_index])):
        val = data[row_index][col_index]
        if not self.min_val <= val <= self.max_val:
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
    event_log.Log('touchscreen_%s_stats' % self.data_name,
                  allowed_min_val=self.min_val,
                  allowed_max_val=self.max_val,
                  acutal_min_val=actual_min_val,
                  acutal_max_val=actual_max_val,
                  standard_deviation=standard_deviation,
                  test_passed=check_passed)

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
    super(CheckReferencesTask, self).__init__(
        test, 'refs', _LABEL_TESTING_REFERENCES,
        test.touchscreen.GetRefValues, test.args.refs_min_val,
        test.args.refs_max_val)


class CheckDeltasTask(CheckRawDataTask):
  """Checks delta data is in an expected range."""

  def __init__(self, test):
    super(CheckDeltasTask, self).__init__(
        test, 'deltas', _LABEL_TESTING_DELTAS,
        test.touchscreen.GetDeltaValues, test.args.deltas_min_val,
        test.args.deltas_max_val)


class CheckTouchController(factory_task.FactoryTask):
  """Verifies that the touch controler interface exists."""

  def __init__(self, test):
    super(CheckTouchController, self).__init__()
    self.template = test.template
    self.touchscreen = test.touchscreen

  def Run(self):
    if self.touchscreen.CheckController():
      self.Pass()
    else:
      self.template.SetState(_LABEL_NOT_FOUND)
      time.sleep(_MESSAGE_DELAY_SECS)
      self.Fail('Touch controller not found.')


class WaitTask(factory_task.FactoryTask):
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
      Arg('refs_max_val', int, 'Maximum value for reference data.'),
      Arg('refs_min_val', int, 'Minimum value for reference data.'),
      Arg('deltas_max_val', int, 'Maximum value for delta data.'),
      Arg('deltas_min_val', int, 'Minimum value for delta data.'),
      Arg('matrix_size', tuple,
          'The size of touchscreen sensor row data for enabled sensors in the '
          'form of (rows, cols). This is used when the matrix size read from '
          'kernel i2c device path is different from the matrix size of '
          'enabled sensors.',
          optional=True),
      Arg('device_index', int, 'Index of touchscreen to test.', default=0)]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_CSS)
    dut = device_utils.CreateDUTInterface()
    self.touchscreen = dut.touchscreen.GetController(self.args.device_index)
    self.touchscreen.SetSubmatrixSize(self.args.matrix_size)

  def runTest(self):
    task_list = [
        CheckTouchController(self),
        CalibrateTouchscreenTask(self),
        CheckReferencesTask(self),
        CheckDeltasTask(self),
        WaitTask(_MESSAGE_DELAY_SECS)
    ]
    task_manager = factory_task.FactoryTaskManager(self.ui, task_list)
    task_manager.Run()
