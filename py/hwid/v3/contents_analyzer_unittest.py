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
    expected_error = contents_analyzer.Error(
        contents_analyzer.ErrorCode.CONTENTS_ERROR,
        "'dram_type_256mb_and_real_is_512mb' does not contain size property")
    self.assertIn(expected_error, report.errors)

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
                               common.COMPONENT_STATUS.supported, False),
                              ('display_panel_100_200', 100, 200,
                               common.COMPONENT_STATUS.supported, True)]
        }, report.name_changed_components)

  def test_AnalyzeChange_PreconditionErrors(self):
    prev_db_contents = 'some invalid text for HWID DB.'
    curr_db_contents = 'some invalid text for HWID DB.'
    inst = contents_analyzer.ContentsAnalyzer(curr_db_contents, None,
                                              prev_db_contents)
    report = inst.AnalyzeChange(lambda s: s)
    self.assertTrue(report.precondition_errors)

  def test_AnalyzeChange_Normal(self):
    LineModificationStatus = (
        contents_analyzer.DBLineAnalysisResult.ModificationStatus)
    LinePart = contents_analyzer.DBLineAnalysisResult.Part
    LinePartType = contents_analyzer.DBLineAnalysisResult.Part.Type

    def _HWIDDBHeaderPatcher(contents):
      # Remove everything before the checksum line.
      lines = contents.splitlines()
      for i, line in enumerate(lines):
        if line.startswith('checksum:'):
          return '\n'.join(lines[i + 1:])
      return contents

    def _CreateNotModifiedLine(text):
      return contents_analyzer.DBLineAnalysisResult(
          LineModificationStatus.NOT_MODIFIED,
          [LinePart(LinePartType.TEXT, text)] if text else [])

    def _CreateAddedLine(text):
      return contents_analyzer.DBLineAnalysisResult(
          LineModificationStatus.NEWLY_ADDED,
          [LinePart(LinePartType.TEXT, text)] if text else [])

    prev_db_contents = file_utils.ReadFile(
        os.path.join(_TEST_DATA_PATH, 'test_analyze_change_db_before.yaml'))
    curr_db_contents = file_utils.ReadFile(
        os.path.join(_TEST_DATA_PATH, 'test_analyze_change_db_after.yaml'))
    inst = contents_analyzer.ContentsAnalyzer(curr_db_contents, None,
                                              prev_db_contents)
    report = inst.AnalyzeChange(_HWIDDBHeaderPatcher)
    self.assertFalse(report.precondition_errors)

    # The full report is too big, let's verify only some key parts of them.
    self.assertEqual(len(report.lines), 38)
    self.assertEqual(report.lines[:5], [
        _CreateNotModifiedLine(x) for x in
        ['', 'project: CHROMEBOOK', '', 'encoding_patterns:', '  0: default']
    ])
    self.assertEqual(report.lines[17:28], [
        _CreateNotModifiedLine('  display_panel_field:'),
        _CreateNotModifiedLine('    0:'),
        contents_analyzer.DBLineAnalysisResult(
            LineModificationStatus.NOT_MODIFIED, [
                LinePart(LinePartType.TEXT, '      display_panel: '),
                LinePart(LinePartType.COMPONENT_NAME,
                         'x@@@@component@display_panel@display_panel_A@@@@'),
            ]),
        _CreateAddedLine('    1:'),
        contents_analyzer.DBLineAnalysisResult(
            LineModificationStatus.NEWLY_ADDED, [
                LinePart(LinePartType.TEXT, '      display_panel: '),
                LinePart(
                    LinePartType.COMPONENT_NAME,
                    'x@@@@component@display_panel@display_panel_123_456#8@@@@'),
            ]),
        _CreateNotModifiedLine(''),
        _CreateNotModifiedLine('components:'),
        _CreateNotModifiedLine('  display_panel:'),
        _CreateNotModifiedLine('    items:'),
        contents_analyzer.DBLineAnalysisResult(
            LineModificationStatus.NOT_MODIFIED, [
                LinePart(LinePartType.TEXT, '      '),
                LinePart(LinePartType.COMPONENT_NAME,
                         'x@@@@component@display_panel@display_panel_A@@@@'),
                LinePart(LinePartType.TEXT, ':'),
            ]),
        contents_analyzer.DBLineAnalysisResult(
            LineModificationStatus.MODIFIED, [
                LinePart(LinePartType.TEXT, '        status: '),
                LinePart(LinePartType.COMPONENT_STATUS,
                         'x@@@@component@display_panel@display_panel_A@@@@'),
            ]),
    ])

    self.assertEqual(
        report.hwid_components, {
            'x@@@@component@display_panel@display_panel_A@@@@':
                contents_analyzer.HWIDComponentAnalysisResult(
                    'display_panel', 'display_panel_A', 'deprecated', False,
                    None, 1, None),
            'x@@@@component@display_panel@display_panel_123_456#8@@@@':
                contents_analyzer.HWIDComponentAnalysisResult(
                    'display_panel', 'display_panel_123_456#8', 'supported',
                    True, (123, 456), 2, 'display_panel_123_456#2'),
        })


if __name__ == '__main__':
  unittest.main()
