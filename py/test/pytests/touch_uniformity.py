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

  {
    "pytest_name": "touch_uniformity",
    "args": {
      "check_list": [
        [0, "i18n! References", 23400, 25100, 0, 0],
        [1, "i18n! Deltas", -30, 40, 0, 0]
      ]
    }
  }

The args thresholds in need to be experimentally determined by checking
a set of machines. The test logs the actual max and min values found.
"""

import collections
import logging

from cros.factory.device import device_utils
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.i18n import _
from cros.factory.test import test_case
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils

from cros.factory.external import numpy


_LABEL_PASS = ['<span class="test-status-passed">', _('PASS'), '</span>']
_LABEL_FAIL = ['<span class="test-status-failed">', _('FAIL'), '</span>']
_MESSAGE_DELAY_SECS = 1

CheckItem = collections.namedtuple(
    'CheckItem', ['frame_idx', 'label', 'min_val', 'max_val', 'rows', 'cols'])


class TouchUniformity(test_case.TestCase):
  ARGS = [
      Arg('device_index', int, 'Index of touch device to test.', default=0),
      Arg('check_list', list,
          'A list of sequence. Each sequence consists of six elements: '
          'frame_idx, label, min_val, max_val, rows, cols.\n'
          'frame_idx: Index of frame to check.\n'
          'label: A i18n translation dictionary of frame label.\n'
          'min_val: Lower bound for values in this frame.\n'
          'max_val: Upper bound for values in this frame.\n'
          'rows: Number of rows from top to check, or zero to check all.\n'
          'cols: Number of columns from left to check, or zero to check all.'),
      Arg('keep_raw_logs', bool, 'Whether to attach the log by Testlog',
          default=True)]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.controller = self.dut.touch.GetController(self.args.device_index)
    self.check_list = [CheckItem(*item) for item in self.args.check_list]
    self.ui.ToggleTemplateClass('font-large', True)
    # Group checker for Testlog.
    self.group_checker = testlog.GroupParam(
        'data', ['frame_idx', 'min_value', 'max_value', 'standard_deviation'])

  def runTest(self):
    self.CheckInterface()
    self.Calibrate()
    self.CheckRawData()

  def CheckInterface(self):
    if not self.controller.CheckInterface():
      self.ui.SetState([
          '<span class="test-status-failed">',
          _('ERROR: Touch device not found'), '</span>'
      ])
      self.Sleep(_MESSAGE_DELAY_SECS)
      self.FailTask('Touch controller not found.')

  def Calibrate(self):
    self.ui.SetState(_('Calibrating Touch device'))
    if not self.controller.Calibrate():
      self.ui.SetState(_LABEL_FAIL, append=True)
      self.Sleep(_MESSAGE_DELAY_SECS)
      self.FailTask('Touch device calibration failed.')

  def _CheckSingleRawData(self, check_item, data):
    """Checks that data is within bounds.

    Returns:
      True if the data is in bounds.
    """
    logging.info('Checking values from frame %d are between %s and %s',
                 check_item.frame_idx, check_item.min_val, check_item.max_val)
    check_passed = True
    for row_index in range(check_item.rows or len(data)):
      for col_index in range(check_item.cols or len(data[0])):
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
                  actual_min_val=actual_min_val,
                  actual_max_val=actual_max_val,
                  standard_deviation=standard_deviation,
                  test_passed=check_passed)

    with self.group_checker:
      testlog.LogParam('frame_idx', check_item.frame_idx)
      testlog.LogParam('standard_deviation', standard_deviation)
      testlog.CheckNumericParam(
          'min_value', actual_min_val, min=check_item.min_val)
      testlog.CheckNumericParam(
          'max_value', actual_max_val, max=check_item.max_val)

    return check_passed

  def CheckRawData(self):
    matrices = self.controller.GetMatrices(
        [item.frame_idx for item in self.check_list])
    fails = []
    to_log = []
    self.ui.SetState('')
    for item, matrix in zip(self.check_list, matrices):
      status = None
      if self._CheckSingleRawData(item, matrix):
        status = _LABEL_PASS
        to_log.append([dict(item._asdict()), 'PASS', matrix])
      else:
        status = _LABEL_FAIL
        fails.append(item.frame_idx)
        to_log.append([dict(item._asdict()), 'FAIL', matrix])
      self.ui.SetState(
          ['<div>',
           _('Testing {item}...', item=item.label), status, '</div>'],
          append=True)
    self.Sleep(_MESSAGE_DELAY_SECS)

    if self.args.keep_raw_logs:
      with file_utils.UnopenedTemporaryFile() as temp_path:
        with open(temp_path, 'w') as f:
          for obj in to_log:
            f.write('%r\n' % obj)
        testlog.AttachFile(
            path=temp_path,
            name='touch_uniformity.log',
            mime_type='text/plain',
            description='plain text log of touch_uniformity')

    if fails:
      self.FailTask('Uniformity check failed on frame %s.' % fails)
