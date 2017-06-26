# -*- encoding: utf-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for checking touch uniformity.

This test is intended to be run during run-in without a fixture or operator.
The test recalibrates the touch device then reads raw reference (baseline) data.
Each value must fall within a specified max and min range. Delta values (the
baseline - current reading) are also checked.

Sample test_list entry::

  OperatorTest(
    id='TouchUniformity',
    pytest_name='touch_uniformity',
    dargs={
        'check_list': [
            (0, {'en-US': u'References', 'zh-CN': u'参考值'},
             23400, 25100, 0, 0),
            (1, {'en-US': u'Deltas', 'zh-CN': u'差量'}, -30, 40, 0, 0)
            ]})

The args thresholds in need to be experimentally determined by checking
a set of machines. The test logs the actual max and min values found.
"""

import collections
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
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils


_LABEL_CALIBRATING = i18n_test_ui.MakeI18nLabelWithClass(
    'Calibrating Touch device', 'test-info')
_LABEL_NOT_FOUND = i18n_test_ui.MakeI18nLabelWithClass(
    'ERROR: Touch device Not Found', 'test-fail')
_LABEL_TESTING = i18n_test_ui.MakeI18nLabelWithClass('Testing... ', 'test-info')
_LABEL_PASS = i18n_test_ui.MakeI18nLabelWithClass('PASS', 'test-pass')
_LABEL_FAIL = i18n_test_ui.MakeI18nLabelWithClass('FAIL', 'test-fail')
_MESSAGE_DELAY_SECS = 1

_BR = '<br>'

_CSS = """
  .test-info {font-size: 2em;}
  .test-pass {font-size: 2em; color:green;}
  .test-fail {font-size: 2em; color:red;}
"""

CheckItem = collections.namedtuple(
    'CheckItem', ['frame_idx', 'label', 'min_val', 'max_val', 'rows', 'cols'])


class CalibrateTask(factory_task.FactoryTask):
  """Recalibrates the touch controller."""

  def __init__(self, test):
    super(CalibrateTask, self).__init__()
    self.template = test.template
    self.controller = test.controller

  def Run(self):
    self.template.SetState(_LABEL_CALIBRATING)
    if self.controller.Calibrate():
      self.template.SetState(' ' + _LABEL_PASS + _BR, append=True)
      self.Pass()
    else:
      self.template.SetState(' ' + _LABEL_FAIL + _BR, append=True)
      time.sleep(_MESSAGE_DELAY_SECS)
      self.Fail('Touch device calibration failed.')


class CheckRawDataTask(factory_task.FactoryTask):
  """Checks raw controler data is in an expected range.

  Args:
    test: The factory test calling this task.
  """

  def __init__(self, test):
    super(CheckRawDataTask, self).__init__()
    self.test = test
    self.check_list = [CheckItem(*item) for item in test.args.check_list]

  def checkRawData(self, check_item, data):
    """Checks that data is within bounds.

    Returns:
      True if the data is in bounds.
    """
    logging.info('Checking values from frame %d are between %s and %s',
                 check_item.frame_idx, check_item.min_val, check_item.max_val)
    check_passed = True
    for row_index in xrange(check_item.rows or len(data)):
      for col_index in xrange(check_item.cols or len(data[0])):
        val = data[row_index][col_index]
        if not check_item.min_val <= val <= check_item.max_val:
          logging.info(
              'Raw data out of range: [%d, %d] = %s', row_index, col_index, val)
          check_passed = False

    merged_data = sum(data, [])
    actual_min_val = min(merged_data)
    actual_max_val = max(merged_data)
    standard_deviation = float(numpy.std(merged_data))
    logging.info('Lowest value: %s', actual_min_val)
    logging.info('Highest value: %s', actual_max_val)
    logging.info('Standard deviation %f', standard_deviation)
    event_log.Log('touch_%d_stats' % check_item.frame_idx,
                  allowed_min_val=check_item.min_val,
                  allowed_max_val=check_item.max_val,
                  acutal_min_val=actual_min_val,
                  acutal_max_val=actual_max_val,
                  standard_deviation=standard_deviation,
                  test_passed=check_passed)

    return check_passed

  def Run(self):
    matrices = self.test.controller.GetMatrices([item.frame_idx
                                                 for item in self.check_list])
    fails = []
    to_log = []
    for item, matrix in zip(self.check_list, matrices):
      self.test.template.SetState(
          _LABEL_TESTING +
          i18n_test_ui.MakeI18nLabelWithClass(item.label, 'test-info'),
          append=True)
      if self.checkRawData(item, matrix):
        self.test.template.SetState(' ' + _LABEL_PASS + _BR, append=True)
        to_log.append([dict(item._asdict()), 'PASS', matrix])
      else:
        self.test.template.SetState(' ' + _LABEL_FAIL + _BR, append=True)
        fails.append(item.frame_idx)
        to_log.append([dict(item._asdict()), 'FAIL', matrix])
    time.sleep(_MESSAGE_DELAY_SECS)

    if self.test.args.upload_log:
      serial_number = self.test.dut.info.GetSerialNumber()
      with file_utils.UnopenedTemporaryFile() as temp_path:
        with open(temp_path, 'w') as f:
          for obj in to_log:
            f.write('%r\n' % obj)
        testlog.AttachFile(
            path=temp_path,
            name='touch_uniformity.%s.log' % serial_number,
            mime_type='text/plain',
            description='plain text log of touch_uniformity')

    if fails:
      self.Fail('Uniformity check failed on frame %s.' % fails)
    else:
      self.Pass()


class CheckInterfaceTask(factory_task.FactoryTask):
  """Verifies that the touch controler interface exists."""

  def __init__(self, test):
    super(CheckInterfaceTask, self).__init__()
    self.template = test.template
    self.controller = test.controller

  def Run(self):
    if self.controller.CheckInterface():
      self.Pass()
    else:
      self.template.SetState(_LABEL_NOT_FOUND)
      time.sleep(_MESSAGE_DELAY_SECS)
      self.Fail('Touch controller not found.')


class TouchUniformity(unittest.TestCase):
  ARGS = [
      Arg('device_index', int, 'Index of touch device to test.', default=0),
      Arg('check_list', (tuple, list),
          'A list of sequence. Each sequence consists of six elements: '
          'frame_idx, label, min_val, max_val, rows, cols.\n'
          'frame_idx: Index of frame to check.\n'
          'label: A i18n translation dictionary of frame label.\n'
          'min_val: Lower bound for values in this frame.\n'
          'max_val: Upper bound for values in this frame.\n'
          'rows: Number of rows from top to check, or zero to check all.\n'
          'cols: Number of columns from left to check, or zero to check all.'),
      Arg('upload_log', bool, 'To upload log file via testlog or not.',
          default=True)]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_CSS)
    self.dut = device_utils.CreateDUTInterface()
    self.controller = self.dut.touch.GetController(self.args.device_index)

  def runTest(self):
    factory_task.FactoryTaskManager(self.ui, [
        CheckInterfaceTask(self),
        CalibrateTask(self),
        CheckRawDataTask(self),
        ]).Run()
