#!/usr/bin/env python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for HwidValidator."""

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine import hwid_validator

TESTDATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'testdata')

GOLDEN_HWIDV3_DATA_BEFORE = open(
    os.path.join(TESTDATA_PATH, 'v3-golden-before.yaml'),
    'r').read().decode('utf-8')
GOLDEN_HWIDV3_DATA_AFTER_BAD = open(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-bad.yaml'),
    'r').read().decode('utf-8')
GOLDEN_HWIDV3_DATA_AFTER_GOOD = open(
    os.path.join(TESTDATA_PATH, 'v3-golden-after-good.yaml'),
    'r').read().decode('utf-8')


class HwidValidatorTest(unittest.TestCase):
  """Test for HwidValidator."""

  def testValidateChange_withValidChange(self):
    hwid_validator.HwidValidator().ValidateChange(GOLDEN_HWIDV3_DATA_AFTER_GOOD,
                                                  GOLDEN_HWIDV3_DATA_BEFORE)

  def testValidateChange_withInvalidChange(self):
    with self.assertRaises(hwid_validator.ValidationError):
      hwid_validator.HwidValidator().ValidateChange(
          GOLDEN_HWIDV3_DATA_AFTER_BAD, GOLDEN_HWIDV3_DATA_BEFORE)


if __name__ == '__main__':
  unittest.main()
