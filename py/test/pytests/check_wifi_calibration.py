# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''Checks Wifi calibration table from
/sys/kernel/debug/ieee80211/phy*/ath9k/dump_eep_power

If the test fails, then the test displays tables and hangs forever.'''


import glob
import pprint
import re
import unittest

from cros.factory.event_log import EventLog
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg

ANCHOR_FOR_LOW_BAND_CALIBRATION_DATA = 'calPierData2G'
ANCHOR_FOR_HIGH_BAND_CALIBRATION_DATA = 'calPierData5G'
EEP_POWER_PATH = '/sys/kernel/debug/ieee80211/phy*/ath9k/dump_eep_power'


def IsInRange(observed, min_val, max_val):
  '''Returns True if min_val <= observed <= max_val.

  If any of min_val or max_val is missing, it means there is no lower or
  upper bounds respectively.
  '''
  if min_val and observed < min_val:
    return False
  if max_val and observed > max_val:
    return False
  return True


def CheckRefPowerRange(table, expected_range_dict, band_name):
  '''Checks if the ref power is in range.'''
  for row_idx, single_row in enumerate(table):
    chain = int(single_row[0])
    ref_power = int(single_row[1])
    expected_range = expected_range_dict[chain]
    if not IsInRange(ref_power, expected_range[0], expected_range[1]):
      factory.console.info('Ref power of %s, row[%d], '
                           'chain[%d] is out of range' %
                           (band_name, row_idx, chain))
      return False
  return True


def CheckCalibratedUnits(table, min_required_units, band_name):
  '''Checks min_required_units presented in calibration table.'''
  if len(table) < min_required_units:
    factory.console.info(
        '%s table has only %d calibrated units, '
        '%d required' %
        (band_name, len(table), min_required_units))
    return False
  return True


class CheckWifiCalibrationTest(unittest.TestCase):
  ARGS = [
    Arg('min_low_band_required_unit', int,
        'Expected the minimum numbers of calibrate units in 2.4G'),
    Arg('min_high_band_required_unit', int,
        'Expected the minimum numbers of calibrate units in 5G'),
    Arg('expected_low_band_ref_power_range', dict,
        'Expected range (min, max) for each chain in 2.4G.\n'
        'Chain is the key of the dict.\n'
        'For example, {0: (-20, None),\n'
        '              1: (None, -10)}\n'
        'will check all refPower for chain 0 is greater than -20\n'
        'and all refPower for chain 1 is less than -10.\n'
        ),
    Arg('expected_high_band_ref_power_range', dict,
        'Expected range (min, max) for each chain in 5G.\n'
        'Chain is the key of the dict.')
  ]
  def readCalibrationTable(self, path, anchor_string):
    with open(path) as f:
      lines = f.readlines()
    idx = 0
    # Find the anchor
    for line in lines:
      idx = idx + 1
      if re.search(anchor_string, line):
        break
    # Read the table until reach an empty line.
    table = []
    for line in lines[idx:]:
      if re.search('^$', line):
        break
      table.append(line.split())
    return table

  def runTest(self):
    # Found location of dump_eep_power
    eep_power_path = glob.glob(EEP_POWER_PATH)
    if len(eep_power_path) != 1:
      raise IOError('unable to read dump_eep_power')

    eep_power_path = eep_power_path[0]

    low_band_table = self.readCalibrationTable(
        eep_power_path, ANCHOR_FOR_LOW_BAND_CALIBRATION_DATA)
    high_band_table = self.readCalibrationTable(
        eep_power_path, ANCHOR_FOR_HIGH_BAND_CALIBRATION_DATA)

    factory.console.info('2.4GHz table=%s' %
                         pprint.pformat(low_band_table, width=200))
    factory.console.info('5GHz table=%s' %
                         pprint.pformat(high_band_table, width=200))
    event_log = EventLog.ForAutoTest()
    event_log.Log('low_band_table', value=low_band_table)
    event_log.Log('high_band_table', value=high_band_table)

    # Check numbers of calibrated units.
    failed_flag = False
    if not CheckCalibratedUnits(
        low_band_table[1:], self.args.min_low_band_required_unit, '2.4G'):
      failed_flag = True
    if not CheckCalibratedUnits(
        high_band_table[1:], self.args.min_high_band_required_unit, '5G'):
      failed_flag = True

    # Check ref power
    if not CheckRefPowerRange(
        low_band_table[1:],
        self.args.expected_low_band_ref_power_range, '2.4G'):
      failed_flag = True
    if not CheckRefPowerRange(
        high_band_table[1:],
        self.args.expected_high_band_ref_power_range, '5G'):
      failed_flag = True

    if not failed_flag:
      return  # Pass the test

    ui = test_ui.UI()
    template = ui_templates.OneSection(ui)
    template.SetTitle(test_ui.MakeLabel(
        "Calibration data doesn't meet requirement"))
    template.SetState(
        '<div class=test-status-failed '
        'style="font-size: 100%; white-space: pre-wrap">' +
        '2.4G = %s\n' % pprint.pformat(low_band_table, width=200) +
        '5G = %s\n' % pprint.pformat(high_band_table, width=200) +
        '</div>')
    ui.Run()  # Forever
