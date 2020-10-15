#!/usr/bin/env python3
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for HwidValidator."""

import os
import unittest
from unittest import mock

# pylint: disable=import-error
from cros.factory.hwid.service.appengine import hwid_validator
from cros.factory.hwid.v3 import filesystem_adapter
from cros.factory.hwid.v3 import validator as v3_validator
from cros.factory.utils import file_utils

TESTDATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'testdata')

GOLDEN_HWIDV3_DATA_BEFORE = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-before.yaml'))
GOLDEN_HWIDV3_DATA_AFTER_BAD = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-bad.yaml'))
GOLDEN_HWIDV3_DATA_AFTER_GOOD = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-good.yaml'))
SARIEN_DATA_GOOD = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'sarien-example.yaml'))
GOLDEN_HWIDV3_DATA_AFTER_DRAM_BAD1 = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-dram-bad1.yaml'))
GOLDEN_HWIDV3_DATA_AFTER_DRAM_BAD2 = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-dram-bad2.yaml'))
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
    hwid_validator.HwidValidator().ValidateChange(GOLDEN_HWIDV3_DATA_AFTER_GOOD,
                                                  GOLDEN_HWIDV3_DATA_BEFORE)

  def testValidateChange_withInvalidChange(self):
    with self.assertRaises(v3_validator.ValidationError):
      hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_BAD, GOLDEN_HWIDV3_DATA_BEFORE)

  def testValidateSarien_withValidChange(self):
    hwid_validator.HwidValidator().ValidateChange(SARIEN_DATA_GOOD,
                                                  SARIEN_DATA_GOOD)

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
      hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_GOOD,
          GOLDEN_HWIDV3_DATA_BEFORE)

  def testValidateDramChange1(self):
    with self.assertRaises(v3_validator.ValidationError) as error:
      hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_DRAM_BAD1, GOLDEN_HWIDV3_DATA_BEFORE)
    self.assertEqual(
        str(error.exception), ("'dram_type_256mb_and_real_is_512mb' does not "
                               "match size property 1024M"))

  def testValidateDramChange2(self):
    with self.assertRaises(v3_validator.ValidationError) as error:
      hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_DRAM_BAD2, GOLDEN_HWIDV3_DATA_BEFORE)
    self.assertEqual(
        str(error.exception),
        'Invalid DRAM: dram_type_not_mention_size')

  def testValidateComponentNameInvalid(self):
    with self.assertRaises(v3_validator.ValidationError):
      hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_INVALID_NAME_PATTERN,
          GOLDEN_HWIDV3_DATA_BEFORE)

  def testValidateComponentNameValid(self):
    hwid_validator.HwidValidator().ValidateChange(
        GOLDEN_HWIDV3_DATA_AFTER_VALID_NAME_PATTERN,
        GOLDEN_HWIDV3_DATA_BEFORE)

  def testValidateComponentNameInvalidWithNote(self):
    with self.assertRaises(v3_validator.ValidationError) as ex:
      hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_INVALID_NAME_PATTERN_WITH_NOTE,
          GOLDEN_HWIDV3_DATA_BEFORE)
    self.assertEqual(
        str(ex.exception),
        ('Invalid component names with sequence number, please modify '
         'them as follows:\n'
         '- cpu_2#4 -> cpu_2#3\n'
         '- cpu_2#non-a-number -> cpu_2#4'))

  def testValidateComponentNameValidWithNote(self):
    hwid_validator.HwidValidator().ValidateChange(
        GOLDEN_HWIDV3_DATA_AFTER_VALID_NAME_PATTERN_WITH_NOTE,
        GOLDEN_HWIDV3_DATA_BEFORE)

  @classmethod
  def CreateBadVPGResult(cls):
    ret = hwid_validator.vpg_module.VerificationPayloadGenerationResult()
    ret.error_msgs = ['err1', 'err2']
    return ret


if __name__ == '__main__':
  unittest.main()
