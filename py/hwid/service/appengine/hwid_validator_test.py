#!/usr/bin/env python2
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for HwidValidator."""

import os
import unittest

import mock

# pylint: disable=import-error
import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine import hwid_validator
from cros.factory.hwid.service.appengine import verification_payload_generator
from cros.factory.hwid.v3 import validator as v3_validator
from cros.factory.utils import file_utils

TESTDATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'testdata')

GOLDEN_HWIDV3_DATA_BEFORE = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-before.yaml')).decode('utf-8')
GOLDEN_HWIDV3_DATA_AFTER_BAD = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-bad.yaml')).decode('utf-8')
GOLDEN_HWIDV3_DATA_AFTER_GOOD = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-good.yaml')).decode('utf-8')
SARIEN_DATA_GOOD = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'sarien-example.yaml')).decode('utf-8')
GOLDEN_HWIDV3_DATA_AFTER_DRAM_BAD1 = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-dram-bad1.yaml')
    ).decode('utf-8')
GOLDEN_HWIDV3_DATA_AFTER_DRAM_BAD2 = file_utils.ReadFile(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-dram-bad2.yaml')
    ).decode('utf-8')


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
          hwid_validator.vpg_module,
          'GenerateVerificationPayload',
          side_effect=verification_payload_generator.\
              GenerateVerificationPayloadError('fail')):
        hwid_validator.HwidValidator().ValidateChange(SARIEN_DATA_GOOD,
                                                      SARIEN_DATA_GOOD)

  def testValidateNonSarien_withGeneratePayloadFail(self):
    with mock.patch.object(
        hwid_validator.vpg_module,
        'GenerateVerificationPayload',
        side_effect=verification_payload_generator.\
            GenerateVerificationPayloadError('fail')):
      hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_GOOD,
          GOLDEN_HWIDV3_DATA_BEFORE)

  def testValidateDramChange1(self):
    with self.assertRaises(v3_validator.ValidationError) as error:
      hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_DRAM_BAD1, GOLDEN_HWIDV3_DATA_BEFORE)
    self.assertEqual(
        str(error.exception),
        'dram_type_256mb_and_real_is_512mb does not match size property 1024M')

  def testValidateDramChange2(self):
    with self.assertRaises(v3_validator.ValidationError) as error:
      hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_DRAM_BAD2, GOLDEN_HWIDV3_DATA_BEFORE)
    self.assertEqual(
        str(error.exception),
        'Invalid DRAM: dram_type_not_mention_size')


if __name__ == '__main__':
  unittest.main()
