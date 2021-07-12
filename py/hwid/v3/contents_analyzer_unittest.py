#!/usr/bin/env python3
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os.path
import unittest

from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import contents_analyzer
from cros.factory.utils import file_utils


_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')

DB_DRAM_GOOD_PATH = os.path.join(_TEST_DATA_PATH,
                                 'test_database_db_good_dram.yaml')
DB_DRAM_BAD_PATH = os.path.join(_TEST_DATA_PATH,
                                'test_database_db_bad_dram.yaml')
DB_COMP_BEFORE_PATH = os.path.join(_TEST_DATA_PATH,
                                   'test_database_db_comp_before.yaml')
DB_COMP_AFTER_GOOD_PATH = os.path.join(
    _TEST_DATA_PATH, 'test_database_db_comp_good_change.yaml')


class ContentsAnalyzerTest(unittest.TestCase):

  def test_ValidateIntegrity_Pass(self):
    db_contents = file_utils.ReadFile(DB_DRAM_GOOD_PATH)
    inst = contents_analyzer.ContentsAnalyzer(db_contents, None, None)
    report = inst.ValidateIntegrity()
    self.assertFalse(report.errors)

  def test_ValidateIntegrity_BadDramField(self):
    db_contents = file_utils.ReadFile(DB_DRAM_BAD_PATH)
    inst = contents_analyzer.ContentsAnalyzer(db_contents, None, None)
    report = inst.ValidateIntegrity()
    expected_error_msg = ("'dram_type_256mb_and_real_is_512mb' does not "
                          "contain size property")
    self.assertIn(expected_error_msg, report.errors)

  def test_ValidateChange_GoodCompNameChange(self):
    prev_db_contents = file_utils.ReadFile(DB_COMP_BEFORE_PATH)
    curr_db_contents = file_utils.ReadFile(DB_COMP_AFTER_GOOD_PATH)
    inst = contents_analyzer.ContentsAnalyzer(curr_db_contents, None,
                                              prev_db_contents)
    report = inst.ValidateChange()
    self.assertEqual(
        {
            'display_panel': [('display_panel_9_10', 9, 10,
                               common.COMPONENT_STATUS.supported, True),
                              ('display_panel_still_invalid2', 0, 0,
                               common.COMPONENT_STATUS.supported, False)]
        }, report.name_changed_components)


if __name__ == '__main__':
  unittest.main()
