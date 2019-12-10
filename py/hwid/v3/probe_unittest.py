#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import probe


TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')
TEST_DATABASE_PATH = os.path.join(TEST_DATA_PATH, 'test_probe_db.yaml')


class GenerateBOMFromProbedResultsTest(unittest.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(TEST_DATABASE_PATH, verify_checksum=False)

  def testEncodingPatternIndexAndImageIdCorrect(self):
    bom = probe.GenerateBOMFromProbedResults(
        self.database, {}, {}, {}, common.OPERATION_MODE.normal, False)[0]

    # The encoding pattern is always 0 for now.
    self.assertEqual(bom.encoding_pattern_index, 0)
    # No rule for image_id, use the maximum one.
    self.assertEqual(bom.image_id, 1)

    bom = probe.GenerateBOMFromProbedResults(
        self.database, {}, {}, {}, common.OPERATION_MODE.rma, False)[0]

    # The encoding pattern is always 0 for now.
    self.assertEqual(bom.encoding_pattern_index, 0)
    # Image ID should be RMA
    self.assertEqual(bom.image_id, 15)

  def testUseDefaultComponents(self):
    bom, mismatched_probed_results = probe.GenerateBOMFromProbedResults(
        self.database, {}, {}, {}, common.OPERATION_MODE.normal, False)

    self.assertEqual(mismatched_probed_results, {})
    self.assertEqual(bom.components,
                     {'comp_cls_1': [],
                      'comp_cls_2': ['comp_2_default'],
                      'comp_cls_3': []})

    # When allow_mismatched_components=True, don't use the default components
    bom = probe.GenerateBOMFromProbedResults(
        self.database, {}, {}, {}, common.OPERATION_MODE.normal, True)[0]
    self.assertEqual(
        bom.components, {'comp_cls_1': [], 'comp_cls_2': [], 'comp_cls_3': []})

  def testSomeComponentMismatched(self):
    probed_results = {
        'comp_cls_1': [
            {'name': 'comp11', 'values': {'key': 'value1'}},
            {'name': 'comp11', 'values': {'key': 'value1'}},

            # mismatched component.
            {'name': 'comp12', 'values': {'key': 'value2'}},
            {'name': 'comp13', 'values': {'key': 'value3'}},
        ],
        'comp_cls_2': [
            {'name': 'comp22', 'values': {'key': 'value2'}},
            {'name': 'comp21', 'values': {'key': 'value1'}},
        ],

        # mismatched component.
        'comp_cls_100': [],
        'comp_cls_200': [
            {'name': 'comp2001', 'values': {'key': 'value1'}}
        ]
    }

    bom, mismatched_probed_results = probe.GenerateBOMFromProbedResults(
        self.database, probed_results, {}, {}, common.OPERATION_MODE.normal,
        True)

    self.assertEqual(mismatched_probed_results,
                     {'comp_cls_1': [
                         {'name': 'comp12', 'values': {'key': 'value2'}},
                         {'name': 'comp13', 'values': {'key': 'value3'}}],
                      'comp_cls_100': [],
                      'comp_cls_200': [{'name': 'comp2001',
                                        'values': {'key': 'value1'}}]})
    self.assertEqual(bom.components,
                     {'comp_cls_1': ['comp_1_1', 'comp_1_1'],
                      'comp_cls_2': ['comp_2_1', 'comp_2_2'],
                      'comp_cls_3': []})

    self.assertRaises(common.HWIDException, probe.GenerateBOMFromProbedResults,
                      self.database, probed_results, {}, {},
                      common.OPERATION_MODE.normal, False)

    # In test_probe_db.yaml, encoded_fields only contains 'comp_cls_3',
    # therefore, all other fields will be ignored when
    # 'ignore_nonencoded_components' is set.
    bom, mismatched_probed_results = probe.GenerateBOMFromProbedResults(
        self.database, probed_results, {}, {}, common.OPERATION_MODE.rma,
        True)
    self.assertEqual(mismatched_probed_results, {})
    self.assertEqual(bom.components, {'comp_cls_3': []})

  def testDuplicateComponent(self):
    bad_probed_results = {
        'comp_cls_3': [
            {'name': 'match_1_and_2', 'values': {'key': 'this is bad'}}
        ]
    }
    self.assertRaises(common.HWIDException, probe.GenerateBOMFromProbedResults,
                      self.database, bad_probed_results, {}, {},
                      common.OPERATION_MODE.normal, False)
    good_probed_results = {
        'comp_cls_3': [
            {'name': 'match_1_and_3', 'values': {'key': 'this is okay'}}
        ]
    }
    bom, mismatched_probed_results = probe.GenerateBOMFromProbedResults(
        self.database, good_probed_results, {}, {},
        common.OPERATION_MODE.normal, True)
    self.assertFalse(mismatched_probed_results)
    self.assertEqual(bom.components['comp_cls_3'], ['comp_3_1'])

  def testIgnoreDefaultUnsupportedComponent(self):
    probed_results = {
        'comp_cls_1': [],
        'comp_cls_2': [{'name': 'comp22', 'values': {'key': 'valueX'}}],
    }

    bom = probe.GenerateBOMFromProbedResults(
        self.database, probed_results, {}, {}, common.OPERATION_MODE.normal,
        True)[0]

    self.assertEqual(bom.components,
                     {'comp_cls_1': [],
                      'comp_cls_2': ['comp_2_x'],
                      'comp_cls_3': []})

  def testUseNameMatch(self):
    probed_results = {
        'comp_cls_1': [{'name': 'comp11'}, {'name': 'comp12'}],
        'comp_cls_2': [],
        'comp_cls_3': [{'name': 'comp31'}]
    }

    bom = probe.GenerateBOMFromProbedResults(
        self.database, probed_results, {}, {}, common.OPERATION_MODE.normal,
        False, True)[0]

    self.assertEqual(bom.components,
                     {'comp_cls_1': ['comp11', 'comp12'],
                      'comp_cls_2': [],
                      'comp_cls_3': ['comp31']})


if __name__ == '__main__':
  unittest.main()
