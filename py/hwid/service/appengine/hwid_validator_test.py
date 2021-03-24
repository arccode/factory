#!/usr/bin/env python3
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for HwidValidator."""

import collections
import os
import unittest
from unittest import mock

# pylint: disable=import-error
from cros.factory.hwid.service.appengine import hwid_validator
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import filesystem_adapter
from cros.factory.hwid.v3 import validator as v3_validator
from cros.factory.utils import file_utils

TESTDATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'testdata')

GOLDEN_MODEL_NAME = 'CHROMEBOOK'
GOLDEN_HWIDV3_DATA_BEFORE = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-before.yaml'))
GOLDEN_HWIDV3_DATA_AFTER_BAD = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-bad.yaml'))
GOLDEN_HWIDV3_DATA_AFTER_GOOD = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-good.yaml'))
SARIEN_MODEL_NAME = 'SARIEN'
SARIEN_DATA_GOOD = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'sarien-example.yaml'))
GOLDEN_HWIDV3_DATA_AFTER_DRAM_BAD = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-dram-bad.yaml'))
GOLDEN_HWIDV3_DATA_AFTER_INVALID_NAME_PATTERN = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-comp-bad.yaml'))
GOLDEN_HWIDV3_DATA_AFTER_VALID_NAME_PATTERN = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-comp-good.yaml'))
GOLDEN_HWIDV3_DATA_AFTER_INVALID_NAME_PATTERN_WITH_NOTE = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-comp-note-bad.yaml'))
GOLDEN_HWIDV3_DATA_AFTER_VALID_NAME_PATTERN_WITH_NOTE = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-comp-note-good.yaml'))


@mock.patch(
    ('cros.factory.hwid.service.appengine'
     '.hwid_validator.CONFIG.hwid_filesystem'),
    filesystem_adapter.LocalFileSystemAdapter(TESTDATA_PATH))
class HwidValidatorTest(unittest.TestCase):
  """Test for HwidValidator."""

  def testValidateChange_withValidChange(self):
    model, ret = hwid_validator.HwidValidator().ValidateChange(
        GOLDEN_HWIDV3_DATA_AFTER_GOOD, GOLDEN_HWIDV3_DATA_BEFORE)
    self.assertEqual(model, GOLDEN_MODEL_NAME)
    self.assertFalse(ret)

  def testValidateChange_withInvalidChange(self):
    with self.assertRaises(v3_validator.ValidationError):
      model, ret = hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_BAD, GOLDEN_HWIDV3_DATA_BEFORE)
      self.assertEqual(model, GOLDEN_MODEL_NAME)
      self.assertFalse(ret)

  def testValidateSarien_withValidChange(self):
    model, ret = hwid_validator.HwidValidator().ValidateChange(
        SARIEN_DATA_GOOD, SARIEN_DATA_GOOD)
    self.assertEqual(model, SARIEN_MODEL_NAME)
    self.assertFalse(ret)

  def testValidateSarien_withGeneratePayloadFail(self):
    with self.assertRaises(v3_validator.ValidationError):
      with mock.patch.object(
          hwid_validator.vpg_module, 'GenerateVerificationPayload',
          return_value=self.CreateBadVPGResult()):
        hwid_validator.HwidValidator().ValidateChange(SARIEN_DATA_GOOD,
                                                      SARIEN_DATA_GOOD)

  def testValidateNonSarien_withGeneratePayloadFail(self):
    with mock.patch.object(
        hwid_validator.vpg_module, 'GenerateVerificationPayload',
        return_value=self.CreateBadVPGResult()):
      model, ret = hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_GOOD, GOLDEN_HWIDV3_DATA_BEFORE)
      self.assertEqual(model, GOLDEN_MODEL_NAME)
      self.assertFalse(ret)

  def testValidateDramChange(self):
    with self.assertRaises(v3_validator.ValidationError) as error:
      hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_DRAM_BAD, GOLDEN_HWIDV3_DATA_BEFORE)
    self.assertEqual(
        str(error.exception),
        "'dram_type_not_mention_size' does not contain size property")

  @mock.patch(('cros.factory.hwid.v3.name_pattern_adapter'
               '.GetSupportedCategories'), return_value=set(['cpu']))
  def testValidateComponentNameInvalid(self, unused_func):
    del unused_func
    with self.assertRaises(v3_validator.ValidationError):
      hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_INVALID_NAME_PATTERN,
          GOLDEN_HWIDV3_DATA_BEFORE)

  @mock.patch(('cros.factory.hwid.v3.name_pattern_adapter'
               '.GetSupportedCategories'), return_value=set(['cpu']))
  def testValidateComponentNameValid(self, unused_func):
    del unused_func
    model, ret = hwid_validator.HwidValidator().ValidateChange(
        GOLDEN_HWIDV3_DATA_AFTER_VALID_NAME_PATTERN, GOLDEN_HWIDV3_DATA_BEFORE)
    self.assertEqual(model, GOLDEN_MODEL_NAME)
    self.assertEqual(
        {
            'cpu': [('cpu_1234_5678', 1234, 5678,
                     common.COMPONENT_STATUS.supported),
                    ('cpu_12345678', 12345678, 0,
                     common.COMPONENT_STATUS.unqualified)]
        }, ret)

  @mock.patch(('cros.factory.hwid.v3.name_pattern_adapter'
               '.GetSupportedCategories'), return_value=set(['cpu']))
  def testValidateComponentNameInvalidWithNote(self, unused_func):
    del unused_func
    with self.assertRaises(v3_validator.ValidationError) as ex:
      hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_INVALID_NAME_PATTERN_WITH_NOTE,
          GOLDEN_HWIDV3_DATA_BEFORE)
    self.assertEqual(
        str(ex.exception),
        ('Invalid component names with sequence number, please modify '
         'them as follows:\n'
         '- cpu_2_3#4 -> cpu_2_3#3\n'
         '- cpu_2_3#non-a-number -> cpu_2_3#4'))

  @mock.patch(('cros.factory.hwid.v3.name_pattern_adapter'
               '.GetSupportedCategories'), return_value=set(['cpu']))
  def testValidateComponentNameValidWithNote(self, unused_func):
    del unused_func
    model, ret = hwid_validator.HwidValidator().ValidateChange(
        GOLDEN_HWIDV3_DATA_AFTER_VALID_NAME_PATTERN_WITH_NOTE,
        GOLDEN_HWIDV3_DATA_BEFORE)
    self.assertEqual(model, GOLDEN_MODEL_NAME)
    self.assertEqual(
        {
            'cpu': [('cpu_2_3#3', 2, 3, common.COMPONENT_STATUS.supported),
                    ('cpu_3_4#5', 3, 4, common.COMPONENT_STATUS.unsupported)]
        }, ret)

  @classmethod
  def CreateBadVPGResult(cls):
    ret = hwid_validator.vpg_module.VerificationPayloadGenerationResult(
        generated_file_contents={}, error_msgs=['err1', 'err2'],
        payload_hash='', primary_identifiers=collections.defaultdict(dict))
    return ret


if __name__ == '__main__':
  unittest.main()
